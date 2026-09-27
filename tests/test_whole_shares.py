"""Whole shares only (2026-09-17): the order file never contains a fractional
quantity, and a slot that comes to less than one share produces no order at
all — on either side."""
import numpy as np
import pandas as pd

from src.config import load_config
from src.live.orders import generate_orders, whole_shares


def test_whole_shares_floor_and_sign():
    assert whole_shares(0.05, 100_000, 1234.0) == 4          # 4.05 -> 4
    assert whole_shares(-0.05, 100_000, 1234.0) == -4        # short: -|shares|
    assert whole_shares(0.03, 100_000, 5200.0) == 0          # 0.58 of a share -> none
    assert whole_shares(0.0, 100_000, 50.0) == 0
    assert whole_shares(0.1, 100_000, np.nan) == 0
    assert whole_shares(0.1, 100_000, 0.0) == 0


def test_sub_share_slots_produce_no_order_and_quantities_are_integers():
    cfg, _ = load_config('configs/system_core105.yaml')
    tw = pd.Series({"BIG": 0.03, "BIGS": -0.03, "OK": 0.03, "OKS": -0.03})
    cur = pd.Series(0, index=tw.index)
    px = pd.Series({"BIG": 5200.0, "BIGS": 5200.0, "OK": 123.45, "OKS": 123.45})
    sig = pd.Series(0.02, index=tw.index)
    orders = generate_orders(tw, cur, px, 100_000.0, sig, cfg)
    tickers = {o.ticker for o in orders}
    assert "BIG" not in tickers and "BIGS" not in tickers     # under one share: nothing
    assert tickers == {"OK", "OKS"}
    for o in orders:
        assert isinstance(o.quantity, int) and o.quantity >= 1
    moo = {o.ticker: o for o in orders if o.order_type == "MOO"}
    assert moo["OK"].quantity == 24 and moo["OK"].action == "BUY"     # floor(3000/123.45)
    assert moo["OKS"].quantity == 24 and moo["OKS"].action == "SELL"
    # the barrier orders carry the same whole quantity as their entry
    for t in ("OK", "OKS"):
        assert {o.quantity for o in orders if o.ticker == t} == {24}
