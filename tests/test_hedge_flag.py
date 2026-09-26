"""port.hedge is ONE setting read by every path.

Until 2026-09-26 only predict consulted it; evaluate_book took construct_targets'
hedge=True default, so stage1/stage2 (and the G-11 gates built on them) reported a
beta-matched short-SPY book while the live book had no index leg at all.
"""
import glob

import numpy as np
import pandas as pd
import yaml

from src.config import Cfg
from src.portfolio.construct import construct_targets, hedge_enabled, HEDGE_COL


def _cfg(hedge):
    port = {"hedge": hedge} if hedge is not None else {}
    return Cfg({"port": port})


def test_none_means_no_hedge_whatever_the_spelling():
    for v in ("none", "None", " NONE "):
        assert hedge_enabled(_cfg(v)) is False


def test_anything_else_keeps_the_hedge():
    assert hedge_enabled(_cfg("short_SPY_beta_matched")) is True
    assert hedge_enabled(_cfg(None)) is True          # absent -> the blueprint default


def _targets(hedge):
    dates = pd.bdate_range("2024-01-02", periods=12)
    cols = ["AAA", "BBB", "CCC"]
    decile = pd.DataFrame(10, index=dates, columns=cols)         # all selected
    mask = pd.DataFrame(True, index=dates, columns=cols)
    sigma = pd.DataFrame(0.02, index=dates, columns=cols)
    beta = pd.DataFrame(1.0, index=dates, columns=cols)
    return construct_targets(decile, mask, sigma, beta, None, tranches=3,
                             single_name_cap=0.5, hedge=hedge)


def test_hedge_column_follows_the_flag():
    assert HEDGE_COL in _targets(True).columns
    off = _targets(False)
    assert HEDGE_COL not in off.columns
    assert (off.to_numpy() >= 0).all()                # nothing short without the leg


def test_the_hedge_leg_is_short_when_on():
    on = _targets(True)
    held = on.drop(columns=[HEDGE_COL]).sum(axis=1)
    assert (on[HEDGE_COL][held > 0] < 0).all()        # short against the long book
    assert np.allclose(on[HEDGE_COL], -held)          # beta 1.0 -> exactly -gross


def test_every_shipped_config_asks_for_no_hedge():
    """If one ever flips, the stage reports and the live book must move together."""
    for f in sorted(glob.glob("configs/system*.yaml")):
        cfg = yaml.safe_load(open(f))
        assert str(cfg["port"]["hedge"]).lower() == "none", f
