"""Run and persist the paired structural-versus-economy experiment."""

from pathlib import Path
import sys

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import CATEGORIES, prepare_coe_data, walk_forward_backtest
from economic_experiment import pair_economic_backtests, summarize_economic_uplift
from economic_features import validate_economic_features


ROOT = Path(__file__).resolve().parents[1]
DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


def main() -> None:
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    coe = prepare_coe_data(response.json()["result"]["records"])
    economic, errors = validate_economic_features(
        pd.read_csv(ROOT / "data" / "economic_financial_features.csv")
    )
    if errors:
        raise ValueError("; ".join(errors))

    predictions = []
    metrics = []
    for category in CATEGORIES:
        structural = walk_forward_backtest(coe, category)
        augmented = walk_forward_backtest(coe, category, economic_features=economic)
        paired = pair_economic_backtests(structural, augmented)
        summary = summarize_economic_uplift(paired)
        predictions.append(paired)
        metrics.append(summary)
        combined = summary[summary["model"].eq("structural_plus_economy")].iloc[0]
        print(
            f"{category}: {len(paired)} forecasts; economy MAE={combined.MAE:,.1f}; "
            f"improvement={combined.MAE_improvement_vs_structural:+.2%}"
        )
    pd.concat(predictions, ignore_index=True).to_csv(
        ROOT / "data" / "economic_backtest_predictions.csv", index=False
    )
    pd.concat(metrics, ignore_index=True).to_csv(
        ROOT / "data" / "economic_backtest_metrics.csv", index=False
    )


if __name__ == "__main__":
    main()
