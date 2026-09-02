#!/usr/bin/env python3
"""Render and OCR SGCarMart archive PDFs, resuming from existing OCR files."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ocr-binary", default="/private/tmp/sgc-ocr")
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--idle-rounds", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    idle = 0
    processed = 0
    while True:
        pending = []
        for pdf in sorted(args.corpus.glob("*/*.pdf")):
            relative = pdf.relative_to(args.corpus).with_suffix(".tsv")
            target = args.output / relative
            reusable = (
                target.exists()
                and target.stat().st_size > 0
                and not target.read_text(encoding="utf-8", errors="ignore").startswith("###ERROR")
            )
            if not reusable:
                pending.append((pdf, target))
        if not pending:
            if not args.follow or idle >= args.idle_rounds:
                break
            idle += 1
            time.sleep(10)
            continue
        idle = 0
        def process(item: tuple[Path, Path]) -> tuple[Path, bool]:
            pdf, target = item
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="sgcarmart-ocr-") as tmp:
                prefix = Path(tmp) / "page"
                render = subprocess.run(
                    ["pdftoppm", "-png", "-r", "180", str(pdf), str(prefix)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                images = sorted(Path(tmp).glob("page-*.png"))
                if render.returncode != 0 or not images:
                    target.write_text(f"###ERROR render_failed returncode={render.returncode}\n", encoding="utf-8")
                    return pdf, False
                result = subprocess.run(
                    [args.ocr_binary, *map(str, images)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "###PAGE" not in result.stdout:
                    target.write_text(f"###ERROR ocr_failed {result.stderr}\n", encoding="utf-8")
                    return pdf, False
                target.write_text(result.stdout, encoding="utf-8")
            return pdf, True

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(process, item) for item in pending]
            for future in as_completed(futures):
                pdf, succeeded = future.result()
                processed += 1
                status = "ocr" if succeeded else "ocr_error"
                print(f"{status}={processed} {pdf.relative_to(args.corpus)}", flush=True)


if __name__ == "__main__":
    main()
