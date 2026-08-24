#!/usr/bin/env python3
"""Build auditable brand/category dealer signals from SGCarMart OCR output."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd


MONEY_RE = re.compile(r"(?:\$\s*)?((?:[0-9]{1,3},)+[0-9]{3}|[0-9]{3,})")
DOLLAR_RE = re.compile(r"\$\s*((?:[0-9]{1,3},)+[0-9]{3}|[0-9]{3,})")
DATE_RANGE_RE = re.compile(
    r"(?:effect|effective).*?from\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s+to\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)
SHORT_DATE_RANGE_RE = re.compile(
    r"(?:valid|effect|effective).*?from\s+(\d{1,2}\s+[A-Za-z]+)(?:\s+(\d{4}))?\s*(?:to|-)\s*(\d{1,2}\s+[A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
BIDS_RE = re.compile(r"(\d+)\s*BIDS?", re.IGNORECASE)
RATE_RE = re.compile(
    r"(?:\b(?:INTEREST\s*RATE|FINANCE\s*RATE|INTEREST)\b[^%\n]{0,50}?([0-9]{1,2}(?:\.[0-9]+)?)\s*%"
    r"|([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*\b(?:INTEREST\s*RATE|FINANCE\s*RATE|INTEREST)\b)",
    re.IGNORECASE,
)


def parse_ocr(path: Path) -> list[list[dict]]:
    pages: list[list[dict]] = []
    current: list[dict] | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("###PAGE"):
            current = []
            pages.append(current)
            continue
        if raw.startswith("###ERROR") or not raw.strip() or current is None:
            continue
        fields = raw.split("\t", 4)
        if len(fields) != 5:
            continue
        try:
            x, y, width, height = map(float, fields[:4])
        except ValueError:
            continue
        current.append({"x": x, "y": y, "width": width, "height": height, "text": fields[4].strip()})
    return pages


def category_for_page(lines: list[dict]) -> tuple[str, str]:
    # Page headings live near the top; footer terms often mention both categories.
    cats = set()
    for line in lines:
        if line["y"] < 0.70:
            continue
        heading = line["text"].upper().strip()
        # Authorised dealers use variants such as "Category A", "CAT B MODELS",
        # "PRICE LIST: CATEGORY A" and "Hybrid - Category B". Keep the match
        # restricted to short top-of-page label lines so explanatory footers do
        # not create a category assignment.
        if len(heading) <= 80:
            cats.update(re.findall(r"\bCAT(?:EGORY)?\s*([AB])\b", heading))
    if cats == {"A"} or cats == {"B"}:
        return next(iter(cats)), "explicit_page_label"
    if cats == {"A", "B"}:
        return "A/B", "multiple_explicit_page_labels"
    return "Unclassified", "no_explicit_page_label"


def amount(text: str) -> int | None:
    match = MONEY_RE.search(text)
    return int(match.group(1).replace(",", "")) if match else None


def explicit_dollar_amount(text: str) -> int | None:
    match = DOLLAR_RE.search(text)
    return int(match.group(1).replace(",", "")) if match else None


def parse_date(raw_date: str) -> str:
    for date_format in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw_date, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def page_features(lines: list[dict]) -> dict:
    text = "\n".join(line["text"] for line in lines)
    upper = text.upper()
    model_header_y = max(
        (line["y"] for line in lines if line["text"].upper().strip() in {"MODEL", "MODELS"}),
        default=0.88,
    )
    price_candidates = []
    for line in lines:
        value = amount(line["text"])
        if value is None or value < 80_000 or value > 1_500_000:
            continue
        if "COE" in line["text"].upper():
            continue
        if 0.20 < line["y"] < model_header_y - 0.018:
            price_candidates.append((value, line["x"]))

    # Price columns repeat at a stable horizontal position. This drops one-off postal codes
    # and other large numbers without making model-level claims.
    x_counts = Counter(round(x / 0.025) * 0.025 for _, x in price_candidates)
    recurring_x = {x for x, count in x_counts.items() if count >= 2}
    if recurring_x:
        prices = sorted(value for value, x in price_candidates if min(abs(x - cluster) for cluster in recurring_x) <= 0.02)
    else:
        prices = sorted(value for value, _ in price_candidates)
    rebate_lines = [
        line for line in lines
        if "REBATE" in line["text"].upper() and "COE" in line["text"].upper()
    ]
    explicit_rebate_amounts = []
    for line in lines:
        value = amount(line["text"])
        near_rebate_label = any(abs(line["y"] - rebate_line["y"]) <= 0.028 for rebate_line in rebate_lines)
        if value and 40_000 <= value <= 180_000 and near_rebate_label:
            explicit_rebate_amounts.append(value)

    bid_matches = [int(value) for value in BIDS_RE.findall(text)]
    has_non_guaranteed = "NON-GUARANTEED" in upper or "NON GUARANTEED" in upper
    without_non = upper.replace("NON-GUARANTEED", "").replace("NON GUARANTEED", "")
    has_guaranteed = "GUARANTEED" in without_non
    if has_non_guaranteed and has_guaranteed:
        guarantee = "mixed guaranteed and non-guaranteed packages"
    elif has_guaranteed:
        guarantee = "guaranteed"
    elif has_non_guaranteed:
        guarantee = "non-guaranteed"
    else:
        guarantee = "not stated"

    flattened = text.replace("\n", " ")
    date_match = DATE_RANGE_RE.search(flattened)
    valid_from = valid_to = ""
    if date_match:
        valid_from = parse_date(date_match.group(1))
        valid_to = parse_date(date_match.group(2))
    else:
        short_match = SHORT_DATE_RANGE_RE.search(flattened)
        if short_match:
            end_year = short_match.group(4)
            start_year = short_match.group(2) or end_year
            valid_from = parse_date(f"{short_match.group(1)} {start_year}")
            valid_to = parse_date(f"{short_match.group(3)} {end_year}")

    promo_lines = [line["text"] for line in lines if any(word in line["text"].upper() for word in ("PROMOTION", "ROADSHOW"))]
    discount_candidates = []
    for line in lines:
        if "DISCOUNT" in line["text"].upper():
            value = explicit_dollar_amount(line["text"])
            if value and value < 80_000:
                discount_candidates.append(value)
    finance_lines = [line["text"] for line in lines if any(word in line["text"].upper() for word in ("FINANCE", "INTEREST RATE", "IN-HOUSE"))]
    trade_lines = [line["text"] for line in lines if "TRADE-IN" in line["text"].upper() or "TRADE IN" in line["text"].upper()]
    finance_label_rows = [
        line for line in lines
        if re.match(r"^FINANCE\s+(?:REBATE|DISCOUNT)\b", line["text"].upper().strip())
    ]
    trade_label_rows = [
        line for line in lines
        if re.match(r"^TRADE[- ]IN\s+(?:REBATE|DISCOUNT)\b", line["text"].upper().strip())
    ]
    finance_amounts = []
    trade_amounts = []
    for line in lines:
        value = explicit_dollar_amount(line["text"])
        if not value or value >= 80_000 or "DEPOSIT" in line["text"].upper():
            continue
        if any(abs(line["y"] - label["y"]) <= 0.012 and line["x"] >= label["x"] - 0.02 for label in finance_label_rows):
            finance_amounts.append(value)
        if any(abs(line["y"] - label["y"]) <= 0.012 and line["x"] >= label["x"] - 0.02 for label in trade_label_rows):
            trade_amounts.append(value)
    rates = []
    for line in lines:
        for match in RATE_RE.finditer(line["text"]):
            value = float(match.group(1) or match.group(2))
            if 0.1 <= value <= 15:
                rates.append(value)

    return {
        "advertised_price_min": min(prices) if prices else None,
        "advertised_price_median": int(pd.Series(prices).median()) if prices else None,
        "advertised_price_max": max(prices) if prices else None,
        "advertised_price_count": len(prices),
        "coe_rebate_level": int(pd.Series(explicit_rebate_amounts).median()) if explicit_rebate_amounts else None,
        "guaranteed_coe_terms": guarantee,
        "coe_bid_count": Counter(bid_matches).most_common(1)[0][0] if bid_matches else None,
        "promotion_discount_amount": max(discount_candidates) if discount_candidates else None,
        "finance_incentive_value": max(finance_amounts) if finance_amounts else None,
        "trade_in_incentive_value": max(trade_amounts) if trade_amounts else None,
        "finance_rate_pct": float(pd.Series(rates).median()) if rates else None,
        "finance_incentive_text": " | ".join(dict.fromkeys(finance_lines))[:1000],
        "trade_in_incentive_text": " | ".join(dict.fromkeys(trade_lines))[:1000],
        "promotion_name": " | ".join(dict.fromkeys(promo_lines))[:500],
        "valid_from": valid_from,
        "promotion_deadline": valid_to,
    }


def market_share_table(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["make"] = data["make"].astype(str).str.upper().str.strip()
    data["month"] = pd.PeriodIndex(data["month"], freq="M")
    monthly = data.groupby(["month", "make"], as_index=False)["number"].sum()
    return monthly


def trailing_share(monthly: pd.DataFrame, brand: str, document_date: str) -> tuple[float | None, float | None, float | None, str]:
    aliases = {"BMW": "B.M.W.", "MERCEDES-BENZ": "MERCEDES BENZ"}
    make = aliases.get(brand.upper(), brand.upper())
    cutoff = pd.Period(document_date[:7], freq="M") - 1
    start = cutoff - 11
    window = monthly[(monthly["month"] >= start) & (monthly["month"] <= cutoff)]
    denominator = float(window["number"].sum())
    numerator = float(window.loc[window["make"] == make, "number"].sum())
    if denominator <= 0:
        return None, None, None, ""
    return numerator / denominator, numerator, denominator, f"{start} to {cutoff}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ocr_dir", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("lta_csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = {(row["dealer_id"], row["document_date"]): row for row in csv.DictReader(handle)}
    monthly = market_share_table(args.lta_csv)
    rows = []
    for ocr_path in sorted(args.ocr_dir.glob("*/*.tsv")):
        dealer_id = ocr_path.parent.name.split("_", 1)[0]
        document_date = ocr_path.stem
        source = manifest.get((dealer_id, document_date))
        if not source:
            continue
        for page_number, lines in enumerate(parse_ocr(ocr_path), start=1):
            category, category_method = category_for_page(lines)
            features = page_features(lines)
            if not any((features["advertised_price_count"], features["coe_rebate_level"], features["promotion_name"], features["finance_incentive_text"], features["trade_in_incentive_text"])):
                continue
            share, numerator, denominator, window = trailing_share(monthly, source["brand"], document_date)
            rows.append({
                "observed_at": f"{document_date}T00:00:00+08:00",
                "source_document_date": document_date,
                "dealer_id": int(dealer_id),
                "dealer": source["dealer_name"],
                "brand": source["brand"],
                "category": category,
                "category_method": category_method,
                "observation_level": "brand_category_pricelist_page_summary",
                "source_page": page_number,
                **features,
                "market_share_weight": share,
                "market_share_registrations": numerator,
                "market_share_total_registrations": denominator,
                "market_share_window": window,
                "market_share_source": "LTA Monthly New Registration of Cars by Make",
                "source_url": source["source_url"] + f"#page={page_number}",
                "source_sha256": source["sha256"],
                "retrieved_at_utc": source["retrieved_at_utc"],
                "extraction_method": "Apple Vision OCR + deterministic page-summary parser",
                "quality_flag": "model_eligible" if category in {"A", "B"} and features["advertised_price_count"] else "review_or_context_only",
            })

    frame = pd.DataFrame(rows).sort_values(["brand", "category", "source_document_date", "source_page"])
    frame["advertised_price_change"] = frame.groupby(["brand", "category"])["advertised_price_median"].diff()
    frame["advertised_price_change_pct"] = frame.groupby(["brand", "category"])["advertised_price_median"].pct_change(fill_method=None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print(f"wrote {len(frame)} rows ({(frame.quality_flag == 'model_eligible').sum()} model-eligible) to {args.output}")


if __name__ == "__main__":
    main()
