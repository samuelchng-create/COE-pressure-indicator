#!/usr/bin/env python3
"""Map SGCarMart page summaries into the app's versioned dealer schema."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


BRAND_GROUPS = {
    "Toyota": "Toyota / Lexus",
    "Lexus": "Toyota / Lexus",
    "Omoda": "Chery / Omoda / Jaecoo",
    "Jaecoo": "Chery / Omoda / Jaecoo",
    "GAC": "GAC / Aion",
    "Aion": "GAC / Aion",
}


def evidenced_available_at(row: pd.Series) -> str:
    """Use conservative end-of-day unless collection proves earlier availability."""
    end_of_day = pd.Timestamp(f"{row.source_document_date}T23:59:59", tz="Asia/Singapore")
    retrieved = pd.Timestamp(row.retrieved_at_utc)
    if retrieved.tzinfo is None:
        retrieved = retrieved.tz_localize("UTC")
    if retrieved < end_of_day:
        return retrieved.tz_convert("Asia/Singapore").floor("s").isoformat()
    return end_of_day.isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    raw = pd.read_csv(args.input)
    raw = raw[raw["quality_flag"].eq("model_eligible")].copy()
    category_map = {"A": "Category A", "B": "Category B"}
    output = pd.DataFrame()
    output["observation_id"] = raw.apply(
        lambda row: f"sgcm-{int(row.dealer_id)}-{row.source_document_date}-p{int(row.source_page)}-{row.category.lower()}",
        axis=1,
    )
    output["observed_at"] = raw["observed_at"]
    output["available_at"] = raw.apply(evidenced_available_at, axis=1)
    output["retrieved_at"] = raw["retrieved_at_utc"]
    output["source_url"] = raw["source_url"]
    output["source_type"] = "SGCarMart archived authorised-dealer price list"
    output["category"] = raw["category"].map(category_map)
    output["brand"] = raw["brand"].map(BRAND_GROUPS).fillna(raw["brand"])
    output["model"] = "Price-list page summary"
    output["variant"] = raw["source_page"].map(lambda value: f"PDF page {int(value)}")
    output["advertised_price"] = raw["advertised_price_median"]
    output["previous_advertised_price"] = raw["advertised_price_median"] - raw["advertised_price_change"]
    output["coe_rebate_level"] = raw["coe_rebate_level"]
    output["guaranteed_coe"] = raw["guaranteed_coe_terms"].isin(
        ["guaranteed", "mixed guaranteed and non-guaranteed packages"]
    )
    output["guaranteed_coe_bid_count"] = raw["coe_bid_count"]
    output["guaranteed_coe_terms"] = raw["guaranteed_coe_terms"]
    output["finance_rate_pct"] = raw["finance_rate_pct"]
    output["finance_incentive_value"] = raw["finance_incentive_value"]
    output["finance_incentive_terms"] = raw["finance_incentive_text"]
    output["trade_in_incentive_value"] = raw["trade_in_incentive_value"]
    output["trade_in_incentive_terms"] = raw["trade_in_incentive_text"]
    output["cash_discount_value"] = raw["promotion_discount_amount"]
    output["other_incentive_value"] = pd.NA
    output["promotion_deadline"] = raw["promotion_deadline"]
    output["promotion_name"] = raw["promotion_name"]
    output["roadshow_name"] = raw["promotion_name"].where(
        raw["promotion_name"].fillna("").str.contains("roadshow", case=False)
    )
    output["roadshow_start"] = raw["valid_from"].where(output["roadshow_name"].notna())
    output["roadshow_end"] = raw["promotion_deadline"].where(output["roadshow_name"].notna())
    output["market_share_weight"] = raw["market_share_weight"]
    output["currency"] = "SGD"
    output["notes"] = raw.apply(
        lambda row: (
            f"source_marque={row.brand}; {row.observation_level}; {row.category_method}; "
            f"price_count={int(row.advertised_price_count)}; "
            f"price_range={row.advertised_price_min}-{row.advertised_price_max}; "
            f"finance_rate_pct={row.finance_rate_pct}; finance={row.finance_incentive_text}; "
            f"trade_in={row.trade_in_incentive_text}; sha256={row.source_sha256}; "
            "retrospective archive reconstruction; date-only available_at is conservatively set to end-of-day "
            "unless the recorded collection time proves earlier public availability."
        ),
        axis=1,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"wrote {len(output)} eligible observations to {args.output}")


if __name__ == "__main__":
    main()
