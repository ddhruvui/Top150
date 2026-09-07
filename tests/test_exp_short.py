"""Branch exp-short-horizon: partial final walk-forward fold (tail coverage),
trailing-stop and dead-money overlays of the M5.2 engine, and the harness's
conviction tilt. Every overlay off -> the original engine, bit-identical."""
import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.labels.barriers import barrier_exits
from src.validation.splits import walk_forward


def _frames(n=40, price=100.0):
    idx = pd.date_range('2024-01-01', periods=n, freq='B')
    c = pd.DataFrame({'X': [price] * n}, index=idx)
    return idx, c.copy(), c.copy(), c * 1.0005, c * 0.9995


def _ent(idx):
    return pd.DataFrame({'date': [idx[0]], 'ticker': ['X'], 'side': [1]})


def test_partial_last_fold_covers_the_tail():
    dates = pd.date_range('2015-01-01', periods=2000, freq='B')
    span, emb = 61, 21
    # 1260 + 504 = 1764 -> a full 252 test block does not fit: no folds today
    assert walk_forward(dates, 1260, 504, 252, 252, span, emb) == []
    folds = walk_forward(dates, 1260, 504, 252, 252, span, emb, partial_last_min=21)
    assert len(folds) == 1
    f = folds[0]
    assert f.test[-1] == dates[-1] and f.test[0] == dates[1764]
    pos = {d: i for i, d in enumerate(dates)}
    a, b = 1764, 1999
    for d in f.train:                      # T-02/T-03 still hold on the partial fold
        i = pos[d]
        assert not (i + 1 <= b and i + 1 + span >= a)
        assert not (b < i <= b + emb)
    # the tail is too short for the minimum -> no partial fold either
    assert walk_forward(dates[:1780], 1260, 504, 252, 252, span, emb,
                        partial_last_min=21) == []
    # a full fold plus a partial one when the remainder is long enough
    dates2 = pd.date_range('2015-01-01', periods=2100, freq='B')
    f2 = walk_forward(dates2, 1260, 504, 252, 252, span, emb, partial_last_min=21)
    assert [len(x.test) for x in f2] == [252, 84]
    assert f2[-1].test[-1] == dates2[-1]


def test_trailing_stop_ratchets_and_is_off_by_default():
    cm = CostModel(per_trade_bps=0)
    sig_val, m, h = 0.02, 1.5, 20                 # fixed barrier +-13.4%
    idx, close, op, hi, lo = _frames()
    sig = close * 0 + sig_val
    hi.iloc[3] = 110.0                            # spike, below the profit-take
    base = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h)
    assert base.iloc[0].barrier_hit == 'vertical'
    # trail width 0.5*0.02*sqrt(20) = 4.47%: level 110*(1-.0447)=105.08 is known
    # after session 3. Session 4 opens at 100, below it -> gap-through fills at
    # the OPEN (M15-04), tagged as a trail exit
    r = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h, trail_m=0.5)
    assert r.iloc[0].barrier_hit == 'trail'
    assert abs(r.iloc[0].exit_price - 100.0) < 1e-9 and r.iloc[0].holding_days == 3
    # same spike, but session 4 opens above the ratchet and dips through it
    # intraday -> fills AT the trailing level, locking in a gain
    lvl = 110.0 * (1 - 0.5 * sig_val * np.sqrt(h))
    op2, hi2, lo2, cl2 = op.copy(), hi.copy(), lo.copy(), close.copy()
    op2.iloc[4], hi2.iloc[4], lo2.iloc[4], cl2.iloc[4] = 106.0, 106.5, 104.0, 106.0
    r = barrier_exits(_ent(idx), op2, hi2, lo2, cl2, sig, cm, m=m, h=h, trail_m=0.5)
    assert r.iloc[0].barrier_hit == 'trail'
    assert abs(r.iloc[0].exit_price - lvl) < 1e-9
    assert r.iloc[0].exit_ret_gross > 0 and r.iloc[0].holding_days == 3
    # without the trail the same tape runs to the vertical
    assert barrier_exits(_ent(idx), op2, hi2, lo2, cl2, sig, cm, m=m,
                         h=h).iloc[0].barrier_hit == 'vertical'
    # the trail never loosens the fixed stop: a flat tape still runs to the vertical
    idx, close, op, hi, lo = _frames()
    r2 = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h, trail_m=0.5)
    assert r2.iloc[0].barrier_hit == 'vertical'


def test_flat_exit_frees_dead_money():
    cm = CostModel(per_trade_bps=0)
    sig_val, m, h = 0.02, 1.5, 20
    idx, close, op, hi, lo = _frames()
    sig = close * 0 + sig_val
    r = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h,
                      flat_k=5, flat_m=0.5)
    assert r.iloc[0].barrier_hit == 'flat' and r.iloc[0].holding_days == 5
    # a trade that has moved is left alone
    close2 = close.copy(); close2.iloc[5] = 103.0
    r2 = barrier_exits(_ent(idx), op, hi, lo, close2, sig, cm, m=m, h=h,
                       flat_k=5, flat_m=0.5)
    assert r2.iloc[0].barrier_hit == 'vertical'
    # overlays off -> identical to the plain engine
    a = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h)
    b = barrier_exits(_ent(idx), op, hi, lo, close, sig, cm, m=m, h=h,
                      trail_m=None, flat_k=None, flat_m=None)
    pd.testing.assert_frame_equal(a, b)
