"""Run and persist the structural-versus-dealer incremental-value experiment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import prepare_coe_data, walk_forward_backtest
from dealer_experiment import MODEL_VERSION as DEALER_MODEL_VERSION
from dealer_experiment import summarize_dealer_uplift, walk_forward_dealer_uplift
from dealer_signals import build_tender_dealer_features, validate_dealer_observations


DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    observations, errors = validate_dealer_observations(
        pd.read_csv(ROOT / "data" / "dealer_observations_sgcarmart_2024_2026.csv")
    )
    if errors:
        raise ValueError("Dealer observations failed validation: " + "; ".join(errors))
    schedule = pd.read_csv(ROOT / "data" / "tender_schedule_2024_2026.csv")
    response = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--retry-delay", "2", URL],
        check=True,
        capture_output=True,
        text=True,
    )
    coe = prepare_coe_data(json.loads(response.stdout)["result"]["records"])

    prediction_frames = []
    metric_frames = []
    for category in ("Category A", "Category B"):
        category_schedule = schedule[schedule["category"].eq(category)]
        features = build_tender_dealer_features(observations, category_schedule, lookback_days=35)
        structural = walk_forward_backtest(coe, category)
        predictions = walk_forward_dealer_uplift(structural, features, min_train=12)
        if predictions.empty:
            continue
        predictions["category"] = category
        metrics = summarize_dealer_uplift(predictions).reset_index()
        metrics.insert(0, "category", category)
        metrics.insert(1, "dealer_model_version", DEALER_MODEL_VERSION)
        prediction_frames.append(predictions)
        metric_frames.append(metrics)
        print(f"\n{category} ({len(predictions)} dealer-test forecasts)")
        print(metrics.to_string(index=False))

    predictions = pd.concat(prediction_frames, ignore_index=True)
    metrics = pd.concat(metric_frames, ignore_index=True)
    predictions.to_csv(ROOT / "data" / "dealer_backtest_predictions.csv", index=False)
    metrics.to_csv(ROOT / "data" / "dealer_backtest_metrics.csv", index=False)


if __name__ == "__main__":
    main()
