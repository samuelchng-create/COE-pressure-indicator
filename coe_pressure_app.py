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
    f"v0.7 vehicle-financing experiment + v0.6 dealer archive • "
    f"{MODEL_VERSION} • experimental, uncalibrated public-interest analysis"
)

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
        c1.metric("Latest COE", f"S${latest['premium']:,.0f}", f"{latest['premium'] - previous['premium']:+,.0f}")
        c2.metric("Completed-tender bid / quota", f"{pressure:.2f}×")
        c3.metric("Bids received", f"{latest['bids_received']:,.0f}")
        c4.metric("Quota", f"{latest['quota']:,.0f}")

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
        st.subheader("Expanding-window out-of-sample results")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Direction accuracy", f"{structural['direction_accuracy']:.1%}")
        m2.metric("MAE", f"S${structural['MAE']:,.0f}")
        m3.metric("RMSE", f"S${structural['RMSE']:,.0f}")
        m4.metric("80% interval coverage", f"{summary.interval_coverage:.1%}")
        n1, n2, n3 = st.columns(3)
        n1.metric("Best naïve benchmark", summary.best_naive.replace("_", " ").title())
        n2.metric("MAE improvement vs best naïve", f"{summary.mae_improvement_vs_best_naive:+.1%}")
        n3.metric("RMSE improvement vs best naïve", f"{summary.rmse_improvement_vs_best_naive:+.1%}")
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
            a1, a2, a3, a4, a5 = st.columns(5)
            a1.metric("Source PDFs", f"{source_pdf_count:,}")
            a2.metric("Source brands", f"{source_brand_count:,}")
            a3.metric("Eligible brands", f"{validated_archive['brand'].nunique():,}")
            a4.metric("Cat A rows", f"{(validated_archive['category'] == 'Category A').sum():,}")
            a5.metric("Cat B rows", f"{(validated_archive['category'] == 'Category B').sum():,}")
            st.download_button(
                "Download validated SGCarMart dealer observations",
                archive.to_csv(index=False).encode(),
                "sgcarmart_dealer_observations_2024_2026.csv",
                "text/csv",
            )
            st.caption(
                f"Dated observations: {validated_archive['observed_at'].min().date()} to {validated_archive['observed_at'].max().date()}. "
                f"The source corpus covers {source_brand_count} brands; eligible rows from "
                f"{', '.join(sorted(validated_archive['brand'].unique()))} require an explicit Cat A/B page label and extracted advertised prices."
            )
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
                c1.metric(f"{row.category} forecasts", f"{int(row.observations):,}")
                c2.metric("Combined MAE", f"S${row.MAE:,.0f}")
                c3.metric("MAE vs structural", f"{row.MAE_improvement_vs_structural:+.1%}")
                c4.metric("Direction accuracy", f"{row.direction_accuracy:.1%}")
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
        "The candidate v0.7 model adds Singapore growth, inflation and unemployment; "
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
            e1.metric("SGD per US dollar", f"{latest_economic.sgd_per_usd:.4f}")
            e2.metric("VIX", f"{latest_economic.vix:.1f}")
            e3.metric("US 10-year yield", f"{latest_economic.us_10y_yield:.2f}%")
            e4.metric("Brent crude", f"US${latest_economic.brent_usd:.2f}")
            e5.metric("Nasdaq 1-month", f"{latest_economic.nasdaq_return_21d:+.1%}")
            e6, e7, e8, e9, e10 = st.columns(5)
            e6.metric("Singapore real GDP YoY", f"{latest_economic.sg_real_gdp_yoy:.1f}%")
            e7.metric("Singapore CPI YoY", f"{latest_economic.sg_cpi_yoy:.1f}%")
            e8.metric("Singapore unemployment", f"{latest_economic.sg_unemployment_rate:.1f}%")
            e9.metric("Vehicle HP rate", f"{latest_economic.vehicle_hire_purchase_3y_rate:.2f}%")
            e10.metric("Vehicle-rate age", f"{latest_economic.vehicle_hire_purchase_rate_staleness_days:,.0f} days")
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
                c1.metric(f"{row.category} forecasts", f"{int(row.observations):,}")
                c2.metric("Financing-model MAE", f"S${row.MAE:,.0f}")
                c3.metric("MAE vs structural", f"{row.MAE_improvement_vs_structural:+.1%}")
                c4.metric("MAE vs economy core", f"{row.MAE_improvement_vs_economy_core:+.1%}")
                c5.metric("Direction accuracy", f"{row.direction_accuracy:.1%}")
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
    st.subheader("v0.7 financing / v0.6 dealer archive audit trail")
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
- **No calibrated Dealer Pressure Index:** no arbitrary composite weights or probabilities are published.
- **Dealer archive reconstruction:** date-only historical SGCarMart price lists are treated as available at 23:59:59 Singapore time on their stated date. If contemporaneous collection proves an earlier public time, that observed time is used; retrieval timestamps and PDF checksums remain recorded for audit.
- **Expanded dealer coverage:** the v0.6 source corpus covers 12 authorised-dealer brands. A brand contributes model rows only when its page layout passes the same explicit Cat A/B label and advertised-price rules; categories are never inferred from vehicle models.
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
