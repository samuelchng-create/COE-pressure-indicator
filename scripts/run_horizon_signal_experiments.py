"""Run paired multi-horizon dealer and economy incremental-value experiments."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coe_model import CATEGORIES, direction_label, prepare_coe_data
from dealer_experiment import walk_forward_dealer_uplift
from dealer_signals import build_tender_dealer_features, validate_dealer_observations
from economic_features import (
    ECONOMIC_CORE_FEATURE_COLUMNS,
    ECONOMIC_FEATURE_COLUMNS,
    validate_economic_features,
)
from horizon_model import HORIZONS, stay_band_for, walk_forward_horizon_backtest
from tender_timing import load_tender_schedule


ROOT = Path(__file__).resolve().parents[1]
DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


def _metrics(
    frame: pd.DataFrame,
    models: tuple[tuple[str, str | None, str | None], ...],
    comparison_model: str,
) -> pd.DataFrame:
    """Summarize models over identical rows using the horizon-specific Stay band."""
    category = str(frame.iloc[0]["category"])
    band = stay_band_for(category)
    actual_direction = frame.apply(
        lambda row: direction_label(row.actual - row.previous_premium, band), axis=1
    )
    records = []
    for model, lower, upper in models:
        predicted_direction = frame.apply(
            lambda row: direction_label(row[model] - row.previous_premium, band), axis=1
        )
        calibrated = frame.dropna(subset=[lower, upper]) if lower and upper else pd.DataFrame()
        records.append(
            {
                "category": category,
                "horizon": int(frame.iloc[0]["horizon"]),
                "model": model,
                "n": len(frame),
                "MAE": mean_absolute_error(frame["actual"], frame[model]),
                "RMSE": mean_squared_error(frame["actual"], frame[model]) ** 0.5,
                "three_way_accuracy": float((actual_direction == predicted_direction).mean()),
                "interval_coverage": (
                    float(
                        (
                            (calibrated["actual"] >= calibrated[lower])
                            & (calibrated["actual"] <= calibrated[upper])
                        ).mean()
                    )
                    if len(calibrated)
                    else np.nan
                ),
            }
        )
    result = pd.DataFrame(records)
    comparison_mae = float(result.loc[result["model"].eq(comparison_model), "MAE"].iloc[0])
    comparison_rmse = float(result.loc[result["model"].eq(comparison_model), "RMSE"].iloc[0])
    result["comparison_model"] = comparison_model
    result["MAE_improvement_vs_comparison"] = (comparison_mae - result["MAE"]) / comparison_mae
    result["RMSE_improvement_vs_comparison"] = (comparison_rmse - result["RMSE"]) / comparison_rmse
    return result


def _pair_economy(
    structural: pd.DataFrame,
    economy: pd.DataFrame,
    financing: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["category", "horizon", "forecast_origin_tender", "next_tender_id", "target_tender_id"]
    paired = structural.rename(columns={"lower": "structural_lower", "upper": "structural_upper"})
    for candidate, name in ((economy, "economy"), (financing, "economy_financing")):
        right = candidate[
            [*keys, "structural", "lower", "upper", "selected_alpha", "model_version"]
        ].rename(
            columns={
                "structural": f"structural_plus_{name}",
                "lower": f"{name}_lower",
                "upper": f"{name}_upper",
                "selected_alpha": f"{name}_selected_alpha",
                "model_version": f"{name}_model_version",
            }
        )
        paired = paired.merge(right, on=keys, how="inner", validate="one_to_one")
    if len(paired) != len(structural) or len(paired) != len(economy) or len(paired) != len(financing):
        raise ValueError("Horizon economy variants do not cover identical forecast origins")
    return paired


def _dealer_experiment(
    structural: pd.DataFrame,
    dealer_features: pd.DataFrame,
) -> pd.DataFrame:
    # Dealer features are frozen at the opening of the first exercise after the
    # forecast origin, regardless of the terminal horizon being evaluated.
    candidate = structural.copy()
    candidate["tender_id"] = candidate["next_tender_id"]
    return walk_forward_dealer_uplift(candidate, dealer_features, min_train=12)


def main() -> None:
    response = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--retry-delay", "2", URL],
        check=True,
        capture_output=True,
        text=True,
    )
    coe = prepare_coe_data(json.loads(response.stdout)["result"]["records"])
    schedule = load_tender_schedule(ROOT / "data" / "tender_schedule_2017_2026.csv")
    economic, economic_errors = validate_economic_features(
        pd.read_csv(ROOT / "data" / "economic_financial_features.csv")
    )
    if economic_errors:
        raise ValueError("; ".join(economic_errors))
    observations, dealer_errors = validate_dealer_observations(
        pd.read_csv(ROOT / "data" / "dealer_observations_sgcarmart_2024_2026.csv")
    )
    if dealer_errors:
        raise ValueError("; ".join(dealer_errors))

    economy_predictions = []
    economy_metrics = []
    dealer_predictions = []
    dealer_metrics = []
    for category in CATEGORIES:
        if category != "Category D":
            dealer_features = build_tender_dealer_features(
                observations,
                schedule[schedule["category"].eq(category)],
                lookback_days=35,
            )
        for horizon in HORIZONS:
            structural = walk_forward_horizon_backtest(coe, category, schedule, horizon)
            economy = walk_forward_horizon_backtest(
                coe,
                category,
                schedule,
                horizon,
                economic_features=economic,
                economic_feature_columns=ECONOMIC_CORE_FEATURE_COLUMNS,
            )
            financing = walk_forward_horizon_backtest(
                coe,
                category,
                schedule,
                horizon,
                economic_features=economic,
                economic_feature_columns=ECONOMIC_FEATURE_COLUMNS,
            )
            paired = _pair_economy(structural, economy, financing)
            economy_predictions.append(paired)
            economy_summary = _metrics(
                paired,
                (
                    ("structural", "structural_lower", "structural_upper"),
                    ("structural_plus_economy", "economy_lower", "economy_upper"),
                    (
                        "structural_plus_economy_financing",
                        "economy_financing_lower",
                        "economy_financing_upper",
                    ),
                ),
                comparison_model="structural",
            )
            economy_metrics.append(economy_summary)

            if category != "Category D":
                dealer = _dealer_experiment(structural, dealer_features)
                if not dealer.empty:
                    dealer_predictions.append(dealer)
                    dealer_metrics.append(
                        _metrics(
                            dealer,
                            (
                                ("structural", "lower", "upper"),
                                ("structural_plus_dealer", "dealer_lower", "dealer_upper"),
                            ),
                            comparison_model="structural",
                        )
                    )

    pd.concat(economy_predictions, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_economic_predictions.csv", index=False
    )
    pd.concat(economy_metrics, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_economic_metrics.csv", index=False
    )
    pd.concat(dealer_predictions, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_dealer_predictions.csv", index=False
    )
    pd.concat(dealer_metrics, ignore_index=True).to_csv(
        ROOT / "data" / "horizon_dealer_metrics.csv", index=False
    )

    print("Multi-horizon economy results")
    economy_result = pd.concat(economy_metrics, ignore_index=True)
    print(
        economy_result[economy_result["model"].ne("structural")][
            ["category", "horizon", "model", "n", "MAE_improvement_vs_comparison"]
        ].to_string(index=False)
    )
    print("\nMulti-horizon dealer results")
    dealer_result = pd.concat(dealer_metrics, ignore_index=True)
    print(
        dealer_result[dealer_result["model"].eq("structural_plus_dealer")][
            ["category", "horizon", "n", "MAE_improvement_vs_comparison"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
