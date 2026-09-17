"""Borrow fees: per-name iBorrowDesk rate where the table has one, else the GC
default (cost.borrow_gc_bps_yr — 0.3%/yr on core105). Charged on SHORT legs only,
so it is inert while the book is long_only: these tests pin the mechanics for the
day shorting is switched back on.
"""
import pandas as pd
import yaml

from src.backtest.costs import CostModel

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
