from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from coe_model import (
    ANALYSIS_START,
    CATEGORIES,
    FEATURE_AVAILABILITY,
    MODEL_VERSION,
    prepare_coe_data,
    summarize_backtest,
    walk_forward_backtest,
)
from direction_probabilities import (
    DIRECTION_PROBABILITY_VERSION,
    forecast_next_tender,
    prequential_direction_probabilities,
)
from dealer_signals import empty_dealer_template, validate_dealer_observations
from economic_features import (
    ECONOMIC_FEATURE_AVAILABILITY,
    ECONOMIC_FEATURE_COLUMNS,
    ECONOMIC_MODEL_VERSION,
    validate_economic_features,
)


st.set_page_config(page_title="Singapore COE Pressure Indicator", layout="wide")
st.title("Singapore COE Pressure Indicator")
st.caption(
    f"v0.9 three-way next-exercise outlook + indicator tooltips • "
    f"{MODEL_VERSION} • experimental, uncalibrated public-interest analysis"
)

METRIC_HELP = {
    "latest_coe": "The winning COE premium in the latest completed tender. The change shown below it is versus the previous tender.",
    "bid_quota": "Bids received divided by the available quota in the completed tender. Above 1.00 means demand exceeded supply.",
    "bids_received": "The total number of bids received in the latest completed tender.",
    "quota": "The number of COEs available for this category in the latest completed tender.",
    "direction_accuracy": "The percentage of one-tender-ahead forecasts that correctly predicted whether the COE premium would rise or fall.",
    "mae": "Mean Absolute Error: the average size of the forecast miss, ignoring whether it was too high or too low. Lower is better.",
    "rmse": "Root Mean Squared Error: a forecast-error measure that penalises large misses more heavily than MAE. Lower is better.",
    "interval_coverage": "The share of actual premiums that fell inside the model's nominal 80% forecast interval. It is historical coverage, not a guarantee.",
    "best_naive": "The simple baseline with the lowest historical MAE: persistence, historical mean drift, or the premium from two tenders earlier.",
    "mae_improvement_naive": "Percentage reduction in MAE versus the best naïve baseline. Positive means the structural model performed better.",
    "rmse_improvement_naive": "Percentage reduction in RMSE versus the best naïve baseline. Positive means the structural model performed better.",
    "source_pdfs": "Dated SGCarMart price-list PDFs retained in the auditable source corpus.",
    "requested_groups": "The number of user-requested brand groups included in the dealer-data coverage audit.",
    "source_marques": "Distinct SGCarMart marques represented in the source PDFs. Grouped brands retain their original marque identity for audit.",
    "eligible_groups": "Brand groups with at least one observation meeting the strict model rules: explicit Cat A/B label and an extracted advertised price.",
    "category_rows": "Dealer observations that passed validation and are eligible for this COE category's experiment.",
    "forecast_count": "Paired one-tender-ahead out-of-sample forecasts used to compare models at identical historical cutoffs.",
    "combined_mae": "MAE for the structural model after adding eligible dealer signals. Lower is better.",
    "mae_vs_structural": "Percentage reduction in MAE versus the structural-only model. Positive means improvement; negative means deterioration.",
    "sgd_usd": "Singapore dollars required to buy one US dollar. A higher value means a weaker Singapore dollar.",
    "vix": "The CBOE Volatility Index, a market measure of expected US equity volatility. Higher values indicate greater market uncertainty.",
    "us_10y": "Yield on the 10-year US Treasury bond, used as a global long-term interest-rate indicator.",
    "brent": "Brent crude-oil price per barrel in US dollars, used as an energy-cost and inflation indicator.",
    "nasdaq_1m": "Percentage change in the Nasdaq Composite over approximately 21 trading days. Positive values indicate a rise.",
    "gdp_yoy": "Year-on-year percentage change in Singapore's inflation-adjusted economic output.",
    "cpi_yoy": "Year-on-year percentage change in Singapore's Consumer Price Index, a broad measure of consumer inflation.",
    "unemployment": "Singapore's seasonally adjusted unemployment rate.",
    "vehicle_hp": "MAS average interest rate for a three-year hire-purchase loan on a new motor vehicle. It is a market-wide proxy, not category-specific.",
    "vehicle_rate_age": "Days between the forecast cutoff and the latest available MAS vehicle-loan-rate observation. Larger values mean the rate is staler.",
    "financing_mae": "MAE for the structural model augmented with economic, market and vehicle-financing variables. Lower is better.",
    "mae_vs_economy": "Percentage reduction in MAE versus the economy model without financing variables. Positive means improvement.",
    "predicted_outcome": "The outcome with the highest estimated probability: Increase above S$1,000, Stay within ±S$1,000, or Decrease below −S$1,000.",
    "outcome_probability": "Estimated chance of this outcome, based on the structural point forecast plus only earlier out-of-sample forecast errors. Experimental, not prospectively calibrated.",
    "predicted_change": "The structural model's point estimate for the change from the latest completed COE premium to the next exercise.",
    "probability_backtests": "Historical one-step probability forecasts made after at least 20 earlier out-of-sample errors were available.",
    "brier_score": "Multiclass Brier score: the average squared difference between predicted probabilities and actual outcomes. Lower is better; zero is perfect.",
    "brier_improvement": "Percentage reduction in Brier score versus probabilities based only on earlier outcome frequencies. Positive means better probability accuracy.",
    "three_way_accuracy": "Percentage of back-tested tenders where the highest-probability outcome matched Increase, Stay or Decrease under the ±S$1,000 rule.",
}

