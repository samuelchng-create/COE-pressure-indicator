"""Leakage-safe structural COE forecasting and evaluation.

The official results table identifies tenders by month and bidding number, not
by the actual closing timestamp.  ``display_date`` is therefore approximate
and is used only for charts.  Model ordering uses ``tender_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from economic_features import ECONOMIC_MODEL_VERSION, merge_economic_features


CATEGORIES = ("Category A", "Category B", "Category D")
MODEL_VERSION = "v0.2-structural-ridge-change-1"
FEATURE_AVAILABILITY = {
    "announced_quota": "Known before the target tender opens.",
    "announced_cat_e_quota": "Known before the target tender opens.",
    "premium/bid/excess-demand/momentum": "Lagged by at least one completed tender.",
    "Cat E outcome signals": "Lagged by at least one completed tender.",
    "seasonality": "Calendar-known before the target tender.",
}

NUMERIC_COLUMNS = ("quota", "bids_success", "bids_received", "premium", "bidding_no")
REQUIRED_COLUMNS = ("month", "bidding_no", "vehicle_class", "quota", "bids_received", "premium")


def _clean_number(series: pd.Series) -> pd.Series:
    """Parse data.gov.sg numeric strings including commas and currency marks."""
    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def prepare_coe_data(records: Iterable[dict] | pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate official tender-level COE results."""
    frame = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    frame.columns = [str(c).lower().strip().replace(" ", "_") for c in frame.columns]
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Official COE data is missing required columns: {', '.join(missing)}")

    for column in NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = _clean_number(frame[column])
    frame["month"] = pd.to_datetime(frame["month"], format="%Y-%m", errors="coerce")
    frame = frame.dropna(subset=list(REQUIRED_COLUMNS)).copy()
    frame["bidding_no"] = frame["bidding_no"].astype(int)
    frame = frame[frame["bidding_no"].isin([1, 2])]
    frame["tender_id"] = (
        frame["month"].dt.strftime("%Y-%m") + "-" + frame["bidding_no"].astype(str)
    )
    frame["display_date"] = frame["month"] + pd.to_timedelta(
        (frame["bidding_no"] - 1) * 14, unit="D"
    )
    frame = frame.sort_values(["month", "bidding_no", "vehicle_class"])
    duplicate = frame.duplicated(["tender_id", "vehicle_class"], keep=False)
    if duplicate.any():
        raise ValueError("Official COE data contains duplicate tender/category rows")
    return frame.reset_index(drop=True)


