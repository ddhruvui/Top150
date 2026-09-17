"""Short sleeve (2026-09-17, blueprint port.selection [MAY]): selection, engine
parity and semantics, live levels, orders, Stage-1 construction, meta
candidates and ticket rows. With the sleeve off every long-only path must be
bit-identical to the engine before the sleeve existed."""
import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.engines.barriers_event import (combine_sleeves, engine_opts_from_cfg,
                                                 live_book, run_event_backtest,
                                                 run_long_short, sleeve_caps)
from src.config import Cfg, load_config
from src.ensemble.rank import select_long, select_short
from src.live.orders import generate_orders, stop_level, trailing_stops
from src.meta.gate import candidates_from_selection
from src.portfolio.construct import construct_targets
from src.primitives.ewma import ewma_sigma
from src.primitives.returns import daily_return, log_return


def _cfg(h=10, tranches=10, **port):
    cfg, _ = load_config('configs/system_core105.yaml')
    d = cfg.to_dict()
    d["barrier"]["h_days"] = h
    d["port"]["tranches"] = tranches
    d["port"].update(port)
    return Cfg(d)


def _off():
    """The long-only book: no short keys at all (what system.yaml has)."""
    cfg, _ = load_config('configs/system_core105.yaml')
    d = cfg.to_dict()
    d["barrier"]["h_days"] = 10
    d["port"]["tranches"] = 10
    for k in ("short_selection", "short_n", "long_gross_cap", "short_gross_cap",
              "short_max_borrow_bps_yr"):
        d["port"].pop(k, None)
    return Cfg(d)


def _panel(rng, drift, n=300, k=30):
    """Synthetic panel with a chosen daily drift (conftest mechanics)."""
    from src.data.panel import Panel
    idx = pd.date_range('2023-01-02', periods=n, freq='B')
    tick = [f'T{i:02d}' for i in range(k)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(drift, .012, (n, k)), axis=0)),
                         index=idx, columns=tick)
    op = close.shift(1).bfill() * (1 + rng.normal(0, .002, (n, k)))
    hi = pd.DataFrame(np.maximum(close.values, op.values) * (1 + np.abs(rng.normal(0, .003, (n, k)))),
                      index=idx, columns=tick)
    lo = pd.DataFrame(np.minimum(close.values, op.values) * (1 - np.abs(rng.normal(0, .003, (n, k)))),
                      index=idx, columns=tick)
    vol = pd.DataFrame(rng.integers(int(1e5), int(1e7), (n, k)).astype(float), index=idx, columns=tick)
    return Panel(sessions=idx, adj_open=op, adj_high=hi, adj_low=lo, adj_close=close,
                 adj_volume=vol, raw_volume=vol, raw_close=close, raw_open=op,
                 quarantined=pd.DataFrame(False, index=idx, columns=tick))


def _sig(p):
    return ewma_sigma(log_return(daily_return(p.adj_close)), span=32)


def _ens(rng, p):
    return pd.DataFrame(rng.random(p.adj_close.shape), index=p.adj_close.index,
                        columns=p.adj_close.columns)


# ----------------------------------------------------------------- config
def test_core105_config_has_the_short_sleeve_on_and_the_cap_split():
    cfg, _ = load_config('configs/system_core105.yaml')
    assert cfg.port.short_selection == "bottom_n" and int(cfg.port.short_n) == 10
    lc, sc = sleeve_caps(cfg)
    assert (lc, sc) == (0.5, 0.5)
    assert abs(lc + sc - float(cfg.port.gross_cap)) < 1e-12    # cash split, no leverage
    assert cfg.port.short_max_borrow_bps_yr == 100
    # the default registry has no sleeve: long cap == gross cap, short cap 0
    cfg0, _ = load_config('configs/system.yaml')
    assert sleeve_caps(cfg0) == (float(cfg0.port.gross_cap), 0.0)


