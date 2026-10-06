"""Validate persisted v0.12 calendar and multi-horizon audit artifacts."""

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    schedule = pd.read_csv(ROOT / "data" / "tender_schedule_2017_2026.csv")
    predictions = pd.read_csv(ROOT / "data" / "horizon_backtest_predictions.csv")
    metrics = pd.read_csv(ROOT / "data" / "horizon_backtest_metrics.csv")
    forecasts = pd.read_csv(ROOT / "data" / "horizon_live_forecasts.csv")
    alignment = pd.read_csv(ROOT / "data" / "dealer_package_horizon_alignment.csv")
    economy_metrics = pd.read_csv(ROOT / "data" / "horizon_economic_metrics.csv")
    dealer_metrics = pd.read_csv(ROOT / "data" / "horizon_dealer_metrics.csv")
    economy_predictions = pd.read_csv(ROOT / "data" / "horizon_economic_predictions.csv")
    dealer_predictions = pd.read_csv(ROOT / "data" / "horizon_dealer_predictions.csv")
    expected = {(category, horizon) for category in ("Category A", "Category B", "Category D") for horizon in (1, 2, 4, 6)}
    assert set(map(tuple, forecasts[["category", "horizon"]].to_records(index=False))) == expected
    assert set(map(tuple, predictions[["category", "horizon"]].drop_duplicates().to_records(index=False))) == expected
    assert set(metrics["model"]) == {"structural", "persistence", "historical_mean_drift", "horizon_momentum"}
    probability_rows = predictions.dropna(subset=["probability_decrease", "probability_stay", "probability_increase"])
    probability_sum = probability_rows[["probability_decrease", "probability_stay", "probability_increase"]].sum(axis=1)
    assert np.allclose(probability_sum, 1.0)
    for _, group in predictions.groupby(["category", "horizon"], sort=False):
        earlier_targets: list[int] = []
        for row in group.itertuples(index=False):
            available = sum(target <= int(row.origin_position) for target in earlier_targets)
            if pd.notna(row.probability_stay) or pd.notna(row.lower):
                assert available >= 20
            earlier_targets.append(int(row.target_position))
    assert predictions["timing_available"].eq(1).all()
    assert schedule["source_url"].str.startswith("https://onemotoring.lta.gov.sg/").all()
    assert schedule["tender_id"].nunique() == 240
    assert alignment["source_url"].notna().all()
    assert set(economy_metrics["model"]) == {
        "structural",
        "structural_plus_economy",
        "structural_plus_economy_financing",
    }
    assert set(map(tuple, economy_metrics[["category", "horizon"]].drop_duplicates().to_records(index=False))) == expected
    expected_dealer = {
        (category, horizon)
        for category in ("Category A", "Category B")
        for horizon in (1, 2, 4, 6)
    }
    assert set(map(tuple, dealer_metrics[["category", "horizon"]].drop_duplicates().to_records(index=False))) == expected_dealer
    assert set(dealer_metrics["model"]) == {"structural", "structural_plus_dealer"}
    assert economy_predictions["target_position"].gt(economy_predictions["origin_position"]).all()
    assert dealer_predictions["target_position"].gt(dealer_predictions["origin_position"]).all()
    print(
        f"validated {len(predictions):,} horizon forecasts, {schedule['tender_id'].nunique()} official calendar exercises "
        f"and {len(alignment):,} dealer-package mappings; signal experiments cover "
        f"{len(economy_predictions):,} economy and {len(dealer_predictions):,} dealer paired rows"
    )


if __name__ == "__main__":
    main()
