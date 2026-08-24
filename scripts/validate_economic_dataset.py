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
    if set(metrics["model"]) != {
        "structural", "structural_plus_economy", "structural_plus_economy_financing", "persistence"
    }:
        raise ValueError("metrics do not contain the required paired models")
    if predictions.duplicated(["category", "tender_id"]).any():
        raise ValueError("predictions contain duplicate category/tender rows")
    if features.iloc[0]["tender_id"] != "2015-10-1":
        raise ValueError("economic feature history must begin at the October 2015 boundary")
    if not metrics["economy_model_version"].str.contains("post-2015", regex=False).all():
        raise ValueError("metrics are not labelled with the post-2015 model version")
    if (predictions["tender_id"].str.slice(0, 7) < "2015-10").any():
        raise ValueError("predictions contain pre-October-2015 tenders")
    expected_source_ids = {
        "DEXSIUS", "VIXCLS", "DGS10", "DCOILBRENTEU", "NASDAQCOM",
        "M015631", "M213781", "M182342", "MAS-MSB-VEHICLE-HP-3Y",
    }
    if set(manifest["source_id"]) != expected_source_ids:
        raise ValueError("source manifest is incomplete")
    print(
        f"validated {len(features):,} tender rows, {len(ECONOMIC_FEATURE_COLUMNS)} features, "
        f"{len(predictions):,} paired forecasts and {len(manifest)} source series"
    )


if __name__ == "__main__":
    main()
