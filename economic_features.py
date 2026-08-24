"""As-of economic and financial features for COE tender forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd


ECONOMIC_MODEL_VERSION = "v0.5-structural-economy-ridge-change-post-2015-1"
ECONOMIC_FEATURE_AVAILABILITY = {
    "daily FX, volatility, rates and oil": "Observation date plus one calendar day, noon Singapore time.",
    "market changes": "Latest as-of value versus the latest value at least 30 calendar days earlier.",
    "Singapore CPI": "Month-end plus a conservative 45-day publication buffer.",
    "Singapore GDP and unemployment": "Quarter-end plus a conservative 75-day publication buffer.",
    "macro revision risk": "Current-vintage SingStat histories may contain later revisions.",
}
ECONOMIC_FEATURE_COLUMNS = (
    "sgd_per_usd",
    "sgd_per_usd_change_21d",
    "vix",
    "vix_change_21d",
    "us_10y_yield",
    "us_10y_yield_change_21d",
    "brent_usd",
    "brent_return_21d",
    "nasdaq_composite",
    "nasdaq_return_21d",
    "sg_real_gdp_yoy",
    "sg_cpi_yoy",
    "sg_unemployment_rate",
)
REQUIRED_COLUMNS = ("tender_id", "forecast_cutoff_at", *ECONOMIC_FEATURE_COLUMNS)


def validate_economic_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate the materialized one-row-per-tender feature dataset."""
    data = frame.copy()
    errors: list[str] = []
    missing = sorted(set(REQUIRED_COLUMNS) - set(data.columns))
    if missing:
        return data, [f"Missing required economic columns: {', '.join(missing)}"]

    data["forecast_cutoff_at"] = pd.to_datetime(data["forecast_cutoff_at"], utc=True, errors="coerce")
    if data["forecast_cutoff_at"].isna().any():
        errors.append("forecast_cutoff_at contains invalid timestamps")
    availability_columns = (
        "market_latest_available_at",
        "gdp_available_at",
        "cpi_available_at",
        "unemployment_available_at",
    )
    for column in availability_columns:
        if column not in data:
            continue
        data[column] = pd.to_datetime(data[column], utc=True, errors="coerce")
        if data[column].isna().any():
            errors.append(f"{column} contains invalid timestamps")
        elif (data[column] > data["forecast_cutoff_at"]).any():
            errors.append(f"{column} exceeds its forecast cutoff")
    if data["tender_id"].duplicated().any():
        errors.append("economic dataset contains duplicate tender_id rows")
    for column in ECONOMIC_FEATURE_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
        if data[column].isna().any():
            errors.append(f"{column} contains missing or non-numeric values")
        if np.isinf(data[column]).any():
            errors.append(f"{column} contains infinite values")
    return data.sort_values("forecast_cutoff_at").reset_index(drop=True), errors


def merge_economic_features(structural_frame: pd.DataFrame, economic: pd.DataFrame) -> pd.DataFrame:
    """Attach validated as-of variables without changing tender ordering."""
    validated, errors = validate_economic_features(economic)
    if errors:
        raise ValueError("; ".join(errors))
    columns = ["tender_id", *ECONOMIC_FEATURE_COLUMNS]
    merged = structural_frame.merge(validated[columns], on="tender_id", how="left", validate="one_to_one")
    missing_rows = merged[list(ECONOMIC_FEATURE_COLUMNS)].isna().any(axis=1)
    if missing_rows.any():
        missing_ids = ", ".join(merged.loc[missing_rows, "tender_id"].head(5))
        raise ValueError(f"Economic features are unavailable for structural tenders: {missing_ids}")
    return merged
