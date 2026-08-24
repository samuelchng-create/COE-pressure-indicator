"""Schema, validation and as-of aggregation for dealer observations.

No dealer index weights are defined here.  Raw fields are aggregated into
interpretable features and may only be retained if the combined model improves
future, untouched walk-forward forecasts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from coe_model import CATEGORIES


DEALER_COLUMNS = [
    "observation_id",
    "observed_at",
    "retrieved_at",
    "source_url",
    "source_type",
    "category",
    "brand",
    "model",
    "variant",
    "advertised_price",
    "previous_advertised_price",
    "coe_rebate_level",
    "guaranteed_coe",
    "guaranteed_coe_bid_count",
    "guaranteed_coe_terms",
    "finance_incentive_value",
    "trade_in_incentive_value",
    "cash_discount_value",
    "other_incentive_value",
    "promotion_deadline",
    "roadshow_name",
    "roadshow_start",
    "roadshow_end",
    "market_share_weight",
    "currency",
    "notes",
]

REQUIRED_DEALER_COLUMNS = {
    "observation_id",
    "observed_at",
    "retrieved_at",
    "source_url",
    "category",
    "brand",
    "model",
    "advertised_price",
    "guaranteed_coe",
    "market_share_weight",
}

DEALER_NUMERIC_COLUMNS = [
    "advertised_price",
    "previous_advertised_price",
    "coe_rebate_level",
    "guaranteed_coe_bid_count",
    "finance_incentive_value",
    "trade_in_incentive_value",
    "cash_discount_value",
    "other_incentive_value",
    "market_share_weight",
]

DEALER_DATE_COLUMNS = [
    "observed_at",
    "retrieved_at",
    "promotion_deadline",
    "roadshow_start",
    "roadshow_end",
]


def empty_dealer_template() -> pd.DataFrame:
    return pd.DataFrame(columns=DEALER_COLUMNS)


def validate_dealer_observations(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate observations without inventing or imputing signal values."""
    data = frame.copy()
    data.columns = [str(column).strip().lower() for column in data.columns]
    errors: list[str] = []
    missing = sorted(REQUIRED_DEALER_COLUMNS - set(data.columns))
    if missing:
        return data, [f"Missing required columns: {', '.join(missing)}"]
    for column in DEALER_COLUMNS:
        if column not in data:
            data[column] = pd.NA

    for column in DEALER_NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(
            data[column].astype("string").str.replace(",", "", regex=False).str.replace("$", "", regex=False),
            errors="coerce",
        )
    for column in DEALER_DATE_COLUMNS:
        data[column] = pd.to_datetime(data[column], errors="coerce", utc=True)

    guaranteed = data["guaranteed_coe"].astype("string").str.lower().map(
        {"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False}
    )
    if guaranteed.isna().any():
        errors.append("guaranteed_coe must be true/false (or yes/no, 1/0)")
    data["guaranteed_coe"] = guaranteed.astype("boolean")
    if data["observation_id"].duplicated().any():
        errors.append("observation_id values must be unique")
    if data["observed_at"].isna().any() or data["retrieved_at"].isna().any():
        errors.append("observed_at and retrieved_at must be valid timestamps")
    if (data["retrieved_at"] < data["observed_at"]).fillna(False).any():
        errors.append("retrieved_at cannot precede observed_at")
    if (~data["category"].isin(CATEGORIES)).any():
        errors.append("category must be Category A, Category B, or Category D")
    if (data["advertised_price"] <= 0).fillna(True).any():
        errors.append("advertised_price must be present and positive")
    invalid_weights = data["market_share_weight"].isna() | (data["market_share_weight"] < 0)
    if invalid_weights.any():
        errors.append("market_share_weight must be present and non-negative")
    if data["source_url"].astype("string").str.strip().eq("").any():
        errors.append("source_url is required for provenance")
    return data[DEALER_COLUMNS], errors


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna() & (weights >= 0)
    if not valid.any() or float(weights[valid].sum()) <= 0:
        return np.nan
    return float(np.average(values[valid], weights=weights[valid]))


def aggregate_before_cutoff(
    observations: pd.DataFrame,
    category: str,
    cutoff_at: pd.Timestamp,
    lookback_days: int = 21,
) -> dict[str, float]:
    """Aggregate only observations retrieved before a frozen forecast cutoff."""
    cutoff = pd.Timestamp(cutoff_at)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    start = cutoff - pd.Timedelta(days=lookback_days)
    sample = observations[
        (observations["category"] == category)
        & (observations["retrieved_at"] <= cutoff)
        & (observations["observed_at"] >= start)
        & (observations["observed_at"] <= cutoff)
    ].copy()
    if sample.empty:
        return {"dealer_observation_count": 0.0}

    weights = sample["market_share_weight"]
    price_change = sample["advertised_price"] - sample["previous_advertised_price"]
    incentive_columns = [
        "finance_incentive_value",
        "trade_in_incentive_value",
        "cash_discount_value",
        "other_incentive_value",
    ]
    total_incentive = sample[incentive_columns].fillna(0).sum(axis=1)
    deadline_days = (sample["promotion_deadline"] - cutoff).dt.total_seconds() / 86400
    active_roadshow = (
        sample["roadshow_start"].notna()
        & sample["roadshow_end"].notna()
        & (sample["roadshow_start"] <= cutoff)
        & (sample["roadshow_end"] >= cutoff)
    )
    return {
        "dealer_observation_count": float(len(sample)),
        "dealer_brand_count": float(sample["brand"].nunique()),
        "weighted_advertised_price": _weighted_mean(sample["advertised_price"], weights),
        "weighted_price_change": _weighted_mean(price_change, weights),
        "weighted_coe_rebate": _weighted_mean(sample["coe_rebate_level"], weights),
        "weighted_total_incentive": _weighted_mean(total_incentive, weights),
        "weighted_guaranteed_coe_share": _weighted_mean(sample["guaranteed_coe"].astype(float), weights),
        "weighted_promotion_deadline_days": _weighted_mean(deadline_days, weights),
        "weighted_active_roadshow_share": _weighted_mean(active_roadshow.astype(float), weights),
    }


def build_tender_dealer_features(
    observations: pd.DataFrame,
    tender_schedule: pd.DataFrame,
    lookback_days: int = 21,
) -> pd.DataFrame:
    """Create one as-of dealer feature row per category/tender cutoff.

    ``tender_schedule`` must contain tender_id, category and forecast_cutoff_at.
    The explicit schedule is required because the COE results dataset does not
    contain actual exercise timestamps.
    """
    required = {"tender_id", "category", "forecast_cutoff_at"}
    missing = sorted(required - set(tender_schedule.columns))
    if missing:
        raise ValueError(f"Tender schedule is missing: {', '.join(missing)}")
    rows = []
    for tender in tender_schedule.itertuples(index=False):
        features = aggregate_before_cutoff(
            observations,
            tender.category,
            pd.Timestamp(tender.forecast_cutoff_at),
            lookback_days,
        )
        rows.append(
            {
                "tender_id": tender.tender_id,
                "category": tender.category,
                "forecast_cutoff_at": pd.Timestamp(tender.forecast_cutoff_at),
                **features,
            }
        )
    return pd.DataFrame(rows)
