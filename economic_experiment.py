"""Paired evaluation of structural versus structural-plus-economy forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


def pair_economic_backtests(structural: pd.DataFrame, augmented: pd.DataFrame) -> pd.DataFrame:
    """Pair forecasts at identical tender origins and retain audit columns."""
    left = structural.rename(
        columns={"structural": "structural", "lower": "structural_lower", "upper": "structural_upper"}
    )
    right = augmented[
        ["tender_id", "structural", "lower", "upper", "selected_alpha", "model_version"]
    ].rename(
        columns={
            "structural": "structural_plus_economy",
            "lower": "economy_lower",
            "upper": "economy_upper",
            "selected_alpha": "economy_selected_alpha",
            "model_version": "economy_model_version",
        }
    )
    paired = left.merge(right, on="tender_id", how="inner", validate="one_to_one")
    if len(paired) != len(structural) or len(paired) != len(augmented):
        raise ValueError("Structural and economy back-tests do not cover identical tender origins")
    return paired


def summarize_economic_uplift(backtest: pd.DataFrame) -> pd.DataFrame:
    """Report paired accuracy and interval metrics without claiming calibration."""
    if backtest.empty:
        raise ValueError("Cannot summarize an empty economic back-test")
    actual_direction = np.sign(backtest["actual"] - backtest["previous_premium"])
    rows = []
    for model, lower, upper in (
        ("structural", "structural_lower", "structural_upper"),
        ("structural_plus_economy", "economy_lower", "economy_upper"),
        ("persistence", None, None),
    ):
        prediction = backtest[model]
        calibrated = backtest.dropna(subset=[lower, upper]) if lower else pd.DataFrame()
        covered = (
            (calibrated["actual"] >= calibrated[lower])
            & (calibrated["actual"] <= calibrated[upper])
            if lower
            else pd.Series(dtype=bool)
        )
        rows.append({
            "category": backtest.iloc[0]["category"],
            "economy_model_version": backtest.iloc[0]["economy_model_version"],
            "model": model,
            "observations": len(backtest),
            "MAE": mean_absolute_error(backtest["actual"], prediction),
            "RMSE": mean_squared_error(backtest["actual"], prediction) ** 0.5,
            "direction_accuracy": float(
                (actual_direction == np.sign(prediction - backtest["previous_premium"])).mean()
            ),
            "interval_coverage": float(covered.mean()) if len(covered) else np.nan,
            "mean_interval_width": float((calibrated[upper] - calibrated[lower]).mean())
            if lower and len(calibrated)
            else np.nan,
        })
    result = pd.DataFrame(rows)
    base = result[result["model"].eq("structural")].iloc[0]
    result["MAE_improvement_vs_structural"] = (base.MAE - result.MAE) / base.MAE
    result["RMSE_improvement_vs_structural"] = (base.RMSE - result.RMSE) / base.RMSE
    return result
