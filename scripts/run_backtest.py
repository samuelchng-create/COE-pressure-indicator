"""Run the v0.5 post-October-2015 back-test against official data."""

from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import CATEGORIES, prepare_coe_data, summarize_backtest, walk_forward_backtest


DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


def main() -> None:
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    data = prepare_coe_data(response.json()["result"]["records"])
    for category in CATEGORIES:
        summary = summarize_backtest(walk_forward_backtest(data, category))
        print(f"\n{category} ({summary.observations} forecasts)")
        print(summary.metrics.round({"MAE": 1, "RMSE": 1, "direction_accuracy": 3}).to_string())
        print(
            f"best_naive={summary.best_naive}; "
            f"MAE improvement={summary.mae_improvement_vs_best_naive:+.2%}; "
            f"RMSE improvement={summary.rmse_improvement_vs_best_naive:+.2%}; "
            f"80% interval coverage={summary.interval_coverage:.2%}"
        )


if __name__ == "__main__":
    main()