# -------------------------------------------------------------- selection
def test_select_short_modes_and_borrow_screen(rng):
    idx = pd.date_range('2024-01-01', periods=5, freq='B')
    cols = [f'N{i:03d}' for i in range(105)]
    ens = pd.DataFrame(rng.random((5, 105)), index=idx, columns=cols)
    mask = ens.notna()
    off = select_short(ens, mask, _off())
    assert not off.to_numpy().any() and off.shape == ens.shape
    bn = select_short(ens, mask, _cfg(short_selection="bottom_n", short_n=10))
    assert (bn.sum(axis=1) == 10).all()
    lg = select_long(ens, mask, _cfg())
    assert not (bn & lg).to_numpy().any()                       # disjoint from the longs
    # bottom-N really is the bottom of the ranking
    for d in idx:
        worst = ens.loc[d].nsmallest(10).index
        assert set(bn.loc[d][bn.loc[d]].index) == set(worst)
    bd = select_short(ens, mask, _cfg(short_selection="bottom_decile"))
    assert (bd.sum(axis=1) >= 10).all() and not (bd & lg).to_numpy().any()
    # §I.4: a hard-to-borrow name never enters the short sleeve
    borrowable = pd.DataFrame(True, index=idx, columns=cols)
    htb = ens.iloc[0].idxmin()
    borrowable.loc[idx[0], htb] = False
    scr = select_short(ens, mask, _cfg(short_selection="bottom_n", short_n=10), borrowable)
    assert not scr.loc[idx[0], htb] and bn.loc[idx[0], htb]
    assert scr.loc[idx[0]].sum() == 9


def test_borrow_fee_frame_matches_the_scalar_lookup():
    tbl = pd.DataFrame({"ticker": ["A", "A", "B"],
                        "date": ["2024-01-03", "2024-01-10", "2024-01-05"],
                        "fee_bps_yr": [80.0, 500.0, 20.0]})
    cm = CostModel(15, borrow_gc_bps_yr=30.0, borrow_table=tbl)
    dates = pd.date_range('2024-01-01', periods=10, freq='B')
    f = cm.borrow_fee_frame(dates, ["A", "B", "C"])
    for d in dates:
        for t in ("A", "B", "C"):
            assert f.at[d, t] == cm.borrow_fee_bps(t, d)
    assert f.at[dates[0], "A"] == 30.0 and f.at[dates[-1], "A"] == 500.0
    assert (f["C"] == 30.0).all()                                # not in the table -> GC
    ok = cm.borrowable(dates, ["A", "B", "C"], 100.0)
    assert ok.at[dates[-1], "B"] and not ok.at[dates[-1], "A"]
    assert cm.borrowable(dates, ["A"], None).all().all()


# ----------------------------------------------------------------- engine
def test_sleeve_off_is_bit_identical(rng, synth_panel):
    cfg = _off()
    p, sig = synth_panel, _sig(synth_panel)
    ens = _ens(rng, p)
    sel = ens.rank(axis=1, ascending=False, method='first').le(5)
    none = pd.DataFrame(False, index=sel.index, columns=sel.columns)
    cm = CostModel(15)
    kw = engine_opts_from_cfg(cfg)
    base = run_event_backtest(sel, p, sig, cm, cfg, **kw)          # no side kwarg
    plus = run_event_backtest(sel, p, sig, cm, cfg, side=1, **kw)
    pd.testing.assert_series_equal(base["daily_net"], plus["daily_net"])
    pd.testing.assert_frame_equal(base["trades"], plus["trades"])
    # no short sleeve -> the long result object itself
    ls = run_long_short(sel, none, p, sig, cm, cfg, short_cap=0.0, **kw)
    pd.testing.assert_series_equal(ls["daily_net"], base["daily_net"])
    assert "sleeves" not in ls
    assert combine_sleeves(base, None) is base
    lc, sc = sleeve_caps(cfg)
    assert lc == kw["gross_cap"] and sc == 0.0


