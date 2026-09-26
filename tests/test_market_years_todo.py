"""Own market_prices build: which years the market job re-parses from eod_bulk.

The source tape carries no m1x/ build, so the market job keeps its own
market_prices parts under results/Core105 and must bring them up to date each
run. Plain reuse froze the panel at the last build date (G-02 would then refuse
every later book); re-parsing all ~30 GiB daily is not an option either.
"""
import json

from tools.market_years_todo import step1_for, years_todo


def _ls(*names):
    """`aws s3 ls` lines for the given day-file names."""
    return [f"2026-09-26 00:50:10    6148540 {n}\n" for n in names]


LISTING = _ls("2024-12-30.json", "2024-12-31.json",
              "2025-01-02.json", "2025-01-03.json.gz",
              "2026-09-24.json", "2026-09-25.json")


def test_from_scratch_builds_every_year():
    assert years_todo(LISTING, {}) == ["2024", "2025", "2026"]


def test_daily_run_rebuilds_only_the_newest_year():
    # every count matches: still re-parse the newest year, whose last file may
    # have grown since it was first parsed
    assert years_todo(LISTING, {"2024": 2, "2025": 2, "2026": 2}) == ["2026"]


def test_new_session_is_picked_up():
    listing = LISTING + _ls("2026-09-28.json")
    assert years_todo(listing, {"2024": 2, "2025": 2, "2026": 2}) == ["2026"]


def test_vendor_backfill_of_an_old_year_is_rebuilt():
    listing = LISTING + _ls("2024-12-27.json")
    assert years_todo(listing, {"2024": 2, "2025": 2, "2026": 2}) == ["2024", "2026"]


def test_non_day_files_are_ignored():
    listing = LISTING + ["2026-09-26 04:51:18       812 _run.json\n",
                         "                           PRE logs/\n"]
    assert years_todo(listing, {"2024": 2, "2025": 2, "2026": 2}) == ["2026"]


def test_empty_listing_selects_nothing():
    assert years_todo([], {"2026": 184}) == []


def test_step1_reparses_a_year_whose_count_is_unchanged(tmp_path, monkeypatch):
    """The newest year's file count can be unchanged while its last file grew:
    --step1 must drop the year from _built.json so step 1 does not skip it."""
    bulk, mkt = tmp_path / "bulk", tmp_path / "mkt"
    bulk.mkdir()
    rows = [{"code": "AAPL", "date": "2026-09-25", "open": 1, "high": 1, "low": 1,
             "close": 1.0, "adjusted_close": 1.0, "volume": 10}]
    (bulk / "2026-09-25.json").write_text(json.dumps(rows))
    (mkt / "market_prices").mkdir(parents=True)
    (mkt / "market_prices" / "_built.json").write_text(json.dumps({"2025": 250, "2026": 1}))
    monkeypatch.setenv("EOD_BULK_DIR", str(bulk))
    monkeypatch.setenv("MARKET_DIR", str(mkt))

    rows.append(dict(rows[0], code="MSFT"))           # the file filled in
    (bulk / "2026-09-25.json").write_text(json.dumps(rows))
    step1_for("2026")

    import pandas as pd
    part = pd.read_parquet(mkt / "market_prices" / "part-2026.parquet")
    assert sorted(part["ticker"]) == ["AAPL", "MSFT"]
    built = json.loads((mkt / "market_prices" / "_built.json").read_text())
    assert built == {"2025": 250, "2026": 1}          # other years untouched
