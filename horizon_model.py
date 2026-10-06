"""Leakage-safe direct multi-exercise COE forecasts with tender-calendar timing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from coe_model import (
    CATEGORIES,
    DIRECTION_LABELS,
    _conformal_radius,
    _pipeline,
    _select_alpha,
    build_feature_frame,
    direction_label,
    feature_columns,
)


HORIZONS = (1, 2, 4, 6)
HORIZON_MODEL_VERSION = "v0.12-direct-horizon-calendar-gap-post-2015-1"
CAR_STAY_BAND = 2_000.0
MOTORCYCLE_STAY_BAND = 1_000.0


def stay_band_for(category: str) -> float:
    return MOTORCYCLE_STAY_BAND if category == "Category D" else CAR_STAY_BAND


def prepare_tender_calendar(schedule: pd.DataFrame) -> pd.DataFrame:
    """Return one verified timing row per tender with close-to-close exposure."""
    required = {"tender_id", "exercise_end_at", "source_url"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"Tender calendar is missing: {', '.join(sorted(missing))}")
    calendar = schedule.copy()
    calendar["exercise_end_at"] = pd.to_datetime(calendar["exercise_end_at"], utc=True)
    if "forecast_cutoff_at" in calendar:
        calendar["forecast_cutoff_at"] = pd.to_datetime(calendar["forecast_cutoff_at"], utc=True)
    calendar = calendar.sort_values("exercise_end_at").drop_duplicates("tender_id", keep="last")
    calendar["gap_days"] = calendar["exercise_end_at"].diff().dt.total_seconds() / 86_400
    calendar["gap_weeks"] = calendar["gap_days"] / 7.0
    calendar["extended_gap"] = (calendar["gap_days"] >= 19).astype(float)
    return calendar.reset_index(drop=True)


def _ordered_category(data: pd.DataFrame, category: str) -> pd.DataFrame:
    ordered = (
        data[data["vehicle_class"].eq(category)]
        .sort_values(["month", "bidding_no"])
        .reset_index(drop=True)
    )
    ordered["position"] = np.arange(len(ordered))
    return ordered


def build_horizon_frame(
    data: pd.DataFrame,
    category: str,
    schedule: pd.DataFrame,
    horizon: int,
    economic_features: pd.DataFrame | None = None,
    economic_feature_columns: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Build origin-known features and a terminal premium target h exercises ahead."""
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")
    if horizon not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")

    calendar = prepare_tender_calendar(schedule)
    timing = calendar.set_index("tender_id")
    ordered = _ordered_category(data, category)
    tender_ids = ordered["tender_id"].tolist()
    premiums = ordered["premium"].astype(float).to_numpy()
    bids = ordered["bids_received"].astype(float).to_numpy()

    # A feature row for exercise i+1 contains only completed information through
    # origin i plus the already-announced next-exercise quota.
    base = build_feature_frame(
        data,
        category,
        economic_features=economic_features,
        economic_feature_columns=economic_feature_columns,
    ).set_index("tender_id", drop=False)
    rows: list[dict] = []
    for origin_position in range(len(ordered) - horizon):
        next_position = origin_position + 1
        target_position = origin_position + horizon
        next_id = tender_ids[next_position]
        target_id = tender_ids[target_position]
        origin_id = tender_ids[origin_position]
        if next_id not in base.index:
            continue
        row = base.loc[next_id].to_dict()
        if isinstance(base.loc[next_id], pd.DataFrame):
            raise ValueError(f"Duplicate structural feature row: {next_id}")

        origin_close = timing.at[origin_id, "exercise_end_at"] if origin_id in timing.index else pd.NaT
        next_close = timing.at[next_id, "exercise_end_at"] if next_id in timing.index else pd.NaT
        target_close = timing.at[target_id, "exercise_end_at"] if target_id in timing.index else pd.NaT
        timing_available = pd.notna(origin_close) and pd.notna(next_close) and pd.notna(target_close)
        next_gap_days = float((next_close - origin_close).total_seconds() / 86_400) if timing_available else 14.0
        horizon_days = float((target_close - origin_close).total_seconds() / 86_400) if timing_available else float(14 * horizon)

        prior_id = tender_ids[origin_position - 1] if origin_position > 0 else None
        prior_close = timing.at[prior_id, "exercise_end_at"] if prior_id in timing.index else pd.NaT
        prior_gap_days = (
            float((origin_close - prior_close).total_seconds() / 86_400)
            if pd.notna(origin_close) and pd.notna(prior_close)
            else 14.0
        )
        path_ids = tender_ids[next_position : target_position + 1]
        if timing_available:
            path_closes = [origin_close, *[timing.at[item, "exercise_end_at"] for item in path_ids]]
            extended_count = float(
                sum((later - earlier).total_seconds() / 86_400 >= 19 for earlier, later in zip(path_closes, path_closes[1:]))
            )
        else:
            extended_count = 0.0

        row.update(
            {
                "forecast_origin_tender": origin_id,
                "next_tender_id": next_id,
                "target_tender_id": target_id,
                "origin_position": origin_position,
                "target_position": target_position,
                "horizon": horizon,
                "actual": premiums[target_position],
                "previous_premium": premiums[origin_position],
                "target_change": premiums[target_position] - premiums[origin_position],
                "display_date": ordered.iloc[target_position]["display_date"],
                "timing_available": float(timing_available),
                "next_gap_days": next_gap_days,
                "next_gap_weeks": next_gap_days / 7.0,
                "next_extended_gap": float(next_gap_days >= 19),
                "horizon_calendar_days": horizon_days,
                "horizon_calendar_weeks": horizon_days / 7.0,
                "extended_gap_count": extended_count,
                "announced_quota_per_week": float(row["announced_quota"]) / (next_gap_days / 7.0),
                "bids_per_week_lag1": bids[origin_position] / (prior_gap_days / 7.0),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan).dropna()


HORIZON_NON_FEATURE_COLUMNS = {
    "month",
    "bidding_no",
    "tender_id",
    "display_date",
    "actual",
    "previous_premium",
    "target_change",
    "forecast_origin_tender",
    "next_tender_id",
    "target_tender_id",
    "origin_position",
    "target_position",
    "horizon",
}


def horizon_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in HORIZON_NON_FEATURE_COLUMNS]


