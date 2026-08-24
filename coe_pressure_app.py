from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from coe_model import (
    CATEGORIES,
    FEATURE_AVAILABILITY,
    MODEL_VERSION,
    prepare_coe_data,
    summarize_backtest,
    walk_forward_backtest,
)
from dealer_signals import empty_dealer_template, validate_dealer_observations


st.set_page_config(page_title="Singapore COE Pressure Indicator", layout="wide")
st.title("Singapore COE Pressure Indicator")
st.caption(f"v0.2 structural model + v0.3 dealer archive experiment • {MODEL_VERSION} • experimental, uncalibrated public-interest analysis")

DATASET = "d_69b3380ad7e51aff3a7dcc84eba52b8a"
URL = f"https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000"


@st.cache_data(ttl=3600)
def load_coe() -> pd.DataFrame:
    response = requests.get(URL, timeout=20)
    response.raise_for_status()
    return prepare_coe_data(response.json()["result"]["records"])


@st.cache_data(show_spinner=False)
def run_backtest(data: pd.DataFrame, category: str) -> pd.DataFrame:
    return walk_forward_backtest(data, category)


try:
    df = load_coe()
except Exception as error:
    st.error(f"Could not load or validate the official data.gov.sg dataset: {error}")
    st.stop()

tabs = st.tabs([*CATEGORIES, "Dealer-signal experiment", "Methodology & audit"])

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
            backtest = run_backtest(df, category)
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
    if dataset_path.exists():
        archive = pd.read_csv(dataset_path)
        validated_archive, archive_errors = validate_dealer_observations(archive)
        if archive_errors:
            st.error("The bundled SGCarMart dataset failed validation:\n\n- " + "\n- ".join(archive_errors))
        else:
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Eligible observations", f"{len(validated_archive):,}")
            a2.metric("Eligible brands", f"{validated_archive['brand'].nunique():,}")
            a3.metric("Cat A rows", f"{(validated_archive['category'] == 'Category A').sum():,}")
            a4.metric("Cat B rows", f"{(validated_archive['category'] == 'Category B').sum():,}")
            st.download_button(
                "Download validated SGCarMart dealer observations",
                archive.to_csv(index=False).encode(),
                "sgcarmart_dealer_observations_2024_2026.csv",
                "text/csv",
            )
            st.caption(
                f"Dated observations: {validated_archive['observed_at'].min().date()} to {validated_archive['observed_at'].max().date()}. "
                "The source corpus covers six brands; eligible rows from BYD, Honda and Toyota require an explicit Cat A/B page label and extracted advertised prices."
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
    st.subheader("v0.2 audit trail")
    st.markdown(
        """
- **Fixed parsing defect:** official values containing commas were previously coerced to missing values, causing recent charts and results to be unreliable.
- **Target:** one-tender-ahead change in COE premium, modelled separately for Categories A, B and D.
- **Validation:** expanding walk-forward evaluation with a minimum 60-tender training window. Ridge regularization is selected inside each training window using time-ordered inner folds.
- **Benchmarks:** persistence, historical mean drift and the premium from two tenders earlier.
- **Uncertainty:** an 80% prequential conformal interval based only on absolute errors from earlier out-of-sample forecasts. Coverage is empirical, not guaranteed prospectively.
- **No current-tender outcome leakage:** premiums, bids, bid-to-quota ratios, excess demand, momentum and Cat E outcome signals are lagged by at least one completed tender.
- **Announced supply assumption:** current-tender category and Cat E quotas are treated as known before bidding. The results dataset lacks publication timestamps, so future frozen forecasts should archive the corresponding LTA announcement.
- **No calibrated Dealer Pressure Index:** no arbitrary composite weights or probabilities are published in v0.2.
- **Dealer archive reconstruction:** date-only SGCarMart price lists are treated as available at 23:59:59 Singapore time on their stated date; the later research retrieval timestamp and PDF checksum remain recorded for audit.
- **Dealer-model eligibility:** only explicitly labelled Cat A/B pages with extracted advertised prices enter the incremental test. Unclassified pages remain visible for review; Cat D has no SGCarMart car-price-list dealer signal.
"""
    )
    availability = pd.DataFrame(
        [{"Feature family": family, "Availability rule": rule} for family, rule in FEATURE_AVAILABILITY.items()]
    )
    st.dataframe(availability, hide_index=True, width="stretch")
    st.markdown(
        "Sources: [data.gov.sg COE Bidding Results](https://data.gov.sg/datasets/d_69b3380ad7e51aff3a7dcc84eba52b8a/view) • "
        "[LTA transport statistics](https://www.lta.gov.sg/content/ltagov/en/who_we_are/statistics_and_publications/statistics.html) • "
        "[SGCarMart price-list archive](https://www.sgcarmart.com/new-cars/pricelists)"
    )
    st.caption("Experimental analysis, not financial advice. Model and methodology are disclosed so negative results remain visible.")