REQUESTED_BRAND_GROUPS = {
    "BYD": ("BYD",),
    "Toyota / Lexus": ("Toyota", "Lexus"),
    "Tesla": ("Tesla",),
    "Mercedes-Benz": ("Mercedes-Benz",),
    "BMW": ("BMW",),
    "Chery / Omoda / Jaecoo": ("Omoda", "Jaecoo"),
    "GAC / Aion": ("GAC", "Aion"),
    "MG": ("MG",),
    "Honda": ("Honda",),
    "Nissan": ("Nissan",),
    "Kia": ("Kia",),
    "ZEEKR": ("ZEEKR",),
    "XPENG": ("XPENG",),
    "Hyundai": ("Hyundai",),
    "Audi": ("Audi",),
    "Suzuki": ("Suzuki",),
    "Dongfeng": ("Dongfeng",),
    "Porsche": ("Porsche",),
    "Volvo": ("Volvo",),
    "Mazda": ("Mazda",),
}
SOURCE_TO_BRAND_GROUP = {
    source: group
    for group, sources in REQUESTED_BRAND_GROUPS.items()
    for source in sources
}


def format_signed_sgd(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}S${abs(value):,.0f}"

DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


@st.cache_data(ttl=3600)
def load_coe(cache_version: str) -> pd.DataFrame:
    del cache_version  # Included in the cache key to invalidate model-regime changes.
    response = requests.get(URL, timeout=20)
    response.raise_for_status()
    return prepare_coe_data(response.json()["result"]["records"])


@st.cache_data(show_spinner=False)
def run_backtest(data: pd.DataFrame, category: str, cache_version: str) -> pd.DataFrame:
    del cache_version
    return walk_forward_backtest(data, category)


try:
    df = load_coe(MODEL_VERSION)
except Exception as error:
    st.error(f"Could not load or validate the official data.gov.sg dataset: {error}")
    st.stop()

st.info(
    f"Comparable analysis window: {ANALYSIS_START:%B %Y} onward. "
    "Earlier tenders are excluded from charts, training, tuning, intervals and benchmark metrics."
)

tabs = st.tabs([*CATEGORIES, "Dealer-signal experiment", "Economy & markets", "Methodology & audit"])

