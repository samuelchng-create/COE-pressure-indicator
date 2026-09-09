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
from official_results import parse_one_motoring_final_results
from tender_timing import exercise_status, load_tender_schedule


st.set_page_config(page_title="Singapore COE Pressure Indicator", layout="wide")
st.title("Singapore COE Pressure Indicator")
st.caption(
    f"v0.10 official final-results bridge + three-way outlook • "
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
ONEMOTORING_RESULTS_URL = (
    "https://onemotoring.lta.gov.sg/content/onemotoring/home/buying/coe-open-bidding.html"
)


@st.cache_data(ttl=300)
def load_coe(cache_version: str) -> tuple[pd.DataFrame, list[str]]:
    del cache_version  # Included in the cache key to invalidate model-regime changes.
    response = requests.get(URL, timeout=20)
    response.raise_for_status()
    records = list(response.json()["result"]["records"])
    direct_tenders: list[str] = []
    try:
        live_response = requests.get(ONEMOTORING_RESULTS_URL, timeout=20)
        live_response.raise_for_status()
        final_records = parse_one_motoring_final_results(live_response.text)
    except (requests.RequestException, ValueError):
        final_records = []
    existing = {(row["month"], str(row["bidding_no"]), row["vehicle_class"]) for row in records}
    for row in final_records:
        key = (row["month"], row["bidding_no"], row["vehicle_class"])
        if key not in existing:
            records.append(row)
            direct_tenders.append(f"{row['month']}-{row['bidding_no']}")
    return prepare_coe_data(records), sorted(set(direct_tenders))


@st.cache_data(show_spinner=False)
def run_backtest(data: pd.DataFrame, category: str, cache_version: str) -> pd.DataFrame:
    del cache_version
    return walk_forward_backtest(data, category)


try:
    df, direct_result_tenders = load_coe(MODEL_VERSION)
except Exception as error:
    st.error(f"Could not load or validate the official data.gov.sg dataset: {error}")
    st.stop()

tender_schedule = load_tender_schedule(
    Path(__file__).parent / "data" / "tender_schedule_2024_2026.csv"
)

if direct_result_tenders:
    st.success(
        f"Official final result {direct_result_tenders[-1]} loaded directly from "
        f"[LTA OneMotoring]({ONEMOTORING_RESULTS_URL}) while the data.gov.sg archive synchronises."
    )

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
        timing = exercise_status(tender_schedule, next_forecast.tender_id)
        if timing is not None:
            timing_level, timing_message, timing_source = timing
            getattr(st, timing_level)(f"{timing_message} [Official LTA schedule]({timing_source})")
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
    st.subheader("Methodology & audit trail — v0.10")
    st.write(
        "This section documents what the indicator is designed to answer, how every forecast is produced, "
        "which information is allowed at each historical cutoff, what changed since the original MVP, and "
        "which results remain experimental. It is intended to make the public analysis reproducible and falsifiable."
    )

    latest_completed_tender = str(df.sort_values(["month", "bidding_no"]).iloc[-1]["tender_id"])
    audit_root = Path(__file__).parent / "data"
    audit_dealer = pd.read_csv(audit_root / "dealer_observations_sgcarmart_2024_2026.csv")
    audit_manifest = pd.read_csv(audit_root / "sgcarmart_source_manifest_2024_2026.csv")
    audit_weights = pd.read_csv(audit_root / "lta_market_share_weights_2024_2026.csv")
    audit_economy = pd.read_csv(audit_root / "economic_financial_features.csv")

    with st.expander("1. Purpose, scope and current status", expanded=True):
        st.markdown(
            f"""
The app studies the next COE bidding exercise separately for **Category A, Category B and Category D**. Its primary model predicts the dollar change from the preceding completed premium. The v0.9 probability layer then classifies the realised change as **Increase** above `+S$1,000`, **Stay** within `±S$1,000` inclusive, or **Decrease** below `−S$1,000`.

The common analysis window begins in **October 2015** because earlier policy regimes are less comparable. The latest completed tender currently returned by the official results feed is **{latest_completed_tender}**. Structural forecasts are the primary published model. Dealer, economy and financing variants remain visible research experiments and do not replace it unless they demonstrate repeatable out-of-sample improvement.

The next-exercise panel resolves its opening and closing times from the versioned official LTA schedule. While an exercise is open it displays the live closing deadline; after the deadline and before the results feed updates, it explicitly says that the official result is pending.

This is public-interest statistical analysis, not a bidding recommendation or financial advice. No forecast, interval or probability is guaranteed.
"""
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {"Component": "Structural Ridge forecast", "Status": "Primary research model", "Claim": "Retrospective benchmark results disclosed"},
                    {"Component": "Three-way probability layer", "Status": "Experimental", "Claim": "Not prospectively calibrated"},
                    {"Component": "Structural + dealer signals", "Status": "Experimental", "Claim": "No general forecasting edge claimed"},
                    {"Component": "Structural + economy/markets", "Status": "Experimental", "Claim": "Not promoted over structural"},
                    {"Component": "Dealer Pressure Index", "Status": "Not published", "Claim": "No arbitrary weights or calibrated probabilities"},
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    with st.expander("2. Data sources and coverage", expanded=True):
        st.markdown(
            "The audit distinguishes the date information was economically available from the later date it was collected for research. "
            "Source URLs and checksums are retained where applicable. Official data.gov.sg results and LTA OneMotoring are checked with a "
            "five-minute application cache. A confirmed OneMotoring result can bridge an archive delay, but provisional closing prices are "
            "not admitted to model training while LTA says results are being finalised."
        )
        coverage_rows = [
            {
                "Data stream": "Official COE tender results",
                "Coverage used": f"October 2015 to {latest_completed_tender}",
                "Role": "Premium, quota, bids and tender ordering",
            },
            {
                "Data stream": "SGCarMart dealer price lists",
                "Coverage used": f"{audit_dealer['observed_at'].min()[:10]} to {audit_dealer['observed_at'].max()[:10]}",
                "Role": f"{len(audit_manifest):,} PDFs; {len(audit_dealer):,} eligible Cat A/B observations",
            },
            {
                "Data stream": "LTA new registrations",
                "Coverage used": f"Weights through {audit_weights['observation_month'].max()}",
                "Role": "Trailing 12-month dealer-brand aggregation weights",
            },
            {
                "Data stream": "Economy and financial markets",
                "Coverage used": f"{len(audit_economy):,} tender cutoffs from {audit_economy['tender_id'].min()} to {audit_economy['tender_id'].max()}",
                "Role": "As-of macroeconomic, market and financing candidates",
            },
            {
                "Data stream": "MAS new-vehicle hire purchase",
                "Coverage used": "Underlying rate series ends April 2023",
                "Role": "Market-wide financing proxy plus explicit staleness",
            },
        ]
        st.dataframe(pd.DataFrame(coverage_rows), hide_index=True, width="stretch")
        st.markdown(
            "Dealer coverage comprises **20 requested brand groups represented by 23 source marques**. "
            "Only 11 groups currently have observations that pass the strict model-eligibility rules. "
            "The 135 explicitly advertised dealer finance rates are all from Honda material, so they are not treated as market-wide."
        )

    with st.expander("3. Structural forecasting model"):
        st.markdown(
            f"""
**Target.** One-tender-ahead COE premium change, fitted separately for Categories A, B and D under `{MODEL_VERSION}`.

**Inputs available before the target tender.** Lagged premiums; one- and two-tender momentum; lagged bid-to-quota ratio and excess demand; announced category quota; quota change; lagged Cat E premium, momentum and bid pressure; announced Cat E quota; and cyclical month/exercise seasonality.

**Estimator.** A standardized Ridge regression. At every forecast origin, the regularization strength is selected again using time-ordered inner validation folds contained entirely inside that origin's training history.

**Supply convention.** Historical back-tests treat target-tender category and Cat E quotas as announced before bidding. For the live next-exercise forecast, the last completed quotas are carried forward until a separately timestamped upcoming announcement is ingested. This is a disclosed neutral assumption, not observed future supply.
"""
        )

    with st.expander("4. Walk-forward evaluation, benchmarks and uncertainty"):
        st.markdown(
            """
The outer evaluation is an expanding walk-forward test with a minimum 60-tender training window. Each row is a genuine one-step forecast: the model is fitted only on earlier tenders and the prediction is recorded before moving to the next outcome.

The structural model is compared at identical origins with three simple baselines:

- **Persistence:** next premium equals the latest completed premium.
- **Historical mean drift:** latest premium plus the average earlier change.
- **Two-tender seasonal:** next premium equals the premium two exercises earlier.

Reported diagnostics include direction accuracy, MAE, RMSE and improvement over the lowest-MAE naïve benchmark. The nominal 80% interval is prequential conformal: its radius uses only absolute errors from earlier outer forecasts. Historical coverage describes the test sample and is not a prospective guarantee.
"""
        )

    with st.expander("5. Three-way next-exercise probabilities"):
        st.markdown(
            f"""
The probability layer `{DIRECTION_PROBABILITY_VERSION}` does not assume normally distributed errors and does not convert the point forecast through an arbitrary confidence formula. It adds the current structural change forecast to each earlier out-of-sample residual, counts how many resulting changes fall into Increase, Stay and Decrease, and applies one-count Laplace smoothing to avoid unjustified zero probabilities.

Its own back-test is also prequential. A historical probability is produced only after 20 earlier out-of-sample residuals exist. It is scored using multiclass Brier score, log loss and highest-probability three-way accuracy, with probabilities based only on earlier outcome frequencies as the benchmark. Future outcomes cannot revise earlier probabilities.

The point forecast and highest-probability outcome may differ when the historical error distribution is asymmetric. These probabilities remain **experimental and uncalibrated prospectively**, even where retrospective Brier score beats the frequency baseline.
"""
        )

    with st.expander("6. Dealer-signal experiment"):
        st.markdown(
            """
The SGCarMart layer reconstructs dated 2024–2026 authorised-dealer price-list signals: advertised package prices and changes, COE rebates, guaranteed-COE terms and bid counts, finance/trade-in/cash incentives, promotion deadlines and roadshows. Brand aggregation uses LTA registrations from the preceding 12 complete months.

Only pages with an explicit Cat A or Cat B label and extracted advertised prices enter the model. Source-marque identity remains in audit notes when brands are grouped, including Toyota/Lexus, Chery/Omoda/Jaecoo and GAC/Aion. Unclassified pages remain auditable context rather than being imputed. Category D is excluded because the car price-list archive does not represent motorcycle dealers.

The experiment fits an expanding-window Ridge correction to the already out-of-sample structural residual. Cat A showed a small retrospective MAE improvement, while Cat B worsened materially. This mixed evidence is not a validated dealer forecasting edge, and no composite Dealer Pressure Index is published.
"""
        )

    with st.expander("7. Economy, markets and financing experiment"):
        st.markdown(
            f"""
The candidate `{ECONOMIC_MODEL_VERSION}` adds 15 tender-aligned variables: SGD/USD level and change; VIX level and change; US 10-year Treasury yield and change; Brent price and return; Nasdaq Composite level and return; Singapore real-GDP growth, CPI inflation and unemployment; and the MAS three-year new-vehicle hire-purchase rate plus its age in days.

Daily international observations are treated as available in Singapore only on the following calendar day. CPI is delayed 45 days; GDP and unemployment are delayed 75 days. Exact official tender-opening timestamps are used from 2024 onward; earlier tenders retain an ordered exercise-date approximation.

The 13-variable economy core produced mixed, marginal results. Adding financing worsened MAE versus both structural-only and economy-core models in all three categories. These variants therefore remain diagnostic research layers rather than the primary forecast. SingStat macro series are current-vintage and may contain later revisions, so this is not a fully vintage-correct real-time back-test.
"""
        )

    with st.expander("8. Leakage controls and historical availability"):
        st.markdown(
            """
- Premiums, bids, bid pressure, excess demand, momentum and Cat E outcomes are lagged by at least one completed tender.
- Outer-test outcomes never enter training, inner tuning, interval construction or probability estimation at that origin.
- Date-only historical SGCarMart documents are conservatively assigned to 23:59:59 Singapore time on the stated date unless contemporaneous evidence proves an earlier public time.
- Dealer records store `observed_at`, evidenced `available_at`, later `retrieved_at`, source URL and PDF checksum separately.
- Daily market observations receive a following-Singapore-day availability time; 21-trading-day changes use observations at least 30 calendar days earlier.
- Current-vintage macro revisions, carried-forward financing rates and live-quota assumptions are disclosed rather than silently treated as contemporaneous data.
"""
        )

    availability = pd.DataFrame(
        [
            {"Feature family": family, "Availability rule": rule}
            for family, rule in {**FEATURE_AVAILABILITY, **ECONOMIC_FEATURE_AVAILABILITY}.items()
        ]
    )
    with st.expander("9. Feature-by-feature availability rules"):
        st.dataframe(availability, hide_index=True, width="stretch")

    with st.expander("10. MVP audit findings and version history"):
        st.markdown(
            """
The original MVP audit found that comma-formatted official numbers could be coerced to missing values, recent tenders could therefore disappear, Ridge features were unscaled, month was treated as ordinal rather than cyclical, Cat E and announced supply were absent, and evaluation showed only persistence MAE. The dealer template also lacked sufficient provenance and enforceable historical cutoffs. The original premium and bid-pressure inputs were lagged, so no direct same-tender outcome leakage was found.

- **Structural v0.5:** fixed numeric parsing; standardized Ridge; cyclical seasonality; Cat E and supply features; nested time-ordered tuning; three naïve benchmarks; MAE, RMSE, direction and conformal coverage.
- **Research v0.8:** October 2015 common boundary; 20-brand-group SGCarMart reconstruction; LTA market-share weighting; economy, markets and vehicle-financing experiments; exact official cutoffs from 2024.
- **Interface/model v0.9:** Increase/Stay/Decrease probability layer, probability benchmarking, complete indicator tooltips and this consolidated methodology/audit narrative.
- **Data refresh v0.10:** strict final-result ingestion from LTA OneMotoring when the data.gov.sg archive is delayed; provisional closing tables remain excluded.
"""
        )

    with st.expander("11. Sources, reproducibility and known limitations"):
        st.markdown(
            """
**Primary sources:** [data.gov.sg COE Bidding Results](https://data.gov.sg/datasets/d_69b3380ad7e51aff3a7dcc84eba52b8a/view) · [LTA transport statistics](https://www.lta.gov.sg/content/ltagov/en/who_we_are/statistics_and_publications/statistics.html) · [SGCarMart price-list archive](https://www.sgcarmart.com/new-cars/pricelists) · [MAS bank and finance-company interest rates](https://eservices.mas.gov.sg/statistics/msb/InterestRatesOfBanksAndFinanceCompanies.aspx) · [SingStat Table Builder](https://tablebuilder.singstat.gov.sg/) · [FRED economic data](https://fred.stlouisfed.org/)

**Known limitations:** reconstructed dealer availability is weaker than a prospectively frozen collection; only a subset of brands produces category-labelled eligible observations; advertised finance-rate coverage is narrow; Cat D lacks dealer-price-list signals; macro data may be revised; the vehicle-finance proxy is stale and not split between cars and motorcycles; pre-2024 tender timestamps are approximate; and the next-exercise quota currently uses a carry-forward assumption.

The repository versions the model code, methodology, source manifests, checksums, tender schedule, feature datasets and back-test outputs. Negative results remain visible. A credible calibration or forecasting-edge claim requires future predictions frozen before bidding and evaluated after the outcomes arrive.
"""
        )
    st.caption("Experimental analysis, not financial advice. Model and methodology are disclosed so negative results remain visible.")
