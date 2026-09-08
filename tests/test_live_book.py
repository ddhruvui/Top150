"""The daily ticket trades the event-engine book (2026-09-08): live_book() at
date T, computed from data through T only, must reproduce the entries the
backtest assigns at T and hold exactly the lots the backtest holds."""
import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.engines.barriers_event import (engine_opts_from_cfg, live_book,
                                                 run_event_backtest, tranche_weights)
from src.config import Cfg, load_config


def _cfg(h=10, tranches=10):
    cfg, _ = load_config('configs/system_top150.yaml')
    d = cfg.to_dict()
    d["barrier"]["h_days"] = h
    d["port"]["tranches"] = tranches
    return Cfg(d)


def _slice(panel, T):
    from dataclasses import replace
    f = {k: getattr(panel, k).loc[:T] for k in
         ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
          "raw_volume", "raw_close", "raw_open", "quarantined")}
    return replace(panel, sessions=panel.sessions[panel.sessions <= T], **f)


def test_live_book_reproduces_the_backtest(rng, synth_panel):
    from src.primitives.ewma import ewma_sigma
    from src.primitives.returns import daily_return, log_return
    cfg = _cfg(h=10, tranches=10)
    p = synth_panel
    dates = p.adj_close.index
    sig = ewma_sigma(log_return(daily_return(p.adj_close)), span=32)
    ens = pd.DataFrame(rng.random(p.adj_close.shape), index=dates, columns=p.adj_close.columns)
    sel = ens.rank(axis=1, ascending=False, method='first').le(5)
    bud = pd.Series(rng.uniform(0.6, 1.4, len(dates)), index=dates)
    cm = CostModel(15)
    full = run_event_backtest(sel, p, sig, cm, cfg, day_budget_mult=bud,
                              **engine_opts_from_cfg(cfg))
    tr = full["trades"]
    pos = {d: i for i, d in enumerate(dates)}
    checked = 0
    for T in dates[-40:-1]:
        iT = pos[T]
        # the only information the backtest uses that close T does not have:
        # a lot that gaps through its barrier at the OPEN of T+1 frees its
        # capital for T's entries in the engine; skip those dates
        nxt = dates[iT + 1]
        gap = tr[(tr["exit_date"] == nxt)
                 & (tr["exit_price"] == p.adj_open.loc[nxt].reindex(tr["ticker"]).to_numpy())
                 & (tr["barrier_hit"] != "vertical")]
        if len(gap):
            continue
        lb = live_book(sel.loc[:T], _slice(p, T), sig.loc[:T], cm, cfg, day_budget_mult=bud)
        assert lb["as_of"] == T
        # 1. today's tranche == the backtest's entries decided at T
        want = tr[tr["entry_date"] == T].set_index("ticker")["tranche_w"].sort_index()
        got = lb["entries"].sort_index()
        pd.testing.assert_series_equal(got, want, check_names=False, rtol=1e-12)
        # 2. holds + due exits == lots the backtest still holds at close T
        open_bt = tr[(tr["fill_date"] <= T) & (tr["exit_date"] > T)]
        mine = pd.concat([lb["holds"], lb["due_exits"]])
        assert sorted(zip(mine["entry_date"], mine["ticker"])) == \
            sorted(zip(open_bt["entry_date"], open_bt["ticker"]))
        # 3. due exits are exactly the lots whose vertical is the next open
        due_bt = open_bt[open_bt["exit_date"] == nxt]
        due_bt = due_bt[due_bt["barrier_hit"] == "vertical"]
        assert sorted(zip(lb["due_exits"]["entry_date"], lb["due_exits"]["ticker"])) == \
            sorted(zip(due_bt["entry_date"], due_bt["ticker"]))
        # 4. the cash cap holds at the next open
        assert lb["gross_next_open"] <= 1.0 + 1e-9
        checked += 1
    assert checked >= 20


def test_live_book_levels_and_tranche_weights(rng, synth_panel):
    from src.primitives.ewma import ewma_sigma
    from src.primitives.returns import daily_return, log_return
    cfg = _cfg(h=10, tranches=10)
    p = synth_panel
    sig = ewma_sigma(log_return(daily_return(p.adj_close)), span=32)
    ens = pd.DataFrame(rng.random(p.adj_close.shape), index=p.adj_close.index,
                       columns=p.adj_close.columns)
    sel = ens.rank(axis=1, ascending=False, method='first').le(5)
    lb = live_book(sel, p, sig, CostModel(15), cfg)
    holds = lb["holds"]
    assert len(holds) and (holds["sessions_left"] >= 1).all()
    # stop is never below the fixed M5.2 stop and the trail (cfg 1.0) is on
    h = int(cfg.barrier.h_days)
    for r in holds.itertuples(index=False):
        s = float(sig.at[r.entry_date, r.ticker])
        fixed = r.entry_price * (1 - float(cfg.barrier.m) * s * np.sqrt(h))
        assert r.stop_level_adj >= fixed - 1e-9
        assert r.stop_kind in ("fixed", "trail")
        assert r.pt_level_adj > r.entry_price
    assert (holds["stop_kind"] == "trail").any()
    # tranche_weights: inverse-vol, sums to 1, capped, None when nothing enters
    row = sel.iloc[-1]
    w = tranche_weights(row, sig.iloc[-1], float(cfg.port.single_name_cap), 10)
    assert abs(w.sum() - 1) < 1e-12 and set(w.index) == set(row.index[row])
    assert tranche_weights(row & False, sig.iloc[-1], 0.3, 10) is None
