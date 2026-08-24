"""Build a conservative as-of economy/markets feature dataset."""

from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economic_features import ECONOMIC_FEATURE_COLUMNS, validate_economic_features


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "economic_financial_features.csv"
MANIFEST = ROOT / "data" / "economic_financial_source_manifest.csv"
START = pd.Timestamp("2002-01-01", tz="Asia/Singapore")
RETRIEVED_AT = pd.Timestamp.now(tz="Asia/Singapore").floor("s")

FRED_SERIES = {
    "sgd_per_usd": "DEXSIUS",
    "vix": "VIXCLS",
    "us_10y_yield": "DGS10",
    "brent_usd": "DCOILBRENTEU",
    "nasdaq_composite": "NASDAQCOM",
}
SINGSTAT_SERIES = {
    "sg_real_gdp_yoy": ("M015631", "2", 75),
    "sg_cpi_yoy": ("M213781", "1", 45),
    "sg_unemployment_rate": ("M182342", "1", 75),
}


def get_text(url: str) -> str:
    """Fetch public data with curl, which handles these providers reliably."""
    completed = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--retry-delay", "2", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def get_json(url: str) -> dict:
    return json.loads(get_text(url))


def load_fred(series_id: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    frame = pd.read_csv(StringIO(get_text(url)))
    frame.columns = ["period_end", "value"]
    frame["period_end"] = pd.to_datetime(frame["period_end"], utc=True)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna().sort_values("period_end")
    # U.S. daily observations are conservatively treated as known in Singapore
    # only at noon on the following calendar day.
    frame["available_at"] = frame["period_end"] + pd.Timedelta(days=1, hours=4)
    return frame


def parse_singstat_period(key: str) -> pd.Timestamp:
    if key.endswith(("1Q", "2Q", "3Q", "4Q")):
        year = int(key[:4])
        quarter = int(key[-2])
        return pd.Period(f"{year}Q{quarter}", freq="Q").end_time.normalize().tz_localize("Asia/Singapore")
    return pd.Timestamp(key, tz="Asia/Singapore") + pd.offsets.MonthEnd(0)


def load_singstat(resource_id: str, series_no: str, release_lag_days: int) -> pd.DataFrame:
    url = f"https://tablebuilder.singstat.gov.sg/api/table/tabledata/{resource_id}"
    payload = get_json(url)["Data"]
    row = next(item for item in payload["row"] if item["seriesNo"] == series_no)
    frame = pd.DataFrame(row["columns"]).rename(columns={"key": "period", "value": "value"})
    frame["period_end"] = frame["period"].map(parse_singstat_period)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["value"]).sort_values("period_end")
    # SingStat's current table is revision-prone and lacks historical release
    # timestamps. Conservative lags prevent using the current period too early;
    # revision/vintage risk remains explicitly disclosed in the manifest.
    frame["available_at"] = frame["period_end"] + pd.Timedelta(days=release_lag_days)
    return frame[["period_end", "available_at", "value"]]