def test_short_sleeve_semantics_on_a_falling_tape(rng):
    p = _panel(rng, drift=-0.004)
    sig = _sig(p)
    ens = _ens(rng, p)
    sel = ens.rank(axis=1, ascending=True, method='first').le(5)
    cfg = _off()
    cm = CostModel(10, borrow_gc_bps_yr=0.0)
    long = run_event_backtest(sel, p, sig, cm, cfg, side=1, gross_cap=0.5,
                              gross_cap_exact=True)
    short = run_event_backtest(sel, p, sig, cm, cfg, side=-1, gross_cap=0.5,
                               gross_cap_exact=True)
    assert (short["trades"]["side"] == -1).all() and (long["trades"]["side"] == 1).all()
    assert short["daily_net"].sum() > 0 > long["daily_net"].sum()
    # same lots, mirrored gross returns (exit_ret_gross = side x price move)
    a = long["trades"].set_index(["entry_date", "ticker"])["exit_ret_gross"]
    b = short["trades"].set_index(["entry_date", "ticker"])["exit_ret_gross"]
    common = a.index.intersection(b.index)
    same_exit = (long["trades"].set_index(["entry_date", "ticker"])["exit_price"].loc[common]
                 == short["trades"].set_index(["entry_date", "ticker"])["exit_price"].loc[common])
    assert same_exit.any()
    assert np.allclose(a.loc[common][same_exit.values], -b.loc[common][same_exit.values])
    # a short's stop is the UPPER barrier
    hits = short["trades"]["barrier_hit"]
    assert (hits.isin(["upper", "lower", "vertical", "censored", "trail", "flat"])).all()
    # borrow accrues daily on the short sleeve only: a 10%/yr fee costs the book
    cm_fee = CostModel(10, borrow_gc_bps_yr=1000.0)
    short_fee = run_event_backtest(sel, p, sig, cm_fee, cfg, side=-1, gross_cap=0.5,
                                   gross_cap_exact=True)
    long_fee = run_event_backtest(sel, p, sig, cm_fee, cfg, side=1, gross_cap=0.5,
                                  gross_cap_exact=True)
    pd.testing.assert_series_equal(long_fee["daily_net"], long["daily_net"])
    extra = (short["daily_net"] - short_fee["daily_net"]).sum()
    assert extra > 0
    assert abs((short_fee["cost_daily"] - short["cost_daily"]).sum() - extra) < 1e-12
    # roughly fee x average short gross x years
    yrs = len(p.adj_close) / 252
    tr = short["trades"]
    gross = (tr.groupby("fill_date")["tranche_w"].sum().reindex(p.adj_close.index, fill_value=0)
             - tr.groupby("exit_date")["tranche_w"].sum().reindex(p.adj_close.index, fill_value=0)).cumsum()
    assert abs(extra - 0.10 * gross.mean() * yrs) < 0.25 * extra
    # combined book = long + short, trades carry both sides
    both = combine_sleeves(long, short)
    pd.testing.assert_series_equal(both["daily_net"], long["daily_net"] + short["daily_net"])
    assert both["n_trades"] == long["n_trades"] + short["n_trades"]
    assert set(both["trades"]["side"]) == {1, -1}
    assert both["hit_counts"]["vertical"] == (long["hit_counts"].get("vertical", 0)
                                              + short["hit_counts"].get("vertical", 0))


def test_run_long_short_caps_each_sleeve(rng, synth_panel):
    p, sig = synth_panel, _sig(synth_panel)
    ens = _ens(rng, p)
    sel_l = ens.rank(axis=1, ascending=False, method='first').le(5)
    sel_s = ens.rank(axis=1, ascending=True, method='first').le(5)
    cfg = _cfg()
    kw = engine_opts_from_cfg(cfg)
    kw["gross_cap"] = 0.5
    res = run_long_short(sel_l, sel_s, p, sig, CostModel(15), cfg, short_cap=0.5, **kw)
    assert "sleeves" in res
    for k, cap in (("long", 0.5), ("short", 0.5)):
        tr = res["sleeves"][k]["trades"]
        g = (tr.groupby("fill_date")["tranche_w"].sum().reindex(p.adj_close.index, fill_value=0)
             - tr.groupby("exit_date")["tranche_w"].sum().reindex(p.adj_close.index, fill_value=0)).cumsum()
        assert g.max() <= cap + 1e-9
        assert (tr["side"] == (1 if k == "long" else -1)).all()


