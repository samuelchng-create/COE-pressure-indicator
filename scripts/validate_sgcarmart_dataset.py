"""Fail-fast checks for the published SGCarMart research dataset."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dealer_signals import validate_dealer_observations


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    observations = pd.read_csv(ROOT / "data" / "dealer_observations_sgcarmart_2024_2026.csv")
    validated, errors = validate_dealer_observations(observations)
    if errors:
        raise AssertionError("; ".join(errors))
    assert validated["observation_id"].is_unique
    assert validated["category"].isin(["Category A", "Category B"]).all()
    assert validated["source_url"].str.startswith("https://media.i-sgcm.com/").all()
    assert validated["market_share_weight"].between(0, 1).all()
    assert (validated["available_at"] <= validated["retrieved_at"]).all()
    assert validated["advertised_price"].between(80_000, 1_500_000).all()
    advertised_rates = validated["finance_rate_pct"].dropna()
    assert len(advertised_rates) == 135
    assert advertised_rates.between(0.1, 15).all()
    assert len(validated) == 997
    assert set(validated["brand"]) == {
        "BYD", "GAC", "Honda", "Hyundai", "Kia", "Mazda", "Nissan", "Subaru", "Toyota"
    }

    manifest = pd.read_csv(ROOT / "data" / "sgcarmart_source_manifest_2024_2026.csv")
    assert not manifest.duplicated(["dealer_id", "document_date"]).any()
    assert manifest["http_status"].astype(str).eq("200").all()
    assert manifest["sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert manifest["error"].eq("none").all()
    assert manifest["brand"].nunique() == 12
    assert len(manifest) == 863

    metrics = pd.read_csv(ROOT / "data" / "dealer_backtest_metrics.csv")
    assert set(metrics["category"]) == {"Category A", "Category B"}
    assert set(metrics["model"]) == {"structural", "structural_plus_dealer", "persistence"}
    assert metrics["dealer_model_version"].str.contains("post-2015", regex=False).all()
    assert len(metrics) == 6
    print(
        f"validated {len(validated)} dealer observations, {len(manifest)} source PDFs and {len(metrics)} metric rows"
    )


if __name__ == "__main__":
    main()