for tab, category in zip(tabs[:3], CATEGORIES):
    with tab:
        category_data = df[df["vehicle_class"] == category].sort_values(["month", "bidding_no"])
        latest = category_data.iloc[-1]
        previous = category_data.iloc[-2]
        pressure = latest["bids_received"] / latest["quota"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latest COE", f"S${latest['premium']:,.0f}", f"{latest['premium'] - previous['premium']:+,.0f}", help=METRIC_HELP["latest_coe"])
        c2.metric("Completed-tender bid / quota", f"{pressure:.2f}×", help=METRIC_HELP["bid_quota"])
        c3.metric("Bids received", f"{latest['bids_received']:,.0f}", help=METRIC_HELP["bids_received"])
        c4.metric("Quota", f"{latest['quota']:,.0f}", help=METRIC_HELP["quota"])

        history = (
            category_data[["display_date", "premium"]]
            .dropna()
            .set_index("display_date")
            .rename(columns={"premium": "COE premium"})
        )
        st.line_chart(history)
        st.caption("Chart dates approximate tender order (1st and 15th); the source identifies month and exercise number, not closing timestamps.")

        with st.spinner(f"Running leakage-safe {category} walk-forward evaluation…"):
            backtest = run_backtest(df, category, MODEL_VERSION)
        if backtest.empty:
            st.warning("Not enough validated history to run this category's back-test.")
            continue
        summary = summarize_backtest(backtest)
        structural = summary.metrics.loc["structural"]
        best_naive = summary.metrics.loc[summary.best_naive]

        direction_backtest = prequential_direction_probabilities(backtest)
        next_forecast = forecast_next_tender(df, category, backtest)
        st.subheader("Next bidding exercise: experimental three-way outlook")
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("Most likely outcome", next_forecast.predicted_direction, help=METRIC_HELP["predicted_outcome"])
        p2.metric("Increase probability", f"{next_forecast.probabilities['Increase']:.1%}", help=METRIC_HELP["outcome_probability"])
        p3.metric("Stay probability", f"{next_forecast.probabilities['Stay']:.1%}", help=METRIC_HELP["outcome_probability"])
        p4.metric("Decrease probability", f"{next_forecast.probabilities['Decrease']:.1%}", help=METRIC_HELP["outcome_probability"])
        p5.metric("Predicted change", format_signed_sgd(next_forecast.predicted_change), help=METRIC_HELP["predicted_change"])
        st.caption(
            f"Target exercise: {next_forecast.tender_id}. Increase means above +S\\$1,000; Stay means within ±S\\$1,000 inclusive; "
            f"Decrease means below −S\\$1,000. Probabilities use {next_forecast.calibration_observations} earlier out-of-sample residuals under "
            f"{DIRECTION_PROBABILITY_VERSION}. Supply assumption: {next_forecast.quota_assumption.lower()}. "
            "The most likely outcome can differ from the point forecast because the historical residual distribution may be asymmetric."
        )
        if not direction_backtest.empty:
            brier = float(direction_backtest["brier_score"].mean())
            baseline_brier = float(direction_backtest["frequency_baseline_brier"].mean())
            brier_improvement = (baseline_brier - brier) / baseline_brier
            three_way_accuracy = float(
                direction_backtest["predicted_direction"].eq(direction_backtest["actual_direction"]).mean()
            )
            q1, q2, q3, q4 = st.columns(4)
            q1.metric("Probability back-tests", f"{len(direction_backtest):,}", help=METRIC_HELP["probability_backtests"])
            q2.metric("Three-way Brier score", f"{brier:.3f}", help=METRIC_HELP["brier_score"])
            q3.metric("Brier vs frequency baseline", f"{brier_improvement:+.1%}", help=METRIC_HELP["brier_improvement"])
            q4.metric("Three-way accuracy", f"{three_way_accuracy:.1%}", help=METRIC_HELP["three_way_accuracy"])
            if brier_improvement <= 0:
                st.warning(
                    "These probabilities did not beat the historical-frequency probability baseline on Brier score. "
                    "They are displayed as an experimental scenario, not a calibrated forecasting edge."
                )
            else:
                st.info(
                    "The probability layer beat the historical-frequency baseline retrospectively, but remains experimental "
                    "until performance is confirmed on future frozen forecasts."
                )

        st.subheader("Expanding-window out-of-sample results")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Direction accuracy", f"{structural['direction_accuracy']:.1%}", help=METRIC_HELP["direction_accuracy"])
        m2.metric("MAE", f"S${structural['MAE']:,.0f}", help=METRIC_HELP["mae"])
        m3.metric("RMSE", f"S${structural['RMSE']:,.0f}", help=METRIC_HELP["rmse"])
        m4.metric("80% interval coverage", f"{summary.interval_coverage:.1%}", help=METRIC_HELP["interval_coverage"])
        n1, n2, n3 = st.columns(3)
        n1.metric("Best naïve benchmark", summary.best_naive.replace("_", " ").title(), help=METRIC_HELP["best_naive"])
        n2.metric("MAE improvement vs best naïve", f"{summary.mae_improvement_vs_best_naive:+.1%}", help=METRIC_HELP["mae_improvement_naive"])
        n3.metric("RMSE improvement vs best naïve", f"{summary.rmse_improvement_vs_best_naive:+.1%}", help=METRIC_HELP["rmse_improvement_naive"])
        if summary.mae_improvement_vs_best_naive <= 0:
            st.warning("The structural model does not beat the best naïve MAE in this historical test. It is a research benchmark, not a calibrated forecasting edge.")

        comparison = summary.metrics.copy()
        comparison.index = comparison.index.str.replace("_", " ").str.title()
        comparison["MAE"] = comparison["MAE"].map(lambda value: f"S${value:,.0f}")
        comparison["RMSE"] = comparison["RMSE"].map(lambda value: f"S${value:,.0f}")
        comparison["direction_accuracy"] = comparison["direction_accuracy"].map(lambda value: f"{value:.1%}")
        st.dataframe(comparison.rename(columns={"direction_accuracy": "Direction accuracy"}), width="stretch")

        forecast_chart = (
            backtest[["display_date", "actual", "structural", "lower", "upper"]]
            .dropna(subset=["actual", "structural"])
            .set_index("display_date")
            .rename(
                columns={
                    "actual": "Actual",
                    "structural": "Structural forecast",
                    "lower": "80% lower",
                    "upper": "80% upper",
                }
            )
        )
        st.line_chart(forecast_chart)
        st.caption(
            f"{summary.observations} one-tender-ahead predictions. Regularization is selected in nested time-ordered folds; intervals use only earlier forecast errors. "
            f"Best naïve MAE: S${best_naive['MAE']:,.0f}."
        )

with tabs[3]:
    st.subheader("SGCarMart 2024–2026 dealer-signal research dataset")
    st.write(
        "This is an ingestion and validation layer, not a published Dealer Pressure Index. "
        "Weights and probabilities remain uncalibrated until a frozen out-of-sample comparison demonstrates incremental value."
    )
    dataset_path = Path(__file__).parent / "data" / "dealer_observations_sgcarmart_2024_2026.csv"
    metrics_path = Path(__file__).parent / "data" / "dealer_backtest_metrics.csv"
    dealer_manifest_path = Path(__file__).parent / "data" / "sgcarmart_source_manifest_2024_2026.csv"
    if dataset_path.exists():
        archive = pd.read_csv(dataset_path)
        validated_archive, archive_errors = validate_dealer_observations(archive)
        if archive_errors:
            st.error("The bundled SGCarMart dataset failed validation:\n\n- " + "\n- ".join(archive_errors))
        else:
            dealer_manifest = pd.read_csv(dealer_manifest_path) if dealer_manifest_path.exists() else pd.DataFrame()
            source_pdf_count = len(dealer_manifest) if not dealer_manifest.empty else 0
            source_brand_count = dealer_manifest["brand"].nunique() if not dealer_manifest.empty else 0
            a1, a2, a3, a4, a5, a6 = st.columns(6)
            a1.metric("Source PDFs", f"{source_pdf_count:,}", help=METRIC_HELP["source_pdfs"])
            a2.metric("Requested groups", f"{len(REQUESTED_BRAND_GROUPS):,}", help=METRIC_HELP["requested_groups"])
            a3.metric("Source marques", f"{source_brand_count:,}", help=METRIC_HELP["source_marques"])
            a4.metric("Eligible groups", f"{validated_archive['brand'].nunique():,}", help=METRIC_HELP["eligible_groups"])
            a5.metric("Cat A rows", f"{(validated_archive['category'] == 'Category A').sum():,}", help=METRIC_HELP["category_rows"])
            a6.metric("Cat B rows", f"{(validated_archive['category'] == 'Category B').sum():,}", help=METRIC_HELP["category_rows"])
            st.download_button(
                "Download validated SGCarMart dealer observations",
                archive.to_csv(index=False).encode(),
                "sgcarmart_dealer_observations_2024_2026.csv",
                "text/csv",
            )
            st.caption(
                f"Dated observations: {validated_archive['observed_at'].min().date()} to {validated_archive['observed_at'].max().date()}. "
                f"The source corpus covers {source_brand_count} marques in {len(REQUESTED_BRAND_GROUPS)} requested groups; eligible rows from "
                f"{', '.join(sorted(validated_archive['brand'].unique()))} require an explicit Cat A/B page label and extracted advertised prices."
            )
            if not dealer_manifest.empty:
                coverage = dealer_manifest[["brand", "document_date"]].copy()
                coverage["Brand group"] = coverage["brand"].map(SOURCE_TO_BRAND_GROUP)
                coverage = (
                    coverage.groupby("Brand group", sort=False)
                    .agg(
                        **{
                            "Source marques": ("brand", lambda values: ", ".join(sorted(set(values)))),
                            "Source PDFs": ("brand", "size"),
                            "Latest document": ("document_date", "max"),
                        }
                    )
                    .reindex(REQUESTED_BRAND_GROUPS)
                    .reset_index()
                )
                eligible_counts = validated_archive["brand"].value_counts()
                coverage["Model-eligible rows"] = coverage["Brand group"].map(eligible_counts).fillna(0).astype(int)
                coverage["Model eligible"] = coverage["Model-eligible rows"].gt(0).map({True: "Yes", False: "No"})
                with st.expander("Coverage by requested brand group", expanded=True):
                    st.dataframe(coverage, hide_index=True, width="stretch")
            finance_rates = validated_archive["finance_rate_pct"].dropna()
            if not finance_rates.empty:
                st.caption(
                    f"Explicit advertised car-finance rates: {len(finance_rates):,} observations, "
                    f"{finance_rates.min():.2f}%–{finance_rates.max():.2f}%. "
                    "Only clearly labelled plausible percentage rates are retained; the current archive coverage is Honda only."
                )
    if metrics_path.exists():
        metrics = pd.read_csv(metrics_path)
        combined = metrics[metrics["model"].eq("structural_plus_dealer")].copy()
        if not combined.empty:
            st.subheader("Incremental out-of-sample test")
            for row in combined.itertuples(index=False):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(f"{row.category} forecasts", f"{int(row.observations):,}", help=METRIC_HELP["forecast_count"])
                c2.metric("Combined MAE", f"S${row.MAE:,.0f}", help=METRIC_HELP["combined_mae"])
                c3.metric("MAE vs structural", f"{row.MAE_improvement_vs_structural:+.1%}", help=METRIC_HELP["mae_vs_structural"])
                c4.metric("Direction accuracy", f"{row.direction_accuracy:.1%}", help=METRIC_HELP["direction_accuracy"])
                if row.MAE_improvement_vs_structural <= 0:
                    st.warning(f"For {row.category}, the dealer-augmented model did not improve MAE in this test. No forecasting edge is claimed.")
                else:
                    st.info(f"For {row.category}, the historical MAE improved, but this remains retrospective evidence requiring future frozen validation.")
            display_metrics = metrics.copy()
            display_metrics["model"] = display_metrics["model"].str.replace("_", " ").str.title()
            st.dataframe(display_metrics, hide_index=True, width="stretch")

    template = empty_dealer_template()
    st.download_button(
        "Download versioned dealer-observation template",
        template.to_csv(index=False).encode(),
        "dealer_observations_v0_2.csv",
        "text/csv",
    )
    upload = st.file_uploader("Validate dealer observations", type="csv")
    if upload is not None:
        uploaded = pd.read_csv(upload)
        validated, errors = validate_dealer_observations(uploaded)
        if errors:
            st.error("Validation failed:\n\n- " + "\n- ".join(errors))
        else:
            st.success(f"Validated {len(validated):,} observations. No model uplift claim has been made.")
            st.dataframe(validated.head(100), width="stretch")
    st.markdown(
        """
The experiment will compare two forecasts at exactly the same tender cutoffs:

1. **Structural-only:** the model reported in the category tabs.
2. **Structural + dealer signals:** advertised-price changes, COE rebates, guaranteed-COE terms, incentives, promotion urgency/roadshows, and market-share weights observed before the frozen cutoff.

The SGCarMart corpus uses page-level category summaries, not unverified model/variant normalization. A dated archive document's effective/publication time is recorded separately from the later research retrieval time. Market-share weights use LTA registrations from the preceding 12 complete months. Cat D is excluded because this car-price-list archive does not represent motorcycle dealers.

Dealer features are accepted only when source URL, observation time, evidenced availability time, retrieval time and category are present. The collection workflow, checksums and data dictionary are versioned in the repository.
"""
    )

with tabs[4]:
    st.subheader("Economic and financial-market variables")
    st.write(
        "The candidate v0.8 model adds Singapore growth, inflation and unemployment; "
        "SGD/USD, global equities, volatility, long-term rates and oil; and the MAS three-year "
        "new-vehicle hire-purchase rate with an explicit staleness measure. The existing "
        "structural forecast remains primary unless the augmented model improves frozen out-of-sample results."
    )
    economic_path = Path(__file__).parent / "data" / "economic_financial_features.csv"
    economic_metrics_path = Path(__file__).parent / "data" / "economic_backtest_metrics.csv"
    source_manifest_path = Path(__file__).parent / "data" / "economic_financial_source_manifest.csv"
    if economic_path.exists():
        economic_raw = pd.read_csv(economic_path)
        economic, economic_errors = validate_economic_features(economic_raw)
        if economic_errors:
            st.error("The bundled economic dataset failed validation:\n\n- " + "\n- ".join(economic_errors))
        else:
            latest_economic = economic.iloc[-1]
            e1, e2, e3, e4, e5 = st.columns(5)
            e1.metric("SGD per US dollar", f"{latest_economic.sgd_per_usd:.4f}", help=METRIC_HELP["sgd_usd"])
            e2.metric("VIX", f"{latest_economic.vix:.1f}", help=METRIC_HELP["vix"])
            e3.metric("US 10-year yield", f"{latest_economic.us_10y_yield:.2f}%", help=METRIC_HELP["us_10y"])
            e4.metric("Brent crude", f"US${latest_economic.brent_usd:.2f}", help=METRIC_HELP["brent"])
            e5.metric("Nasdaq 1-month", f"{latest_economic.nasdaq_return_21d:+.1%}", help=METRIC_HELP["nasdaq_1m"])
            e6, e7, e8, e9, e10 = st.columns(5)
            e6.metric("Singapore real GDP YoY", f"{latest_economic.sg_real_gdp_yoy:.1f}%", help=METRIC_HELP["gdp_yoy"])
            e7.metric("Singapore CPI YoY", f"{latest_economic.sg_cpi_yoy:.1f}%", help=METRIC_HELP["cpi_yoy"])
            e8.metric("Singapore unemployment", f"{latest_economic.sg_unemployment_rate:.1f}%", help=METRIC_HELP["unemployment"])
            e9.metric("Vehicle HP rate", f"{latest_economic.vehicle_hire_purchase_3y_rate:.2f}%", help=METRIC_HELP["vehicle_hp"])
            e10.metric("Vehicle-rate age", f"{latest_economic.vehicle_hire_purchase_rate_staleness_days:,.0f} days", help=METRIC_HELP["vehicle_rate_age"])
            st.download_button(
                "Download tender-aligned economic features",
                economic_raw.to_csv(index=False).encode(),
                "economic_financial_features.csv",
                "text/csv",
            )
            st.caption(
                f"{len(economic):,} conservative tender cutoffs with {len(ECONOMIC_FEATURE_COLUMNS)} variables. "
                "Daily U.S.-market observations are delayed to the following Singapore day; macro series use fixed publication buffers."
            )
    if economic_metrics_path.exists():
        economic_metrics = pd.read_csv(economic_metrics_path)
        financing_model = economic_metrics[
            economic_metrics["model"].eq("structural_plus_economy_financing")
        ]
        if not financing_model.empty:
            st.subheader("Paired expanding-window financing-rate test")
            for row in financing_model.itertuples(index=False):
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric(f"{row.category} forecasts", f"{int(row.observations):,}", help=METRIC_HELP["forecast_count"])
                c2.metric("Financing-model MAE", f"S${row.MAE:,.0f}", help=METRIC_HELP["financing_mae"])
                c3.metric("MAE vs structural", f"{row.MAE_improvement_vs_structural:+.1%}", help=METRIC_HELP["mae_vs_structural"])
                c4.metric("MAE vs economy core", f"{row.MAE_improvement_vs_economy_core:+.1%}", help=METRIC_HELP["mae_vs_economy"])
                c5.metric("Direction accuracy", f"{row.direction_accuracy:.1%}", help=METRIC_HELP["direction_accuracy"])
                if row.MAE_improvement_vs_structural <= 0:
                    st.warning(f"For {row.category}, the full financing-rate candidate worsened MAE. No edge is claimed.")
            st.caption(
                "The MAS series covers new vehicles generally and is used as a financing-cost proxy for cars and motorcycles; "
                "it does not publish a vehicle-type split and its last observation is April 2023. Adding its level and staleness "
                "worsened MAE versus both structural-only and the 13-variable economy core in all categories."
            )
            st.dataframe(economic_metrics, hide_index=True, width="stretch")
    if source_manifest_path.exists():
        with st.expander("Sources and historical availability rules"):
            st.dataframe(pd.read_csv(source_manifest_path), hide_index=True, width="stretch")
    st.info(
        "Macroeconomic tables are current-vintage series and may contain later revisions. Conservative release lags "
        "prevent use of the current period too early, but they do not recreate true historical data vintages."
    )

with tabs[5]:
    st.subheader("v0.8 dealer and exact-cutoff economy audit trail")
    st.markdown(
        f"""
- **Common analysis boundary:** all charts, model fitting, tuning, intervals and benchmark metrics start in October 2015. Pre-October-2015 tenders are excluded for policy-regime reliability and comparability.
- **Fixed parsing defect:** official values containing commas were previously coerced to missing values, causing recent charts and results to be unreliable.
- **Target:** one-tender-ahead change in COE premium, modelled separately for Categories A, B and D.
- **Validation:** expanding walk-forward evaluation with a minimum 60-tender training window. Ridge regularization is selected inside each training window using time-ordered inner folds.
- **Benchmarks:** persistence, historical mean drift and the premium from two tenders earlier.
- **Uncertainty:** an 80% prequential conformal interval based only on absolute errors from earlier out-of-sample forecasts. Coverage is empirical, not guaranteed prospectively.
- **No current-tender outcome leakage:** premiums, bids, bid-to-quota ratios, excess demand, momentum and Cat E outcome signals are lagged by at least one completed tender.
- **Announced supply assumption:** current-tender category and Cat E quotas are treated as known before bidding. The results dataset lacks publication timestamps, so future frozen forecasts should archive the corresponding LTA announcement.
- **Probability forecast:** the three-way Increase/Stay/Decrease probabilities use only earlier out-of-sample structural residuals with Laplace smoothing. Stay is defined as an inclusive ±S$1,000 change. Brier score is compared with an earlier-outcome-frequency baseline; probabilities remain experimental until future frozen validation.
- **No calibrated Dealer Pressure Index:** no arbitrary composite dealer weights or probabilities are published.
- **Dealer archive reconstruction:** date-only historical SGCarMart price lists are treated as available at 23:59:59 Singapore time on their stated date. If contemporaneous collection proves an earlier public time, that observed time is used; retrieval timestamps and PDF checksums remain recorded for audit.
- **Expanded dealer coverage:** the v0.8 corpus covers 20 requested brand groups through 23 SGCarMart source marques and 1,487 dated PDFs. Toyota/Lexus, Chery/Omoda/Jaecoo and GAC/Aion preserve their source-marque identity in audit notes while using grouped display labels and the matching consolidated LTA make series.
- **Dealer-model eligibility:** only explicitly labelled Cat A/B pages with extracted advertised prices enter the incremental test. Unclassified pages remain visible for review; Cat D has no SGCarMart car-price-list dealer signal.
- **Economy/markets/financing experiment:** the candidate adds 15 as-of variables under `{ECONOMIC_MODEL_VERSION}`, including the MAS new-vehicle hire-purchase rate and its staleness, and is evaluated at the same outer forecast origins as the 13-variable economy core and structural model.
- **Car versus motorcycle financing:** 135 explicit advertised car-rate observations enter the Cat A/B dealer experiment. For Cat D, the MAS all-new-vehicle rate is only a market-wide proxy; no motorcycle-specific historical rate is imputed.
- **Market-data timing:** daily FX, volatility, interest-rate and oil observations are treated as available in Singapore only on the following calendar day. Twenty-one-trading-day changes use data at least 30 calendar days earlier.
- **Macro-data timing and revision caveat:** CPI is delayed 45 days; GDP and unemployment are delayed 75 days. SingStat tables are current-vintage and may include later revisions, so the experiment is not a real-time-vintage back-test.
"""
    )
    availability = pd.DataFrame(
        [
            {"Feature family": family, "Availability rule": rule}
            for family, rule in {**FEATURE_AVAILABILITY, **ECONOMIC_FEATURE_AVAILABILITY}.items()
        ]
    )
    st.dataframe(availability, hide_index=True, width="stretch")
    st.markdown(
        "Sources: [data.gov.sg COE Bidding Results](https://data.gov.sg/datasets/d_69b3380ad7e51aff3a7dcc84eba52b8a/view) • "
        "[LTA transport statistics](https://www.lta.gov.sg/content/ltagov/en/who_we_are/statistics_and_publications/statistics.html) • "
        "[SGCarMart price-list archive](https://www.sgcarmart.com/new-cars/pricelists) • "
        "[MAS bank and finance-company interest rates](https://eservices.mas.gov.sg/statistics/msb/InterestRatesOfBanksAndFinanceCompanies.aspx) • "
        "[SingStat Table Builder](https://tablebuilder.singstat.gov.sg/) • "
        "[FRED economic data](https://fred.stlouisfed.org/)"
    )
    st.caption("Experimental analysis, not financial advice. Model and methodology are disclosed so negative results remain visible.")