def walk_forward_horizon_backtest(
    data: pd.DataFrame,
    category: str,
    schedule: pd.DataFrame,
    horizon: int,
    economic_features: pd.DataFrame | None = None,
    economic_feature_columns: tuple[str, ...] | None = None,
    min_train: int = 60,
    interval_coverage: float = 0.80,
    min_calibration: int = 20,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    inner_splits: int = 4,
) -> pd.DataFrame:
    """Direct horizon back-test; training targets must finish by the test origin."""
    frame = build_horizon_frame(
        data,
        category,
        schedule,
        horizon,
        economic_features=economic_features,
        economic_feature_columns=economic_feature_columns,
    )
    columns = horizon_feature_columns(frame)
    rows: list[dict] = []
    residual_records: list[tuple[int, float]] = []
    for test in frame.itertuples(index=False):
        # Embargo overlapping labels: a training target must be completed no
        # later than this forecast's origin.
        train = frame[frame["target_position"] <= test.origin_position]
        if len(train) < min_train:
            continue
        test_frame = frame[frame["origin_position"].eq(test.origin_position)].iloc[[0]]
        alpha = _select_alpha(train, columns, alphas, inner_splits)
        model = _pipeline(alpha)
        model.fit(train[columns], train["target_change"])
        predicted_change = float(model.predict(test_frame[columns])[0])
        previous = float(test.previous_premium)
        actual = float(test.actual)
        predicted = previous + predicted_change
        available_errors = [
            error
            for target_position, error in residual_records
            if target_position <= int(test.origin_position)
        ]
        radius = (
            _conformal_radius(available_errors, interval_coverage)
            if len(available_errors) >= min_calibration
            else np.nan
        )
        historical_drift = float(train["target_change"].mean())
        origin_position = int(test.origin_position)
        prior_horizon_premium = float(_ordered_category(data, category).iloc[origin_position - horizon]["premium"])
        last_horizon_change = previous - prior_horizon_premium
        rows.append(
            {
                "category": category,
                "model_version": HORIZON_MODEL_VERSION,
                "horizon": horizon,
                "forecast_origin_tender": test.forecast_origin_tender,
                "next_tender_id": test.next_tender_id,
                "target_tender_id": test.target_tender_id,
                "origin_position": int(test.origin_position),
                "target_position": int(test.target_position),
                "display_date": test.display_date,
                "actual": actual,
                "previous_premium": previous,
                "structural": predicted,
                "persistence": previous,
                "historical_mean_drift": previous + historical_drift,
                "horizon_momentum": previous + last_horizon_change,
                "lower": predicted - radius if np.isfinite(radius) else np.nan,
                "upper": predicted + radius if np.isfinite(radius) else np.nan,
                "selected_alpha": alpha,
                "n_train": len(train),
                "timing_available": test.timing_available,
                "next_gap_days": test.next_gap_days,
                "horizon_calendar_days": test.horizon_calendar_days,
                "extended_gap_count": test.extended_gap_count,
            }
        )
        residual_records.append((int(test.target_position), abs(actual - predicted)))
    return pd.DataFrame(rows)


