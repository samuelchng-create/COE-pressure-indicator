"""Run and persist the paired structural-versus-economy experiment."""

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import CATEGORIES, prepare_coe_data, walk_forward_backtest
from economic_experiment import add_financing_backtest, pair_economic_backtests, summarize_economic_uplift
from economic_features import ECONOMIC_CORE_FEATURE_COLUMNS, validate_economic_features


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
    coe = prepare_coe_data(json.loads(response.stdout)["result"]["records"])
    economic, errors = validate_economic_features(
        pd.read_csv(ROOT / "data" / "economic_financial_features.csv")
    )
    if errors:
        raise ValueError("; ".join(errors))

    predictions = []
    metrics = []
    for category in CATEGORIES:
        structural = walk_forward_backtest(coe, category)
        economy_core = walk_forward_backtest(
            coe,
            category,
            economic_features=economic,
            economic_feature_columns=ECONOMIC_CORE_FEATURE_COLUMNS,
        )
        financing = walk_forward_backtest(coe, category, economic_features=economic)
        paired = add_financing_backtest(
            pair_economic_backtests(structural, economy_core), financing
        )
        summary = summarize_economic_uplift(paired)
        predictions.append(paired)
        metrics.append(summary)
        combined = summary[summary["model"].eq("structural_plus_economy_financing")].iloc[0]
        print(
            f"{category}: {len(paired)} forecasts; financing MAE={combined.MAE:,.1f}; "
            f"vs structural={combined.MAE_improvement_vs_structural:+.2%}; "
            f"vs economy core={combined.MAE_improvement_vs_economy_core:+.2%}"
        )
    pd.concat(predictions, ignore_index=True).to_csv(
        ROOT / "data" / "economic_backtest_predictions.csv", index=False
    )
    pd.concat(metrics, ignore_index=True).to_csv(
        ROOT / "data" / "economic_backtest_metrics.csv", index=False
    )


if __name__ == "__main__":
    main()
