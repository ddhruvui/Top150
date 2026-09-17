"""Borrow fees: per-name iBorrowDesk rate where the table has one, else the GC
default (cost.borrow_gc_bps_yr — 0.3%/yr on core105). Charged on SHORT legs only,
so it is inert while the book is long_only: these tests pin the mechanics for the
day shorting is switched back on.
"""
import json

import pandas as pd
import yaml

from src.backtest.costs import CostModel
from src.data.borrow import borrow_table, watchlist_fees

GC = 30.0                                   # 0.3%/yr, configs/system_core105.yaml
TBL = pd.DataFrame({
    "date": pd.to_datetime(["2024-01-02", "2024-03-01", "2024-03-05", "2024-03-06"]),
    "ticker": ["META", "META", "META", "NULLY"],
    "fee_bps_yr": [54.9, 120.0, None, None],     # the vendor leaves NULLs on no-quote days
})


def _cm():
    return CostModel(per_trade_bps=15, borrow_gc_bps_yr=GC, borrow_table=TBL)


def test_per_name_fee_is_used_and_is_the_last_quote_on_or_before_the_date():
    cm = _cm()
    assert cm.borrow_fee_bps("META", "2024-02-01") == 54.9
    assert cm.borrow_fee_bps("META", "2024-03-01") == 120.0
    assert cm.borrow_fee_bps("META", "2024-06-01") == 120.0     # carries forward


def test_gc_default_covers_everything_the_table_does_not():
    cm = _cm()
    assert cm.borrow_fee_bps("SPY", "2024-06-01") == GC          # ETFs are not in it
    assert cm.borrow_fee_bps("META", "2015-01-01") == GC         # before the first quote
    assert cm.borrow_fee_bps(None, None) == GC


def test_null_vendor_fees_fall_back_instead_of_poisoning_the_cost():
    cm = _cm()
    # NULL rows are dropped: META keeps its 2024-03-01 quote rather than going NaN,
    # and a name whose only row is NULL falls back to GC.
    assert cm.borrow_fee_bps("META", "2024-03-10") == 120.0
    assert cm.borrow_fee_bps("NULLY", "2024-03-10") == GC
    assert CostModel(borrow_gc_bps_yr=GC, borrow_table=TBL[TBL["fee_bps_yr"].isna()]) \
        .borrow_fee_bps("NULLY", "2024-03-10") == GC


def test_borrow_is_charged_on_shorts_only():
    cm = _cm()
    long_rt = cm.round_trip_frac(side=1, holding_days=10, ticker="META", date="2024-03-01")
    assert abs(long_rt - 2 * cm.leg_frac()) < 1e-12              # no borrow leg
    short_rt = cm.round_trip_frac(side=-1, holding_days=10, ticker="META", date="2024-03-01")
    assert abs(short_rt - (2 * cm.leg_frac() + 120.0 / 1e4 / 252 * 10)) < 1e-12
    short_gc = cm.round_trip_frac(side=-1, holding_days=10, ticker="SPY", date="2024-03-01")
    assert abs(short_gc - (2 * cm.leg_frac() + GC / 1e4 / 252 * 10)) < 1e-12


def test_core105_config_sets_the_03_percent_default():
    cfg = yaml.safe_load(open("configs/system_core105.yaml"))
    assert float(cfg["cost"]["borrow_gc_bps_yr"]) == GC


# ---- the watchlist tree: where SPY and QQQ fees come from --------------------
# m1/borrow_fees is built from data_borrow/history/, which holds equities only.
# SPY and QQQ live in data_borrow/watchlist/history/<TICKER>.json.
M1 = pd.DataFrame({
    "ticker": ["BRK-B", "BRK-B", "NVDA"],
    "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-02"]),
    "fee_bps_yr": [25.0, 26.0, 25.0],
})


def _tree(tmp_path, files):
    hist = tmp_path / "watchlist" / "history"
    hist.mkdir(parents=True)
    for name, recs in files.items():
        (hist / f"{name}.json").write_text(json.dumps(recs))
    return tmp_path


def test_watchlist_rows_are_read(tmp_path):
    d = _tree(tmp_path, {"SPY": [
        {"ticker": "SPY", "date": "2015-07-13", "fee_bps_yr": 50.5},
        {"ticker": "SPY", "date": "2026-09-11", "fee_bps_yr": 25.0},
        {"ticker": "SPY", "date": "2026-09-12", "fee_bps_yr": None},   # no quote
    ]})
    wl = watchlist_fees(d)
    assert list(wl.columns) == ["ticker", "date", "fee_bps_yr"]
    assert len(wl) == 2 and set(wl["ticker"]) == {"SPY"}


def test_etfs_get_their_own_fee_instead_of_the_gc_default(tmp_path):
    d = _tree(tmp_path, {"SPY": [{"ticker": "SPY", "date": "2024-01-02", "fee_bps_yr": 41.0}],
                         "QQQ": [{"ticker": "QQQ", "date": "2024-01-02", "fee_bps_yr": 37.0}]})
    cm = CostModel(borrow_gc_bps_yr=GC, borrow_table=borrow_table(M1, d))
    assert cm.borrow_fee_bps("SPY", "2024-06-01") == 41.0
    assert cm.borrow_fee_bps("QQQ", "2024-06-01") == 37.0
    assert cm.borrow_fee_bps("NVDA", "2024-06-01") == 25.0      # still from M1
    assert cm.borrow_fee_bps("NOPE", "2024-06-01") == GC


def test_m1_wins_where_both_carry_the_same_day(tmp_path):
    d = _tree(tmp_path, {"BRK-B": [
        {"ticker": "BRK-B", "date": "2024-01-03", "fee_bps_yr": 999.0},   # same day as M1
        {"ticker": "BRK-B", "date": "2024-01-04", "fee_bps_yr": 27.0},    # M1 lacks it
    ]})
    tbl = borrow_table(M1, d)
    cm = CostModel(borrow_gc_bps_yr=GC, borrow_table=tbl)
    assert cm.borrow_fee_bps("BRK-B", "2024-01-03") == 26.0     # M1 value, not 999
    assert cm.borrow_fee_bps("BRK-B", "2024-01-04") == 27.0     # filled from watchlist


def test_missing_tree_is_not_an_error(tmp_path):
    assert watchlist_fees(None).empty and watchlist_fees(tmp_path).empty
    tbl = borrow_table(M1, tmp_path)
    assert len(tbl) == len(M1)
    assert borrow_table(None, tmp_path).empty