def _probabilities(possible_changes: np.ndarray, category: str, smoothing: float = 1.0) -> dict[str, float]:
    band = stay_band_for(category)
    counts = {label: smoothing for label in DIRECTION_LABELS}
    for value in possible_changes:
        counts[direction_label(float(value), band)] += 1.0
    total = sum(counts.values())
    return {label: counts[label] / total for label in DIRECTION_LABELS}


def add_horizon_probabilities(backtest: pd.DataFrame, min_calibration: int = 20) -> pd.DataFrame:
    residual_records: list[tuple[int, float]] = []
    records: list[dict] = []
    category = str(backtest.iloc[0]["category"])
    band = stay_band_for(category)
    for row in backtest.itertuples(index=False):
        predicted_change = float(row.structural - row.previous_premium)
        actual_change = float(row.actual - row.previous_premium)
        record = row._asdict()
        available_residuals = [
            residual
            for target_position, residual in residual_records
            if target_position <= int(row.origin_position)
        ]
        if len(available_residuals) >= min_calibration:
            probabilities = _probabilities(
                predicted_change + np.asarray(available_residuals), category
            )
            actual_direction = direction_label(actual_change, band)
            predicted_direction = max(DIRECTION_LABELS, key=probabilities.get)
            record.update(
                {
                    "actual_direction": actual_direction,
                    "predicted_direction": predicted_direction,
                    "probability_decrease": probabilities["Decrease"],
                    "probability_stay": probabilities["Stay"],
                    "probability_increase": probabilities["Increase"],
                    "brier_score": sum((probabilities[label] - float(label == actual_direction)) ** 2 for label in DIRECTION_LABELS),
                }
            )
        records.append(record)
        residual_records.append(
            (int(row.target_position), float(row.actual - row.structural))
        )
    return pd.DataFrame(records)


def summarize_horizon(backtest: pd.DataFrame) -> pd.DataFrame:
    models = ("structural", "persistence", "historical_mean_drift", "horizon_momentum")
    category = str(backtest.iloc[0]["category"])
    band = stay_band_for(category)
    actual_direction = backtest.apply(lambda row: direction_label(row.actual - row.previous_premium, band), axis=1)
    rows = []
    for model in models:
        predicted_direction = backtest.apply(lambda row: direction_label(row[model] - row.previous_premium, band), axis=1)
        calibrated = backtest.dropna(subset=["lower", "upper"])
        rows.append(
            {
                "category": category,
                "horizon": int(backtest.iloc[0]["horizon"]),
                "model": model,
                "n": len(backtest),
                "MAE": mean_absolute_error(backtest["actual"], backtest[model]),
                "RMSE": mean_squared_error(backtest["actual"], backtest[model]) ** 0.5,
                "three_way_accuracy": float((actual_direction == predicted_direction).mean()),
                "interval_coverage": float(((calibrated.actual >= calibrated.lower) & (calibrated.actual <= calibrated.upper)).mean()) if model == "structural" and len(calibrated) else np.nan,
            }
        )
    result = pd.DataFrame(rows)
    structural_mae = float(result.loc[result.model.eq("structural"), "MAE"].iloc[0])
    naive = result[~result.model.eq("structural")].sort_values("MAE").iloc[0]
    result["best_naive"] = str(naive.model)
    result["MAE_improvement_vs_best_naive"] = (float(naive.MAE) - structural_mae) / float(naive.MAE)
    return result


@dataclass(frozen=True)
class HorizonForecast:
    category: str
    horizon: int
    target_tender_id: str
    predicted_premium: float
    predicted_change: float
    lower: float
    upper: float
    probabilities: dict[str, float]
    predicted_direction: str
    calendar_days: float
    extended_gap_count: int
    selected_alpha: float


def _future_tender_sequence(data: pd.DataFrame, count: int) -> list[tuple[pd.Timestamp, int, str]]:
    latest = data.sort_values(["month", "bidding_no"]).iloc[-1]
    month = pd.Timestamp(latest["month"])
    bidding_no = int(latest["bidding_no"])
    result = []
    for _ in range(count):
        if bidding_no == 1:
            bidding_no = 2
        else:
            month = month + pd.offsets.MonthBegin(1)
            bidding_no = 1
        result.append((month, bidding_no, f"{month:%Y-%m}-{bidding_no}"))
    return result