# -------------------------------------------------------------- live book
def test_live_book_short_levels_and_parity(rng, synth_panel):
    p, sig = synth_panel, _sig(synth_panel)
    cfg = _cfg()
    ens = _ens(rng, p)
    sel = ens.rank(axis=1, ascending=True, method='first').le(5)
    cm = CostModel(15)
    lb = live_book(sel, p, sig, cm, cfg, side=-1, gross_cap=0.5)
    assert lb["side"] == -1
    holds = lb["holds"]
    assert len(holds)
    h, m = int(cfg.barrier.h_days), float(cfg.barrier.m)
    for r in holds.itertuples(index=False):
        s = float(sig.at[r.entry_date, r.ticker])
        fixed = r.entry_price * (1 + m * s * np.sqrt(h))
        assert r.stop_level_adj > r.entry_price > r.pt_level_adj
        assert r.stop_level_adj <= fixed + 1e-9          # the trail only lowers it
        assert r.stop_kind in ("fixed", "trail")
        assert r.stop_vs_close_pct > 0 > r.pt_vs_close_pct
    assert (holds["stop_kind"] == "trail").any()
    # parity with the backtest (the test_live_book protocol, short side): at a
    # close T seen only through T, the live short book enters what the backtest
    # enters at T and holds the lots the backtest still holds
    from dataclasses import replace
    full = run_event_backtest(sel, p, sig, cm, cfg, side=-1, gross_cap=0.5,
                              **{k: v for k, v in engine_opts_from_cfg(cfg).items()
                                 if k != "gross_cap"})
    tr = full["trades"]
    dates = p.adj_close.index
    checked = 0
    for T in dates[-30:-1]:
        nxt = dates[dates.get_loc(T) + 1]
        gap = tr[(tr["exit_date"] == nxt)
                 & (tr["exit_price"] == p.adj_open.loc[nxt].reindex(tr["ticker"]).to_numpy())
                 & (tr["barrier_hit"] != "vertical")]
        if len(gap):
            continue                      # an open-gap exit at T+1 is unknowable at T
        f = {k: getattr(p, k).loc[:T] for k in
             ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
              "raw_volume", "raw_close", "raw_open", "quarantined")}
        p_T = replace(p, sessions=p.sessions[p.sessions <= T], **f)
        lb_T = live_book(sel.loc[:T], p_T, sig.loc[:T], cm, cfg, side=-1, gross_cap=0.5)
        want = tr[tr["entry_date"] == T].set_index("ticker")["tranche_w"].sort_index()
        pd.testing.assert_series_equal(lb_T["entries"].sort_index(), want,
                                       check_names=False, rtol=1e-12)
        open_bt = tr[(tr["fill_date"] <= T) & (tr["exit_date"] > T)]
        mine = pd.concat([lb_T["holds"], lb_T["due_exits"]])
        assert sorted(zip(mine["entry_date"], mine["ticker"])) == \
            sorted(zip(open_bt["entry_date"], open_bt["ticker"]))
        assert lb_T["gross_next_open"] <= 0.5 + 1e-9
        checked += 1
    assert checked >= 10


