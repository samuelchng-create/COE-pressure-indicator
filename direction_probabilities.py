"""Leakage-safe three-way probability layer for next-tender COE forecasts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from coe_model import _pipeline, _select_alpha, build_feature_frame, feature_columns


DIRECTION_PROBABILITY_VERSION = "v0.1-prequential-residual-three-way-post-2015-1"
DIRECTION_LABELS = ("Decrease", "Stay", "Increase")
STAY_BAND = 1_000.0


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


def prequential_direction_probabilities(
    backtest: pd.DataFrame,
    min_calibration: int = 20,
    smoothing: float = 1.0,
) -> pd.DataFrame:
    """Back-test three-way probabilities using only earlier OOS residuals."""
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
    """Forecast the next exercise and derive empirical three-way probabilities."""
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