def build_feature_frame(
    data: pd.DataFrame,
    category: str,
    economic_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build features whose values are available before each target tender.

    Outcome variables (premium, bids and demand pressure) are shifted.  The
    target tender's quota is intentionally not shifted: LTA announces supply
    before bidding.  The source dataset does not include release timestamps,
    so that availability assumption is disclosed and separately auditable.
    """
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")
    index_columns = ["month", "bidding_no", "tender_id", "display_date"]
    wide = data.pivot(index=index_columns, columns="vehicle_class", values=["premium", "quota", "bids_received"])
    wide = wide.sort_index(level=[0, 1])

    premium = wide["premium"][category]
    quota = wide["quota"][category]
    bids = wide["bids_received"][category]
    e_premium = wide["premium"]["Category E"]
    e_quota = wide["quota"]["Category E"]
    e_bids = wide["bids_received"]["Category E"]
    pressure = bids / quota
    e_pressure = e_bids / e_quota

    result = pd.DataFrame(index=wide.index)
    result["actual"] = premium
    result["previous_premium"] = premium.shift(1)
    result["target_change"] = premium - premium.shift(1)
    result["premium_lag1"] = premium.shift(1)
    result["premium_lag2"] = premium.shift(2)
    result["premium_lag3"] = premium.shift(3)
    result["momentum_lag1"] = (premium - premium.shift(1)).shift(1)
    result["momentum_lag2"] = (premium.shift(1) - premium.shift(2)).shift(1)
    result["bid_pressure_lag1"] = pressure.shift(1)
    result["bid_pressure_lag2"] = pressure.shift(2)
    result["excess_demand_lag1"] = (pressure - 1.0).shift(1)
    result["announced_quota"] = quota
    result["quota_lag1"] = quota.shift(1)
    result["announced_quota_change"] = quota / quota.shift(1) - 1.0
    result["cat_e_premium_lag1"] = e_premium.shift(1)
    result["cat_e_momentum_lag1"] = (e_premium - e_premium.shift(1)).shift(1)
    result["cat_e_bid_pressure_lag1"] = e_pressure.shift(1)
    result["announced_cat_e_quota"] = e_quota

    months = np.asarray(result.index.get_level_values("month").month)
    bid_numbers = np.asarray(result.index.get_level_values("bidding_no"))
    result["month_sin"] = np.sin(2 * np.pi * months / 12)
    result["month_cos"] = np.cos(2 * np.pi * months / 12)
    result["second_exercise"] = (bid_numbers == 2).astype(float)
    frame = result.replace([np.inf, -np.inf], np.nan).dropna().reset_index()
    if economic_features is not None:
        frame = merge_economic_features(frame, economic_features)
    return frame


NON_FEATURE_COLUMNS = {
    "month",
    "bidding_no",
    "tender_id",
    "display_date",
    "actual",
    "previous_premium",
    "target_change",
}


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in NON_FEATURE_COLUMNS]


def _pipeline(alpha: float):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


def _select_alpha(
    train: pd.DataFrame,
    columns: list[str],
    alphas: tuple[float, ...],
    inner_splits: int,
) -> float:
    """Select regularization using only time-ordered folds within training data."""
    n_splits = min(inner_splits, max(2, len(train) // 12))
    splitter = TimeSeriesSplit(n_splits=n_splits)
    scores: dict[float, list[float]] = {alpha: [] for alpha in alphas}
    for train_idx, validation_idx in splitter.split(train):
        inner_train = train.iloc[train_idx]
        validation = train.iloc[validation_idx]
        for alpha in alphas:
            model = _pipeline(alpha)
            model.fit(inner_train[columns], inner_train["target_change"])
            predicted = model.predict(validation[columns])
            scores[alpha].append(mean_absolute_error(validation["target_change"], predicted))
    return min(alphas, key=lambda alpha: (float(np.mean(scores[alpha])), alpha))


def _conformal_radius(residuals: list[float], coverage: float) -> float:
    """Finite-sample prequential split-conformal absolute-error radius."""
    n = len(residuals)
    quantile = min(1.0, np.ceil((n + 1) * coverage) / n)
    return float(np.quantile(np.asarray(residuals), quantile, method="higher"))


def walk_forward_backtest(
    data: pd.DataFrame,
    category: str,
    economic_features: pd.DataFrame | None = None,
    min_train: int = 60,
    interval_coverage: float = 0.80,
    min_calibration: int = 20,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    inner_splits: int = 4,
) -> pd.DataFrame:
    """Run an expanding-window, nested-tuning, one-step-ahead back-test."""
    frame = build_feature_frame(data, category, economic_features=economic_features)
    if len(frame) <= min_train:
        return pd.DataFrame()
    columns = feature_columns(frame)
    rows: list[dict] = []
    prior_errors: list[float] = []

    for position in range(min_train, len(frame)):
        train = frame.iloc[:position]
        test = frame.iloc[[position]]
        alpha = _select_alpha(train, columns, alphas, inner_splits)
        model = _pipeline(alpha)
        model.fit(train[columns], train["target_change"])
        predicted_change = float(model.predict(test[columns])[0])
        previous = float(test.iloc[0]["previous_premium"])
        predicted = previous + predicted_change
        actual = float(test.iloc[0]["actual"])
        radius = (
            _conformal_radius(prior_errors, interval_coverage)
            if len(prior_errors) >= min_calibration
            else np.nan
        )
        rows.append(
            {
                "category": category,
                "model_version": ECONOMIC_MODEL_VERSION if economic_features is not None else MODEL_VERSION,
                "tender_id": test.iloc[0]["tender_id"],
                "display_date": test.iloc[0]["display_date"],
                "train_end_tender": train.iloc[-1]["tender_id"],
                "actual": actual,
                "previous_premium": previous,
                "structural": predicted,
                "persistence": previous,
                "historical_mean_drift": previous + float(train["target_change"].mean()),
                "two_tender_seasonal": float(test.iloc[0]["premium_lag2"]),
                "lower": predicted - radius if np.isfinite(radius) else np.nan,
                "upper": predicted + radius if np.isfinite(radius) else np.nan,
                "selected_alpha": alpha,
                "n_train": len(train),
            }
        )
        prior_errors.append(abs(actual - predicted))
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class BacktestSummary:
    category: str
    observations: int
    metrics: pd.DataFrame
    best_naive: str
    mae_improvement_vs_best_naive: float
    rmse_improvement_vs_best_naive: float
    interval_coverage: float
    mean_interval_width: float


def summarize_backtest(backtest: pd.DataFrame) -> BacktestSummary:
    if backtest.empty:
        raise ValueError("Cannot summarize an empty back-test")
    models = ("structural", "persistence", "historical_mean_drift", "two_tender_seasonal")
    actual_direction = np.sign(backtest["actual"] - backtest["previous_premium"])
    records = []
    for model in models:
        prediction = backtest[model]
        records.append(
            {
                "model": model,
                "MAE": mean_absolute_error(backtest["actual"], prediction),
                "RMSE": mean_squared_error(backtest["actual"], prediction) ** 0.5,
                "direction_accuracy": float(
                    (actual_direction == np.sign(prediction - backtest["previous_premium"])).mean()
                ),
            }
        )
    metrics = pd.DataFrame(records).set_index("model")
    naive_names = [name for name in models if name != "structural"]
    best_naive = str(metrics.loc[naive_names, "MAE"].idxmin())
    structural_mae = float(metrics.loc["structural", "MAE"])
    structural_rmse = float(metrics.loc["structural", "RMSE"])
    naive_mae = float(metrics.loc[best_naive, "MAE"])
    naive_rmse = float(metrics.loc[best_naive, "RMSE"])
    calibrated = backtest.dropna(subset=["lower", "upper"])
    covered = (
        (calibrated["actual"] >= calibrated["lower"])
        & (calibrated["actual"] <= calibrated["upper"])
    )
    return BacktestSummary(
        category=str(backtest.iloc[0]["category"]),
        observations=len(backtest),
        metrics=metrics,
        best_naive=best_naive,
        mae_improvement_vs_best_naive=(naive_mae - structural_mae) / naive_mae,
        rmse_improvement_vs_best_naive=(naive_rmse - structural_rmse) / naive_rmse,
        interval_coverage=float(covered.mean()) if len(calibrated) else np.nan,
        mean_interval_width=float((calibrated["upper"] - calibrated["lower"]).mean())
        if len(calibrated)
        else np.nan,
    )
