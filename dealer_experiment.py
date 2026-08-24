"""Prequential test of incremental dealer-signal value over structural forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


MODEL_VERSION = "v0.6-dealer-residual-ridge-expanded-brands-post-2015-1"
DEALER_FEATURE_COLUMNS = [
    "dealer_observation_count",
    "dealer_brand_count",
    "weighted_advertised_price",
    "weighted_price_change",
    "weighted_coe_rebate",
    "weighted_total_incentive",
    "weighted_guaranteed_coe_share",
    "weighted_promotion_deadline_days",
    "weighted_active_roadshow_share",
]


def _model(alpha: float):
    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        StandardScaler(),
        Ridge(alpha=alpha),
    )


def _select_alpha(train: pd.DataFrame, alphas: tuple[float, ...]) -> float:
    n_splits = min(3, max(2, len(train) // 8))
    splitter = TimeSeriesSplit(n_splits=n_splits)
    scores = {alpha: [] for alpha in alphas}
    for train_index, validation_index in splitter.split(train):
        inner_train = train.iloc[train_index]
        validation = train.iloc[validation_index]
        for alpha in alphas:
            model = _model(alpha)
            model.fit(inner_train[DEALER_FEATURE_COLUMNS], inner_train["structural_residual"])
            prediction = model.predict(validation[DEALER_FEATURE_COLUMNS])
            scores[alpha].append(mean_absolute_error(validation["structural_residual"], prediction))
    return min(alphas, key=lambda alpha: (float(np.mean(scores[alpha])), alpha))


def walk_forward_dealer_uplift(
    structural_backtest: pd.DataFrame,
    dealer_features: pd.DataFrame,
    min_train: int = 12,
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
) -> pd.DataFrame:
    """Predict structural residuals using only earlier dealer-feature rows."""
    merged = structural_backtest.merge(
        dealer_features.drop(columns=["category", "forecast_cutoff_at"], errors="ignore"),
        on="tender_id",
        how="inner",
        validate="one_to_one",
    ).sort_values("tender_id")
    merged = merged[merged["dealer_observation_count"].fillna(0) > 0].copy()
    merged["structural_residual"] = merged["actual"] - merged["structural"]
    if len(merged) <= min_train:
        return pd.DataFrame()
    rows = []
    prior_errors: list[float] = []
    for position in range(min_train, len(merged)):
        train = merged.iloc[:position]
        test = merged.iloc[[position]]
        alpha = _select_alpha(train, alphas)
        model = _model(alpha)
        model.fit(train[DEALER_FEATURE_COLUMNS], train["structural_residual"])
        residual_adjustment = float(model.predict(test[DEALER_FEATURE_COLUMNS])[0])
        combined = float(test.iloc[0]["structural"]) + residual_adjustment
        if len(prior_errors) >= 12:
            n = len(prior_errors)
            quantile = min(1.0, np.ceil((n + 1) * 0.80) / n)
            radius = float(np.quantile(np.asarray(prior_errors), quantile, method="higher"))
        else:
            radius = np.nan
        record = test.iloc[0].to_dict()
        record.update(
            {
                "dealer_model_version": MODEL_VERSION,
                "structural_plus_dealer": combined,
                "predicted_residual_adjustment": residual_adjustment,
                "dealer_lower": combined - radius if np.isfinite(radius) else np.nan,
                "dealer_upper": combined + radius if np.isfinite(radius) else np.nan,
                "dealer_selected_alpha": alpha,
                "dealer_n_train": len(train),
            }
        )
        rows.append(record)
        prior_errors.append(abs(float(test.iloc[0]["actual"]) - combined))
    return pd.DataFrame(rows)


def summarize_dealer_uplift(backtest: pd.DataFrame) -> pd.DataFrame:
    records = []
    actual_direction = np.sign(backtest["actual"] - backtest["previous_premium"])
    for model in ("structural", "structural_plus_dealer", "persistence"):
        prediction = backtest[model]
        record = {
                "model": model,
                "observations": len(backtest),
                "MAE": mean_absolute_error(backtest["actual"], prediction),
                "RMSE": mean_squared_error(backtest["actual"], prediction) ** 0.5,
                "direction_accuracy": float(
                    (actual_direction == np.sign(prediction - backtest["previous_premium"])).mean()
                ),
                "interval_coverage": np.nan,
                "mean_interval_width": np.nan,
            }
        if model == "structural":
            calibrated = backtest.dropna(subset=["lower", "upper"])
            record["interval_coverage"] = float(
                ((calibrated["actual"] >= calibrated["lower"]) & (calibrated["actual"] <= calibrated["upper"])).mean()
            ) if len(calibrated) else np.nan
            record["mean_interval_width"] = float((calibrated["upper"] - calibrated["lower"]).mean()) if len(calibrated) else np.nan
        elif model == "structural_plus_dealer":
            calibrated = backtest.dropna(subset=["dealer_lower", "dealer_upper"])
            record["interval_coverage"] = float(
                ((calibrated["actual"] >= calibrated["dealer_lower"]) & (calibrated["actual"] <= calibrated["dealer_upper"])).mean()
            ) if len(calibrated) else np.nan
            record["mean_interval_width"] = float((calibrated["dealer_upper"] - calibrated["dealer_lower"]).mean()) if len(calibrated) else np.nan
        records.append(record)
    result = pd.DataFrame(records).set_index("model")
    structural_mae = result.loc["structural", "MAE"]
    structural_rmse = result.loc["structural", "RMSE"]
    result["MAE_improvement_vs_structural"] = (structural_mae - result["MAE"]) / structural_mae
    result["RMSE_improvement_vs_structural"] = (structural_rmse - result["RMSE"]) / structural_rmse
    return result
