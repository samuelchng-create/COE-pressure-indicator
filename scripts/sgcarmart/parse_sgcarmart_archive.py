#!/usr/bin/env python3
"""Extract SGCarMart dealer archive metadata from a saved public price-list page."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    raw = args.html.read_text(encoding="utf-8")
    # SGCarMart renamed this Next.js payload field from ``adDealerList`` to
    # ``adList`` in October 2026. Accept both names so historical snapshots and
    # current refreshes remain reproducible.
    markers = ('adDealerList\\":', 'adList\\":')
    marker = next((candidate for candidate in markers if candidate in raw), None)
    if marker is None:
        raise ValueError("authorised-dealer list array not found")
    start = raw.index(marker) + len(marker)
    if raw[start] != "[":
        raise ValueError("adDealerList array not found")
    depth = 0
    end = None
    for index in range(start, len(raw)):
        if raw[index] == "[":
            depth += 1
        elif raw[index] == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError("unterminated adDealerList array")

    encoded = raw[start:end]
    dealers = json.loads(encoded.replace(r'\"', '"'))
    for dealer in dealers:
        dealer["pricelist_dates"] = dealer.pop("pricelistDates")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dealers, indent=2), encoding="utf-8")
    print(f"wrote {len(dealers)} dealers to {args.output}")


if __name__ == "__main__":
    main()