# ----------------------------------------------------------------- orders
def test_orders_for_a_short_sale_and_the_nightly_repeg():
    cfg = _cfg(h=40)
    tw = pd.Series({"L": 0.10, "S": -0.10})
    cur = pd.Series({"L": 0, "S": 0})
    px = pd.Series({"L": 50.0, "S": 200.0})
    sig = pd.Series({"L": 0.02, "S": 0.02})
    orders = generate_orders(tw, cur, px, 100_000.0, sig, cfg)
    thr = float(cfg.barrier.m) * 0.02 * np.sqrt(40)
    by = {(o.ticker, o.order_type, o.action): o for o in orders}
    # long: BUY MOO, SELL stop below, SELL limit above
    assert by[("L", "MOO", "BUY")].quantity == 200
    assert abs(by[("L", "STP", "SELL")].stop_price - round(50 * (1 - thr), 2)) < 1e-9
    assert abs(by[("L", "LMT", "SELL")].limit_price - round(50 * (1 + thr), 2)) < 1e-9
    # short: SELL MOO to open, BUY stop ABOVE, BUY limit BELOW
    assert by[("S", "MOO", "SELL")].quantity == 50
    assert "short" in by[("S", "MOO", "SELL")].note
    assert abs(by[("S", "STP", "BUY")].stop_price - round(200 * (1 + thr), 2)) < 1e-9
    assert abs(by[("S", "LMT", "BUY")].limit_price - round(200 * (1 - thr), 2)) < 1e-9
    assert len(orders) == 6
    # covering an existing short is a plain BUY MOO with no new barrier orders
    cov = generate_orders(pd.Series({"S": 0.0}), pd.Series({"S": -50}), px, 100_000.0, sig, cfg)
    assert [(o.action, o.order_type, o.quantity) for o in cov] == [("BUY", "MOO", 50)]

    # nightly re-peg: a short's stop only ever moves DOWN, off the running low
    fixed, kind = stop_level(200.0, 0.02, np.nan, cfg, side=-1)
    assert kind == "fixed" and abs(fixed - 200 * (1 + thr)) < 1e-9
    w = float(cfg.barrier.trail_m) * 0.02 * np.sqrt(40)
    lo_far, k1 = stop_level(200.0, 0.02, 150.0, cfg, side=-1)
    assert k1 == "trail" and abs(lo_far - 150 * (1 + w)) < 1e-9 and lo_far < fixed
    # a running low so close to the fill that low x (1 + w) sits ABOVE the fixed
    # stop: the trail is ignored, the fixed stop stands
    lo_near, k2 = stop_level(200.0, 0.02, 230.0, cfg, side=-1)
    assert 230.0 * (1 + w) > fixed
    assert k2 == "fixed" and lo_near == fixed
    pos = pd.DataFrame([{"ticker": "S", "shares": -50, "entry_price": 200.0,
                         "sigma_entry": 0.02, "high_since_fill": 205.0,
                         "low_since_fill": 150.0},
                        {"ticker": "L", "shares": 200, "entry_price": 50.0,
                         "sigma_entry": 0.02, "high_since_fill": 60.0,
                         "low_since_fill": 49.0}])
    reps = {o.ticker: o for o in trailing_stops(pos, cfg)}
    assert reps["S"].action == "BUY" and reps["S"].quantity == 50
    assert abs(reps["S"].stop_price - round(150 * (1 + w), 2)) < 1e-9
    assert reps["L"].action == "SELL" and abs(reps["L"].stop_price - round(60 * (1 - w), 2)) < 1e-9


