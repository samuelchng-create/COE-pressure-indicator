#!/usr/bin/env python3
"""Export auditable trailing LTA registration weights for archived brands."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ALIASES = {"BMW": "B.M.W.", "MERCEDES-BENZ": "MERCEDES BENZ"}
SOURCE_URL = "https://datamall.lta.gov.sg/content/datamall/en/static-data.html"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("lta_csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    registrations = pd.read_csv(args.lta_csv)
    registrations["month"] = pd.PeriodIndex(registrations["month"], freq="M")
    registrations["make"] = registrations["make"].astype(str).str.upper().str.strip()
    monthly = registrations.groupby(["month", "make"], as_index=False)["number"].sum()

    brands = manifest[["brand"]].drop_duplicates().sort_values("brand")["brand"].tolist()
    first_month = pd.Period(manifest["document_date"].min()[:7], freq="M")
    last_source_month = pd.Period(manifest["document_date"].max()[:7], freq="M")
    # A weight is available only when the preceding complete month exists in LTA data.
    last_month = min(last_source_month, monthly["month"].max() + 1)
    rows = []
    for observation_month in pd.period_range(first_month, last_month, freq="M"):
        trailing_end = observation_month - 1
        trailing_start = trailing_end - 11
        window = monthly[monthly["month"].between(trailing_start, trailing_end)]
        denominator = float(window["number"].sum())
        if denominator <= 0:
            continue
        for brand in brands:
            lta_make = ALIASES.get(brand.upper(), brand.upper())
            numerator = float(window.loc[window["make"].eq(lta_make), "number"].sum())
            rows.append(
                {
                    "observation_month": str(observation_month),
                    "brand": brand,
                    "lta_make": lta_make,
                    "trailing_12m_start": str(trailing_start),
                    "trailing_12m_end": str(trailing_end),
                    "brand_registrations": numerator,
                    "all_make_registrations": denominator,
                    "market_share_weight": numerator / denominator,
                    "source_url": SOURCE_URL,
                }
            )

    output = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"wrote {len(output)} rows for {len(brands)} brands to {args.output}")


if __name__ == "__main__":
    main()
