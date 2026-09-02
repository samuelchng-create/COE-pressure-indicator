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

from economic_features import ECONOMIC_FEATURE_COLUMNS, ECONOMIC_MODEL_VERSION, merge_economic_features


CATEGORIES = ("Category A", "Category B", "Category D")
ANALYSIS_START = pd.Timestamp("2015-10-01")
MODEL_VERSION = "v0.5-structural-ridge-change-post-2015-1"
DIRECTION_PROBABILITY_VERSION = "v0.1-prequential-residual-three-way-post-2015-1"
DIRECTION_LABELS = ("Decrease", "Stay", "Increase")
STAY_BAND = 1_000.0
FEATURE_AVAILABILITY = {
    "analysis window": "Only tenders from October 2015 onward enter training, validation and charts.",
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
    frame = frame[frame["month"] >= ANALYSIS_START].copy()
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
    economic_feature_columns: tuple[str, ...] | None = None,
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
        columns = economic_feature_columns or ECONOMIC_FEATURE_COLUMNS
        frame = merge_economic_features(frame, economic_features, columns=columns)
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


def direction_label(change: float, stay_band: float = STAY_BAND) -> str:
    """Map a premium change to the disclosed three-way outcome definition."""
    if change > stay_band:
        return "Increase"
    if change < -stay_band:
        return "Decrease"
    return "Stay"


def _smoothed_direction_probabilities(
    possible_changes: np.ndarray,
    smoothing: float = 1.0,
) -> dict[str, float]:
    counts = {label: smoothing for label in DIRECTION_LABELS}
    for change in possible_changes:
        counts[direction_label(float(change))] += 1.0
    total = float(sum(counts.values()))
    return {label: counts[label] / total for label in DIRECTION_LABELS}


def walk_forward_backtest(
    data: pd.DataFrame,
    category: str,
    economic_features: pd.DataFrame | None = None,
    economic_feature_columns: tuple[str, ...] | None = None,
    min_train: int = 60,
    interval_coverage: float = 0.80,
    min_calibration: int = 20,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    inner_splits: int = 4,
) -> pd.DataFrame:
    """Run an expanding-window, nested-tuning, one-step-ahead back-test."""
    frame = build_feature_frame(
        data,
        category,
        economic_features=economic_features,
        economic_feature_columns=economic_feature_columns,
    )
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


def prequential_direction_probabilities(
    backtest: pd.DataFrame,
    min_calibration: int = 20,
    smoothing: float = 1.0,
) -> pd.DataFrame:
    """Back-test three-way probabilities using only earlier OOS residuals.

    The structural point forecast is shifted by the empirical distribution of
    earlier walk-forward residuals. Laplace smoothing avoids unjustified zero
    probabilities. A historical-outcome-frequency baseline is computed at the
    same origins for a fair probability benchmark.
    """
    required = {"actual", "previous_premium", "structural", "tender_id", "category"}
    missing = sorted(required - set(backtest.columns))
    if missing:
        raise ValueError(f"Direction probability back-test is missing: {', '.join(missing)}")
    prior_residuals: list[float] = []
    prior_outcomes: list[str] = []
    rows: list[dict] = []
    for row in backtest.itertuples(index=False):
        actual_change = float(row.actual - row.previous_premium)
        predicted_change = float(row.structural - row.previous_premium)
        actual_direction = direction_label(actual_change)
        if len(prior_residuals) >= min_calibration:
            probabilities = _smoothed_direction_probabilities(
                predicted_change + np.asarray(prior_residuals), smoothing=smoothing
            )
            baseline_counts = {
                label: prior_outcomes.count(label) + smoothing for label in DIRECTION_LABELS
            }
            baseline_total = float(sum(baseline_counts.values()))
            baseline = {label: baseline_counts[label] / baseline_total for label in DIRECTION_LABELS}
            brier = sum(
                (probabilities[label] - float(label == actual_direction)) ** 2
                for label in DIRECTION_LABELS
            )
            baseline_brier = sum(
                (baseline[label] - float(label == actual_direction)) ** 2
                for label in DIRECTION_LABELS
            )
            rows.append(
                {
                    "category": row.category,
                    "tender_id": row.tender_id,
                    "actual_direction": actual_direction,
                    "predicted_direction": max(DIRECTION_LABELS, key=probabilities.get),
                    "probability_decrease": probabilities["Decrease"],
                    "probability_stay": probabilities["Stay"],
                    "probability_increase": probabilities["Increase"],
                    "brier_score": brier,
                    "frequency_baseline_brier": baseline_brier,
                    "log_loss": -float(np.log(probabilities[actual_direction])),
                    "frequency_baseline_log_loss": -float(np.log(baseline[actual_direction])),
                    "calibration_observations": len(prior_residuals),
                }
            )
        prior_residuals.append(float(row.actual - row.structural))
        prior_outcomes.append(actual_direction)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class NextTenderForecast:
    category: str
    tender_id: str
    previous_premium: float
    predicted_change: float
    predicted_premium: float
    predicted_direction: str
    probabilities: dict[str, float]
    selected_alpha: float
    calibration_observations: int
    quota_assumption: str


def forecast_next_tender(
    data: pd.DataFrame,
    category: str,
    backtest: pd.DataFrame,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    inner_splits: int = 4,
) -> NextTenderForecast:
    """Forecast the next exercise and derive empirical three-way probabilities.

    The official results feed contains completed tenders only. Until a separate
    timestamped quota announcement is ingested, the next exercise uses the last
    completed quota as a clearly disclosed neutral supply assumption.
    """
    ordered = data.sort_values(["month", "bidding_no"])
    latest_tender_id = str(ordered.iloc[-1]["tender_id"])
    latest_rows = ordered[ordered["tender_id"].eq(latest_tender_id)].copy()
    if latest_rows.empty:
        raise ValueError("No completed tender is available for a next-tender forecast")
    last_month = pd.Timestamp(latest_rows.iloc[0]["month"])
    last_bidding_no = int(latest_rows.iloc[0]["bidding_no"])
    if last_bidding_no == 1:
        next_month, next_bidding_no = last_month, 2
    else:
        next_month, next_bidding_no = last_month + pd.offsets.MonthBegin(1), 1
    next_tender_id = f"{next_month:%Y-%m}-{next_bidding_no}"

    synthetic = latest_rows.copy()
    synthetic["month"] = next_month
    synthetic["bidding_no"] = next_bidding_no
    synthetic["tender_id"] = next_tender_id
    synthetic["display_date"] = next_month + pd.to_timedelta((next_bidding_no - 1) * 14, unit="D")
    augmented = pd.concat([ordered, synthetic], ignore_index=True)
    frame = build_feature_frame(augmented, category)
    test = frame[frame["tender_id"].eq(next_tender_id)]
    train = frame[~frame["tender_id"].eq(next_tender_id)]
    if len(test) != 1 or train.empty:
        raise ValueError("Could not construct the next-tender feature row")
    columns = feature_columns(frame)
    alpha = _select_alpha(train, columns, alphas, inner_splits)
    model = _pipeline(alpha)
    model.fit(train[columns], train["target_change"])
    predicted_change = float(model.predict(test[columns])[0])
    previous_premium = float(test.iloc[0]["previous_premium"])
    residuals = (backtest["actual"] - backtest["structural"]).dropna().to_numpy(dtype=float)
    if len(residuals) < 20:
        raise ValueError("At least 20 earlier out-of-sample residuals are required")
    probabilities = _smoothed_direction_probabilities(predicted_change + residuals)
    return NextTenderForecast(
        category=category,
        tender_id=next_tender_id,
        previous_premium=previous_premium,
        predicted_change=predicted_change,
        predicted_premium=previous_premium + predicted_change,
        predicted_direction=max(DIRECTION_LABELS, key=probabilities.get),
        probabilities=probabilities,
        selected_alpha=alpha,
        calibration_observations=len(residuals),
        quota_assumption="Last completed category and Cat E quotas carried forward",
    )


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