def latest_asof(frame: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[float, pd.Timestamp]:
    eligible = frame[frame["available_at"] <= cutoff]
    if eligible.empty:
        return np.nan, pd.NaT
    row = eligible.iloc[-1]
    return float(row["value"]), row["available_at"]


def market_snapshot(frame: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[float, float, pd.Timestamp]:
    value, available = latest_asof(frame, cutoff)
    previous, _ = latest_asof(frame, cutoff - pd.Timedelta(days=30))
    return value, previous, available


def tender_cutoffs() -> pd.DataFrame:
    end = pd.Timestamp.now(tz="Asia/Singapore").normalize() + pd.offsets.MonthBegin(1)
    rows = []
    for month in pd.date_range(START, end, freq="MS"):
        for bidding_no, day in ((1, 1), (2, 15)):
            cutoff = month + pd.Timedelta(days=day - 1)
            if cutoff > pd.Timestamp.now(tz="Asia/Singapore"):
                continue
            rows.append({
                "tender_id": f"{month:%Y-%m}-{bidding_no}",
                "forecast_cutoff_at": cutoff,
            })
    return pd.DataFrame(rows)


def main() -> None:
    fred = {name: load_fred(series_id) for name, series_id in FRED_SERIES.items()}
    macro = {
        name: load_singstat(resource_id, series_no, lag)
        for name, (resource_id, series_no, lag) in SINGSTAT_SERIES.items()
    }
    rows = []
    for tender in tender_cutoffs().itertuples(index=False):
        cutoff = pd.Timestamp(tender.forecast_cutoff_at)
        fx, fx_old, fx_at = market_snapshot(fred["sgd_per_usd"], cutoff)
        vix, vix_old, vix_at = market_snapshot(fred["vix"], cutoff)
        yield10, yield_old, yield_at = market_snapshot(fred["us_10y_yield"], cutoff)
        brent, brent_old, brent_at = market_snapshot(fred["brent_usd"], cutoff)
        nasdaq, nasdaq_old, nasdaq_at = market_snapshot(fred["nasdaq_composite"], cutoff)
        gdp, gdp_at = latest_asof(macro["sg_real_gdp_yoy"], cutoff)
        cpi, cpi_at = latest_asof(macro["sg_cpi_yoy"], cutoff)
        unemployment, unemployment_at = latest_asof(macro["sg_unemployment_rate"], cutoff)
        rows.append({
            "tender_id": tender.tender_id,
            "forecast_cutoff_at": cutoff.isoformat(),
            "sgd_per_usd": fx,
            "sgd_per_usd_change_21d": fx / fx_old - 1.0,
            "vix": vix,
            "vix_change_21d": vix - vix_old,
            "us_10y_yield": yield10,
            "us_10y_yield_change_21d": yield10 - yield_old,
            "brent_usd": brent,
            "brent_return_21d": brent / brent_old - 1.0,
            "nasdaq_composite": nasdaq,
            "nasdaq_return_21d": nasdaq / nasdaq_old - 1.0,
            "sg_real_gdp_yoy": gdp,
            "sg_cpi_yoy": cpi,
            "sg_unemployment_rate": unemployment,
            "market_latest_available_at": max(fx_at, vix_at, yield_at, brent_at, nasdaq_at).isoformat(),
            "gdp_available_at": gdp_at.isoformat(),
            "cpi_available_at": cpi_at.isoformat(),
            "unemployment_available_at": unemployment_at.isoformat(),
        })
    output = pd.DataFrame(rows)
    validated, errors = validate_economic_features(output)
    if errors:
        raise ValueError("; ".join(errors))
    keep = list(output.columns)
    validated[keep].to_csv(OUTPUT, index=False)

    manifest_rows = []
    for feature, series_id in FRED_SERIES.items():
        manifest_rows.append({
            "feature_family": feature,
            "source_id": series_id,
            "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
            "provider": "Federal Reserve Bank of St. Louis (underlying series provider varies)",
            "frequency": "daily",
            "availability_rule": "observation date plus one calendar day, noon Singapore time",
            "revision_risk": "low for market observations; provider corrections remain possible",
            "retrieved_at": RETRIEVED_AT.isoformat(),
        })
    for feature, (resource_id, _, lag) in SINGSTAT_SERIES.items():
        manifest_rows.append({
            "feature_family": feature,
            "source_id": resource_id,
            "source_url": f"https://tablebuilder.singstat.gov.sg/api/table/tabledata/{resource_id}",
            "provider": "Singapore Department of Statistics / Ministry of Manpower",
            "frequency": "monthly" if feature == "sg_cpi_yoy" else "quarterly",
            "availability_rule": f"period end plus {lag} calendar days",
            "revision_risk": "current-vintage table may contain later revisions; no real-time vintage archive used",
            "retrieved_at": RETRIEVED_AT.isoformat(),
        })
    pd.DataFrame(manifest_rows).to_csv(MANIFEST, index=False)
    print(f"wrote {len(validated):,} tender rows with {len(ECONOMIC_FEATURE_COLUMNS)} features")


if __name__ == "__main__":
    main()
