#!/usr/bin/env python3
"""Download a bounded, reproducible SGCarMart pricelist archive corpus."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# Twelve high-registration passenger-car brands. Pages still enter the model
# only when the deterministic parser finds an explicit Cat A/B page label and
# advertised prices; mixed-category documents remain auditable context.
SELECTED_IDS = {4, 13, 14, 18, 24, 25, 29, 42, 44, 81, 86, 123}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dealers", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-08-24")
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()

    dealers = json.loads(args.dealers.read_text(encoding="utf-8"))
    selected = [dealer for dealer in dealers if dealer["id"] in SELECTED_IDS]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "download_manifest.csv"
    existing = {}
    if manifest_path.exists():
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[(int(row["dealer_id"]), row["document_date"])] = row

    jobs = []
    for dealer in selected:
        for document_date in dealer["pricelist_dates"]:
            if args.start <= document_date <= args.end:
                jobs.append((dealer, document_date))
    jobs.sort(key=lambda item: (item[1], item[0]["id"]))

    fieldnames = [
        "dealer_id", "dealer_name", "brand", "document_date", "source_url",
        "local_path", "http_status", "bytes", "sha256", "retrieved_at_utc", "error",
    ]
    rows = list(existing.values())
    for row in rows:
        if row["http_status"] == "200" and not row.get("error"):
            row["error"] = "none"
    rows.sort(key=lambda row: (row["document_date"], int(row["dealer_id"])))

    def write_manifest() -> None:
        with manifest_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    write_manifest()
    complete = {(int(row["dealer_id"]), row["document_date"]) for row in rows if row["http_status"] == "200"}
    print(f"planned={len(jobs)} already_complete={len(complete)}", flush=True)

    for sequence, (dealer, document_date) in enumerate(jobs, start=1):
        key = (dealer["id"], document_date)
        if key in complete:
            continue
        url = f"https://media.i-sgcm.com/public/new-cars/pricelist/{dealer['id']}/{document_date}.pdf"
        brand_dir = args.output_dir / f"{dealer['id']}_{dealer['brand'].lower().replace(' ', '_')}"
        brand_dir.mkdir(parents=True, exist_ok=True)
        target = brand_dir / f"{document_date}.pdf"
        status = ""
        error = ""
        size = ""
        checksum = ""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "COE-pressure-indicator-research/0.2"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
                status = str(response.status)
            target.write_bytes(payload)
            size = str(len(payload))
            checksum = sha256(target)
        except urllib.error.HTTPError as exc:
            status = str(exc.code)
            error = str(exc)
        except Exception as exc:  # keep the manifest auditable and resumable
            error = f"{type(exc).__name__}: {exc}"

        row = {
            "dealer_id": dealer["id"],
            "dealer_name": dealer["name"],
            "brand": dealer["brand"],
            "document_date": document_date,
            "source_url": url,
            "local_path": str(target),
            "http_status": status,
            "bytes": size,
            "sha256": checksum,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": error or "none",
        }
        rows = [r for r in rows if (int(r["dealer_id"]), r["document_date"]) != key]
        rows.append(row)
        rows.sort(key=lambda r: (r["document_date"], int(r["dealer_id"])))
        write_manifest()
        print(f"{sequence}/{len(jobs)} {dealer['brand']} {document_date} status={status or 'error'}", flush=True)
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