# ---------------------------------------------------------- construction
def test_construct_targets_short_sleeve_and_long_only_parity(rng):
    idx = pd.date_range('2024-01-01', periods=60, freq='B')
    cols = [f'T{i:02d}' for i in range(20)]
    ens = pd.DataFrame(rng.random((60, 20)), index=idx, columns=cols)
    dec = (ens.rank(axis=1, pct=True) * 10).clip(upper=10).apply(np.ceil).astype(float)
    mask = pd.DataFrame(True, index=idx, columns=cols)
    sig = pd.DataFrame(rng.uniform(0.01, 0.03, (60, 20)), index=idx, columns=cols)
    short_sel = dec.eq(1)
    base = construct_targets(dec, mask, sig, None, None, tranches=5, single_name_cap=0.3,
                             hedge=False)
    same = construct_targets(dec, mask, sig, None, None, tranches=5, single_name_cap=0.3,
                             hedge=False, short_sel=None, long_budget=1.0, short_budget=0.0)
    pd.testing.assert_frame_equal(base, same)                      # bit-identical
    assert (base >= 0).all().all()
    ls = construct_targets(dec, mask, sig, None, None, tranches=5, single_name_cap=0.3,
                           hedge=False, short_sel=short_sel, long_budget=0.5,
                           short_budget=0.5)
    neg = ls < 0
    assert neg.to_numpy().any()
    # negative weights only where the short sleeve selected the name recently
    recent_short = short_sel.rolling(5, min_periods=1).max().astype(bool)
    assert not (neg & ~recent_short).to_numpy().any()
    assert (ls.abs() <= 0.3 + 1e-12).all().all()
    # once both sleeves are full: net exposure ~ 0 (0.5 long - 0.5 short) and
    # gross between one sleeve's budget and the cap — a name in both deciles
    # inside the tranche window nets, which is what trims gross below 1.0
    late = ls.iloc[10:]
    assert abs(late.sum(axis=1).mean()) < 0.03
    assert 0.5 < late.abs().sum(axis=1).mean() <= 1.0 + 1e-9
    # a name the short sleeve can never touch carries exactly the long-only
    # book's weight scaled by the long budget — with the single-name cap out of
    # the way (its one redistribution pass spreads a capped name's excess over
    # every other held name, both sleeves included, which is intended). A name
    # that was short recently differs too: the no-trade band carries its netted
    # weight forward, the same rule the long-only book applies to its history.
    half = construct_targets(dec, mask, sig, None, None, tranches=5, single_name_cap=1.0,
                             hedge=False, long_budget=0.5)
    short_first10 = short_sel.copy()
    short_first10[cols[10:]] = False
    ls2 = construct_targets(dec, mask, sig, None, None, tranches=5, single_name_cap=1.0,
                            hedge=False, short_sel=short_first10, long_budget=0.5,
                            short_budget=0.5)
    pd.testing.assert_frame_equal(half[cols[10:]], ls2[cols[10:]],
                                  check_exact=False, atol=1e-12)
    assert (ls2[cols[10:]] >= 0).all().all() and (ls2[cols[:10]] < 0).to_numpy().any()


# -------------------------------------------------------- meta + ticket
def test_candidates_from_selection_and_short_ticket_rows(rng, synth_panel):
    from src.pipeline.predict import sleeve_ticket
    p, sig = synth_panel, _sig(synth_panel)
    ens = _ens(rng, p)
    sel = ens.rank(axis=1, ascending=True, method='first').le(5)
    cand = candidates_from_selection(sel, p.adj_close.index[:3], side=-1)
    assert len(cand) == 15 and (cand["side"] == -1).all()
    assert set(cand["ticker"][cand["date"] == p.adj_close.index[0]]) == \
        set(sel.iloc[0][sel.iloc[0]].index)

    cfg = _cfg()
    lb = live_book(sel, p, sig, CostModel(15), cfg, side=-1, gross_cap=0.5)
    T = p.adj_close.index[-1]
    h = int(cfg.barrier.h_days)
    thr = float(cfg.barrier.m) * sig.loc[T] * np.sqrt(h)
    trail_w = float(cfg.barrier.trail_m) * sig.loc[T] * np.sqrt(h)
    S = sleeve_ticket(lb, -1, ens.loc[T], p.raw_close.loc[T], thr, trail_w, h)
    assert S["new"] and all(r["action"] == "SHORT" and r["side"] == -1 for r in S["new"])
    for r in S["new"]:
        assert r["stop_pct"] > 0 > r["profit_take_pct"]           # stop above, PT below
        assert abs(r["stop_pct"] + r["profit_take_pct"]) < 1e-9
        assert r["trail_pct"] > 0 and r["levels_basis"] == "fill"
    for r in S["holds"]:
        assert r["action"] == "HOLD SHORT" and r["stop_pct"] > 0 > r["profit_take_pct"]
    for r in S["exits"]:
        assert r["action"] == "COVER" and "cover" in r["reason"]
    assert abs(sum(r["target_weight"] for r in S["new"] + S["holds"]) - S["gross"]) < 1e-3
    L = sleeve_ticket(live_book(sel, p, sig, CostModel(15), cfg, side=1, gross_cap=0.5),
                      1, ens.loc[T], p.raw_close.loc[T], thr, trail_w, h)
    assert all(r["action"] == "BUY" and r["stop_pct"] < 0 < r["profit_take_pct"]
               for r in L["new"])