def forecast_horizon(
    data: pd.DataFrame,
    category: str,
    schedule: pd.DataFrame,
    horizon: int,
    backtest: pd.DataFrame,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    inner_splits: int = 4,
) -> HorizonForecast:
    """Fit the direct horizon model through the latest completed exercise."""
    training = build_horizon_frame(data, category, schedule, horizon)
    columns = horizon_feature_columns(training)
    alpha = _select_alpha(training, columns, alphas, inner_splits)
    model = _pipeline(alpha)
    model.fit(training[columns], training["target_change"])

    ordered = data.sort_values(["month", "bidding_no"])
    latest_id = str(ordered.iloc[-1]["tender_id"])
    latest_rows = ordered[ordered["tender_id"].eq(latest_id)].copy()
    future = _future_tender_sequence(ordered, max(HORIZONS))
    synthetic_rows = []
    for month, bidding_no, tender_id in future:
        synthetic = latest_rows.copy()
        synthetic["month"] = month
        synthetic["bidding_no"] = bidding_no
        synthetic["tender_id"] = tender_id
        synthetic["display_date"] = month + pd.to_timedelta((bidding_no - 1) * 14, unit="D")
        synthetic_rows.append(synthetic)
    augmented = pd.concat([ordered, *synthetic_rows], ignore_index=True)
    next_id = future[0][2]
    target_id = future[horizon - 1][2]
    live = build_feature_frame(augmented, category)
    live = live[live["tender_id"].eq(next_id)].iloc[[0]].copy()

    calendar = prepare_tender_calendar(schedule)
    timing = calendar.set_index("tender_id")
    origin_close = timing.at[latest_id, "exercise_end_at"]
    next_close = timing.at[next_id, "exercise_end_at"]
    target_close = timing.at[target_id, "exercise_end_at"]
    next_gap_days = float((next_close - origin_close).total_seconds() / 86_400)
    horizon_days = float((target_close - origin_close).total_seconds() / 86_400)
    path_ids = [entry[2] for entry in future[:horizon]]
    path_closes = [origin_close, *[timing.at[item, "exercise_end_at"] for item in path_ids]]
    extended_count = int(
        sum((later - earlier).total_seconds() / 86_400 >= 19 for earlier, later in zip(path_closes, path_closes[1:]))
    )
    ordered_category = _ordered_category(data, category)
    prior_id = str(ordered_category.iloc[-2]["tender_id"])
    prior_close = timing.at[prior_id, "exercise_end_at"]
    prior_gap_days = float((origin_close - prior_close).total_seconds() / 86_400)
    live["forecast_origin_tender"] = latest_id
    live["target_tender_id"] = target_id
    live["origin_position"] = int(ordered_category.iloc[-1]["position"])
    live["target_position"] = live["origin_position"] + horizon
    live["horizon"] = horizon
    live["timing_available"] = 1.0
    live["next_gap_days"] = next_gap_days
    live["next_gap_weeks"] = next_gap_days / 7.0
    live["next_extended_gap"] = float(next_gap_days >= 19)
    live["horizon_calendar_days"] = horizon_days
    live["horizon_calendar_weeks"] = horizon_days / 7.0
    live["extended_gap_count"] = float(extended_count)
    live["announced_quota_per_week"] = live["announced_quota"] / (next_gap_days / 7.0)
    live["bids_per_week_lag1"] = float(ordered_category.iloc[-1]["bids_received"]) / (prior_gap_days / 7.0)

    predicted_change = float(model.predict(live[columns])[0])
    previous = float(ordered_category.iloc[-1]["premium"])
    residuals = (backtest["actual"] - backtest["structural"]).dropna().to_numpy(dtype=float)
    probabilities = _probabilities(predicted_change + residuals, category)
    radius = _conformal_radius(np.abs(residuals).tolist(), 0.80)
    return HorizonForecast(
        category=category,
        horizon=horizon,
        target_tender_id=target_id,
        predicted_premium=previous + predicted_change,
        predicted_change=predicted_change,
        lower=previous + predicted_change - radius,
        upper=previous + predicted_change + radius,
        probabilities=probabilities,
        predicted_direction=max(DIRECTION_LABELS, key=probabilities.get),
        calendar_days=horizon_days,
        extended_gap_count=extended_count,
        selected_alpha=alpha,
    )
