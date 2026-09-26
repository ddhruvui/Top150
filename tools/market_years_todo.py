#!/usr/bin/env python3
"""Which market_prices year-parts need (re)building — and step 1 for one year.

Used by the market job in scripts/pod_bootstrap_predict.sh when the source tape
has no m1x/ build to reuse, so this project keeps its own under results/Core105.

    python tools/market_years_todo.py < listing
        stdin: `aws s3 ls data/eod_bulk/US/` output. Prints the years to
        (re)build, space-separated: every year whose day-file count differs
        from MARKER (market_prices/_built.json), plus always the newest year —
        the newest day-file can still be filling when it is first listed, and a
        count-only marker would never notice it grow.

    FORCE_YEAR=2026 python tools/market_years_todo.py --step1
        drops FORCE_YEAR from _built.json, then runs build_market.py's step 1,
        which parses whatever day-files sit in EOD_BULK_DIR (the caller pulls
        exactly one year there). Without the drop, step 1 would skip a year whose
        file count happened to be unchanged.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

DAY_FILE = re.compile(r"\s(\d{4})-\d\d-\d\d\.json(\.gz)?\s*$")


def years_todo(listing_lines, built: dict) -> list[str]:
    counts = collections.Counter()
    for ln in listing_lines:
        m = DAY_FILE.search(ln)
        if m:
            counts[m.group(1)] += 1
    todo = {y for y, n in counts.items() if built.get(y) != n}
    if counts:
        todo.add(max(counts))
    return sorted(todo)


def _load_marker(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def step1_for(year: str) -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "data" / "build_market.py"
    spec = importlib.util.spec_from_file_location("build_market", src)
    bm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bm)
    marker = bm.MARKET_DIR / "market_prices" / "_built.json"
    if marker.exists():
        built = json.loads(marker.read_text())
        built.pop(year, None)
        marker.write_text(json.dumps(built))
    bm.step1_market_prices()


def main() -> int:
    if "--step1" in sys.argv[1:]:
        step1_for(os.environ["FORCE_YEAR"])
        return 0
    print(" ".join(years_todo(sys.stdin, _load_marker(os.environ.get("MARKER", "")))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
