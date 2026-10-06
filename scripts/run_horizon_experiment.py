"""Build v0.12 direct multi-horizon forecasts and persisted audit outputs."""

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import CATEGORIES, prepare_coe_data
from horizon_model import (
    HORIZONS,
    add_horizon_probabilities,
    forecast_horizon,
    summarize_horizon,
    walk_forward_horizon_backtest,
)
from tender_timing import load_tender_schedule


ROOT = Path(__file__).resolve().parents[1]
DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


def main() -> None:
    response = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--retry-delay", "2", URL],
        check=True,
        capture_output=True,
        text=True,
    )
    data = prepare_coe_data(json.loads(response.stdout)["result"]["records"])
    schedule = load_tender_schedule(ROOT / "data" / "tender_schedule_2017_2026.csv")
    predictions = []
    metrics = []
    forecasts = []
    gap_metrics = []
    for category in CATEGORIES:
        for horizon in HORIZONS:
            backtest = walk_forward_horizon_backtest(data, category, schedule, horizon)
            enriched = add_horizon_probabilities(backtest)
            predictions.append(enriched)
            for segment, sample in (
                ("regular_path", enriched[enriched["extended_gap_count"].eq(0)]),
                ("contains_extended_gap", enriched[enriched["extended_gap_count"].gt(0)]),
            ):
                if sample.empty:
                    continue
                gap_metrics.append(
                    {
                        "category": category,
                        "horizon": horizon,
                        "segment": segment,
                        "n": len(sample),
                        "MAE": mean_absolute_error(sample["actual"], sample["structural"]),
                        "RMSE": mean_squared_error(sample["actual"], sample["structural"]) ** 0.5,
                        "mean_calendar_days": sample["horizon_calendar_days"].mean(),
                    }
                )
            summary = summarize_horizon(backtest)
            probability_rows = enriched.dropna(subset=["brier_score"])
            summary["probability_n"] = len(probability_rows)
            summary["Brier"] = float(probability_rows["brier_score"].mean())
            metrics.append(summary)
            live = forecast_horizon(data, category, schedule, horizon, backtest)
            forecasts.append(
                {
                    "category": live.category,
                    "horizon": live.horizon,
                    "target_tender_id": live.target_tender_id,
                    "predicted_premium": live.predicted_premium,
                    "predicted_change": live.predicted_change,
                    "lower": live.lower,
                    "upper": live.upper,
                    "predicted_direction": live.predicted_direction,
                    "probability_decrease": live.probabilities["Decrease"],
                    "probability_stay": live.probabilities["Stay"],
                    "probability_increase": live.probabilities["Increase"],
                    "calendar_days": live.calendar_days,
                    "extended_gap_count": live.extended_gap_count,
                    "selected_alpha": live.selected_alpha,
                }
            )
            structural = summary[summary.model.eq("structural")].iloc[0]
            print(
                f"{category} h={horizon}: n={len(backtest)}, MAE={structural.MAE:,.0f}, "
                f"vs naive={structural.MAE_improvement_vs_best_naive:+.1%}, "
                f"three-way={structural.three_way_accuracy:.1%}"
            )
    pd.concat(predictions, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_backtest_predictions.csv", index=False
    )
    pd.concat(metrics, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_backtest_metrics.csv", index=False
    )
    pd.DataFrame(forecasts).to_csv(ROOT / "data" / "horizon_live_forecasts.csv", index=False)
    pd.DataFrame(gap_metrics).to_csv(ROOT / "data" / "horizon_gap_metrics.csv", index=False)


if __name__ == "__main__":
    main()
