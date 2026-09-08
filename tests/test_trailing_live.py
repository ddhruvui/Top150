"""Trailing stop wiring (adopted 2026-09-08): config -> engine options -> the
ONE barrier engine -> the M18 order file. A config without the key, or
trail_m 0, is the original engine bit-for-bit."""
import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.engines.barriers_event import engine_opts_from_cfg, run_event_backtest
from src.config import Cfg, load_config
from src.labels.barriers import barrier_exits
from src.live.orders import stop_level, trailing_stops, trail_width


def _cfg_without(cfg, key):
    d = cfg.to_dict()
    d["barrier"] = {k: v for k, v in d["barrier"].items() if k != key}
    return Cfg(d)


def test_config_carries_the_trail_and_engine_opts_pick_it_up():
    cfg, _ = load_config('configs/system_top150.yaml')
    assert float(cfg.barrier.trail_m) == 1.0
    assert engine_opts_from_cfg(cfg)["trail_m"] == 1.0
    assert engine_opts_from_cfg(_cfg_without(cfg, "trail_m"))["trail_m"] is None


def test_trail_zero_is_off_and_matches_no_trail():
    cm = CostModel(per_trade_bps=0)
    idx = pd.date_range('2024-01-01', periods=40, freq='B')
    c = pd.DataFrame({'X': [100.0] * 40}, index=idx)
    op, hi, lo = c.copy(), c * 1.0005, c * 0.9995
    hi.iloc[3] = 110.0
    sig = c * 0 + 0.02
    ent = pd.DataFrame({'date': [idx[0]], 'ticker': ['X'], 'side': [1]})
    a = barrier_exits(ent, op, hi, lo, c, sig, cm, m=1.5, h=20)
    b = barrier_exits(ent, op, hi, lo, c, sig, cm, m=1.5, h=20, trail_m=0)
    pd.testing.assert_frame_equal(a, b)
    assert barrier_exits(ent, op, hi, lo, c, sig, cm, m=1.5, h=20,
                         trail_m=1.0).iloc[0].barrier_hit == 'trail'


def test_event_engine_defaults_to_the_config_trail(rng, synth_panel):
    from src.primitives.ewma import ewma_sigma
    from src.primitives.returns import daily_return, log_return
    cfg, _ = load_config('configs/system_top150.yaml')
    p = synth_panel
    sig = ewma_sigma(log_return(daily_return(p.adj_close)), span=32)
    ens = pd.DataFrame(rng.random(p.adj_close.shape), index=p.adj_close.index,
                       columns=p.adj_close.columns)
    sel = ens.rank(axis=1, ascending=False, method='first').le(5)
    with_cfg = run_event_backtest(sel, p, sig, CostModel(5), cfg, h=20)
    assert with_cfg['hit_counts'].get('trail', 0) > 0          # config trail applies
    off = run_event_backtest(sel, p, sig, CostModel(5), cfg, h=20, trail_m=0)
    plain = run_event_backtest(sel, p, sig, CostModel(5), _cfg_without(cfg, "trail_m"), h=20)
    assert 'trail' not in off['hit_counts'] and 'trail' not in plain['hit_counts']
    pd.testing.assert_frame_equal(off['trades'], plain['trades'])


def test_order_file_repegs_the_stop_nightly():
    cfg, _ = load_config('configs/system_top150.yaml')
    m, h = float(cfg.barrier.m), int(cfg.barrier.h_days)
    sig = 0.02
    w = trail_width(sig, cfg)
    assert abs(w - 1.0 * sig * np.sqrt(h)) < 1e-12
    fixed = 100.0 * (1 - m * sig * np.sqrt(h))
    # With m 1.5 and trail 1.0 the trailing level is above the fixed stop for any
    # running high over ~92.7% of the fill — i.e. from the fill session on, since
    # the high can never be below the fill. The fixed stop only stands for a
    # (hypothetical) high below that crossover.
    cross = (1 - m * sig * np.sqrt(h)) / (1 - w)
    px, kind = stop_level(100.0, sig, 100.0 * cross * 0.99, cfg)
    assert kind == 'fixed' and abs(px - fixed) < 1e-9
    px, kind = stop_level(100.0, sig, 100.0, cfg)          # at the fill itself
    assert kind == 'trail' and px > fixed
    # the name ran: the stop ratchets to high x (1 - w), above the fixed level
    px, kind = stop_level(100.0, sig, 130.0, cfg)
    assert kind == 'trail' and abs(px - 130.0 * (1 - w)) < 1e-9 and px > fixed
    # trail off -> always the fixed stop
    px, kind = stop_level(100.0, sig, 130.0, _cfg_without(cfg, "trail_m"))
    assert kind == 'fixed'
    pos = pd.DataFrame({'ticker': ['A', 'B', 'C'], 'shares': [10, 5, 0],
                        'entry_price': [100.0, 50.0, 10.0], 'sigma_entry': [sig, sig, sig],
                        'high_since_fill': [130.0, 50.0 * cross * 0.9, 20.0]})
    orders = trailing_stops(pos, cfg)
    assert [o.ticker for o in orders] == ['A', 'B']          # flat names get no order
    assert all(o.order_type == 'STP' and o.tif == 'GTC' and o.action == 'SELL' for o in orders)
    assert orders[0].quantity == 10 and 'trail' in orders[0].note
    assert 'fixed' in orders[1].note
