"""Validate the bundled economy/markets dataset and paired experiment outputs."""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economic_features import ECONOMIC_FEATURE_COLUMNS, validate_economic_features


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    features, errors = validate_economic_features(
        pd.read_csv(ROOT / "data" / "economic_financial_features.csv")
    )
    if errors:
        raise ValueError("; ".join(errors))
    manifest = pd.read_csv(ROOT / "data" / "economic_financial_source_manifest.csv")
    metrics = pd.read_csv(ROOT / "data" / "economic_backtest_metrics.csv")
    predictions = pd.read_csv(ROOT / "data" / "economic_backtest_predictions.csv")
    if set(metrics["category"]) != {"Category A", "Category B", "Category D"}:
        raise ValueError("metrics do not cover Categories A, B and D")
    if set(metrics["model"]) != {"structural", "structural_plus_economy", "persistence"}:
        raise ValueError("metrics do not contain the required paired models")
    if predictions.duplicated(["category", "tender_id"]).any():
        raise ValueError("predictions contain duplicate category/tender rows")
    expected_source_ids = {"DEXSIUS", "VIXCLS", "DGS10", "DCOILBRENTEU", "NASDAQCOM", "M015631", "M213781", "M182342"}
    if set(manifest["source_id"]) != expected_source_ids:
        raise ValueError("source manifest is incomplete")
    print(
        f"validated {len(features):,} tender rows, {len(ECONOMIC_FEATURE_COLUMNS)} features, "
        f"{len(predictions):,} paired forecasts and {len(manifest)} source series"
    )


if __name__ == "__main__":
    main()
