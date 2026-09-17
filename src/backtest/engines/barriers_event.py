"""M15 — event-driven confirmation engine with LIVE barrier exits (Stage 3, §J).

Positions have individual lifecycles: a new 1/`tranches` NAV tranche enters each
day (decile-10 + meta gate, inverse-vol weights), fills at open t+1, and exits
via the ONE M5.2 barrier engine (stop / profit-take intraday, vertical MOO at
t+h+1) — never a re-implementation (M15-02/G-15). Same-session exits increment
the PDT counter; under $25k the exhausted 4th converts to next-open deferral
[IMPL pdt.mode_under_25k]. Gap-throughs fill at the session open (M15-04).

This engine cross-checks the fast path within |dSharpe| <= 0.1 tolerance [IMPL].

Short sleeve (2026-09-17, blueprint port.selection [MAY]): `run_event_backtest`
takes `side`; a long/short book is a long sleeve plus a short sleeve, each under
its own live-gross cap (`sleeve_caps`), combined by `run_long_short` /
`combine_sleeves`. With no short keys in the config every path here is
bit-identical to the long-only engine.
"""
from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

from src.backtest.compliance import PDTCounter
from src.backtest.costs import CostModel
from src.labels.barriers import barrier_exits


def engine_opts_from_cfg(cfg) -> dict:
    """Config-driven engine options for the aggressive-book keys. Every key
    absent from the config -> the pre-existing default -> bit-identical
    behavior (the default system.yaml carries none of them)."""
    return {"net_moo_costs": bool(cfg.cost.get("net_moo_at_open", False)),
            "gross_cap": cfg.port.get("gross_cap"),
            "gross_cap_exact": bool(cfg.port.get("gross_cap_exact", False)),
            "trail_m": cfg.barrier.get("trail_m"),
            "flat_k": cfg.barrier.get("flat_k"),
            "flat_m": cfg.barrier.get("flat_m")}


def tranche_weights(row: pd.Series, sigma_row: pd.Series, cap: float, tranches: int,
                    meta_row: pd.Series | None = None) -> pd.Series | None:
    """Step 1 of the event engine for ONE decision day: inverse-vol weights over
    the names entering (x the meta multiplier), normalized to a tranche gross
    of 1 and capped at the book-level single-name cap. None when nothing
    enters. Shared by the backtest loop and the live book (G-15)."""
    names = list(row.index[row.astype(bool)])
    if not names:
        return None
    iv = 1.0 / sigma_row[names]
    if meta_row is not None:
        mm = meta_row.reindex(names).fillna(0.0)
        iv = iv * mm
    iv = iv.replace([np.inf, -np.inf], np.nan).dropna()
    iv = iv[iv > 0]
    if not len(iv):
        return None
    return (iv / iv.sum()).clip(upper=cap * tranches)   # cap at book level


def run_event_backtest(selection: pd.DataFrame, panel, sigma32: pd.DataFrame,
                       cost_model: CostModel, cfg,
                       meta_mult: pd.DataFrame | None = None,
                       account_equity: float | None = None,
                       day_budget_mult: pd.Series | None = None,
                       nav0: float = 1.0, m: float | None = None,
                       h: int | None = None,
                       thr_cap: float | None = None,
                       m_up: float | None = None,
                       m_dn: float | None = None,
                       net_moo_costs: bool = False,
                       gross_cap: float | None = None,
                       gross_cap_exact: bool = False,
                       stay_mask: pd.DataFrame | None = None,
                       trail_m: float | None = None,
                       flat_k: int | None = None,
                       flat_m: float | None = None,
                       fill_max: float | None = None,
                       side: int = 1) -> dict:
    """selection: wide bool frame (decision date x ticker) of names entering that
    day's tranche. Returns {'daily_net', 'equity', 'trades', 'pdt_log', ...}.

    side: +1 (default) runs a LONG sleeve — bit-identical to the engine before
    the short sleeve existed. -1 runs a SHORT sleeve over the same selection
    frame: every lot is a short sale (the ONE barrier engine flips the
    profit-take/stop roles and trails the stop off the running low), daily P&L
    is -tranche_w x open-to-open return, and the borrow fee accrues for every
    session held at the per-name rate (GC default). The dividend liability
    needs no term of its own: the adjusted tape is total-return, so a short's
    path return already contains the dividend (as in the fast path).
    `tranche_w` stays a positive exposure on both sides and `side` carries the
    direction, so the cash cap, MOO netting and PDT logic are shared unchanged.
    A long/short book is two sleeve runs joined by run_long_short."""
    side = int(side)
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side}")
    dates = panel.adj_open.index
    O = panel.adj_open
    pos = {d: i for i, d in enumerate(dates)}
    tranches = int(cfg.port.tranches)
    cap = float(cfg.port.single_name_cap)
    m_b = float(cfg.barrier.m) if m is None else float(m)
    h_b = int(cfg.barrier.h_days) if h is None else int(h)
    if thr_cap is None:
        thr_cap = cfg.barrier.get("thr_cap_pct")
    # M5.2 overlays default to the config (the ONE engine, G-15); an explicit
    # argument overrides per variant — pass 0 to switch an adopted overlay off
    if trail_m is None:
        trail_m = cfg.barrier.get("trail_m")
    if flat_k is None:
        flat_k = cfg.barrier.get("flat_k")
    if flat_m is None:
        flat_m = cfg.barrier.get("flat_m")

    # 1) entries per decision day with inverse-vol weights inside the tranche
    #
    # gross_cap: hard ceiling on PROJECTED live gross (sum of open tranche
    # weights, assuming each runs to its vertical exit — early barrier exits
    # only free capital sooner, so the projection is conservative). The
    # entering tranche is scaled down to fit; a Reg-T margin account cannot
    # follow the uncapped vol-target through low-vol regimes.
    entries = []
    live_q: list[tuple[int, float]] = []   # (expiry index, entering gross)
    live_gross = 0.0
    for d0, row in selection.iterrows():
        meta_row = meta_mult.reindex(index=[d0]).iloc[0] if meta_mult is not None else None
        w = tranche_weights(row, sigma32.loc[d0], cap, tranches, meta_row)
        if w is None:
            continue
        # M13 regime overlay + M14 vol targeting scale the ENTERING tranche
        bud = float(day_budget_mult.get(d0, 1.0)) if day_budget_mult is not None else 1.0
        if gross_cap is not None and not gross_cap_exact:
            i_d = pos.get(pd.Timestamp(d0))
            if i_d is not None:
                while live_q and live_q[0][0] <= i_d:
                    live_gross -= live_q.pop(0)[1]
                intended = float(w.sum()) / tranches * bud
                allowed = max(0.0, float(gross_cap) - live_gross)
                if intended > allowed:
                    bud *= allowed / intended if intended > 0 else 0.0
                    intended = allowed
                if intended > 0:
                    live_q.append((i_d + h_b + 1, intended))
                    live_gross += intended
                if bud <= 0:
                    continue
        for t, wt in w.items():
            entries.append({"date": d0, "ticker": t, "side": side,
                            "tranche_w": wt / tranches * bud})
    edf = pd.DataFrame(entries)
    if edf.empty:
        z = pd.Series(0.0, index=dates)
        return {"daily_net": z, "equity": (1 + z).cumprod(), "trades": edf,
                "pdt_log": [], "n_trades": 0, "avg_hold": float("nan"),
                "hit_counts": {}}

    # 2) exits via the ONE barrier engine (C-06)
    ex = barrier_exits(edf[["date", "ticker", "side"]], panel.adj_open, panel.adj_high,
                       panel.adj_low, panel.adj_close, sigma32, cost_model,
                       m=m_b, h=h_b, tie_break=str(cfg.barrier.tie_break),
                       thr_cap=thr_cap, m_up=m_up, m_dn=m_dn,
                       trail_m=trail_m, flat_k=flat_k, flat_m=flat_m)
    ex["tranche_w"] = edf["tranche_w"].to_numpy()
    ex = ex[ex["barrier_hit"].isin(["upper", "lower", "vertical", "censored",
                                    "trail", "flat"])]

    # 3) PDT: same-session exits; under $25k the exhausted 4th defers to next open
    pdt = PDTCounter(account_equity)
    pdt_log = []
    Ov = O.to_numpy()
    cols = {t: j for j, t in enumerate(O.columns)}

    # 2b) optional rank-exit overlay: a position also exits (next-open MOO)
    # after the first decision date where stay_mask says the name no longer
    # qualifies (e.g. fell out of the top-N ranks). Only an AFFIRMATIVE False
    # forces an exit — dates/names outside the mask stay neutral. Applied as
    # an override on the barrier engine's result, like the PDT deferral; the
    # earlier of (barrier exit, rank exit) wins.
    if stay_mask is not None and len(ex):
        SM = stay_mask.reindex(index=dates, columns=O.columns) \
                      .fillna(True).to_numpy(bool)
        n_d = len(dates)
        for idx in ex.index:
            i0 = pos[ex.at[idx, "fill_date"]]
            i1 = pos[ex.at[idx, "exit_date"]]
            jc = cols[ex.at[idx, "ticker"]]
            hit_s = None
            for s in range(i0, i1 - 1):     # decision at close s -> exit open s+1
                if not SM[s, jc]:
                    hit_s = s
                    break
            if hit_s is None:
                continue
            e = hit_s + 1
            while e < n_d and not np.isfinite(Ov[e, jc]):
                e += 1                       # halted bar: next tradable open
            if e >= n_d or e >= i1:
                continue                     # barrier exit comes first anyway
            P0 = float(ex.at[idx, "entry_price"])
            px = float(Ov[e, jc])
            sd = int(ex.at[idx, "side"])
            gross = sd * (px / P0 - 1.0)
            ex.at[idx, "exit_date"] = dates[e]
            ex.at[idx, "exit_price"] = px
            ex.at[idx, "barrier_hit"] = "rank"
            ex.at[idx, "label"] = int(np.sign(gross)) if gross != 0 else 0
            ex.at[idx, "exit_ret_gross"] = gross
            ex.at[idx, "exit_ret_net"] = gross - cost_model.round_trip_frac(
                side=sd, holding_days=e - i0, ticker=ex.at[idx, "ticker"],
                date=dates[e])
            ex.at[idx, "holding_days"] = e - i0
            ex.at[idx, "day_trade"] = False

    day_rows = ex.index[ex["day_trade"]]
    for i in day_rows:
        d_fill = ex.at[i, "fill_date"]
        if pdt.can_day_trade(d_fill):
            pdt.record(d_fill)
            pdt_log.append({"date": str(d_fill), "action": "day_trade_allowed"})
        else:
            j, ifill = cols[ex.at[i, "ticker"]], pos[d_fill]
            if ifill + 1 < len(dates) and np.isfinite(Ov[ifill + 1, j]):
                ex.at[i, "exit_date"] = dates[ifill + 1]
                ex.at[i, "exit_price"] = Ov[ifill + 1, j]
                g = ex.at[i, "side"] * (ex.at[i, "exit_price"] / ex.at[i, "entry_price"] - 1)
                ex.at[i, "exit_ret_gross"] = g
                ex.at[i, "exit_ret_net"] = g - cost_model.round_trip_frac(
                    side=int(ex.at[i, "side"]), holding_days=1)
                ex.at[i, "day_trade"] = False
                pdt_log.append({"date": str(d_fill), "action": "deferred_to_next_open"})

    # 3b) EXACT gross cap (cash-account mode): scale each day's entering
    # tranche so realized live gross never exceeds the cap, releasing capital
    # on ACTUAL exit dates (barrier exits are weight-independent, so exits are
    # known before sizing). An at-open exit (vertical / gap-through / deferred)
    # frees its capital for that same open's entries — the MOO file sells and
    # buys at one print; an intraday barrier exit frees it the next session.
    # The projected cap above instead assumes every position runs to its
    # vertical, leaving early-exit capital idle (~0.80x invested at cap 1.0).
    #
    # fill_max [IMPL lever]: the exact cap only ever scales an entering tranche
    # DOWN. At short horizons a third of positions leave early through a
    # barrier and their capital sits idle until the nominal 1/tranches slice
    # of the next day (~0.76x invested at h=7-10). With fill_max > 1 the
    # entering tranche is scaled UP to re-deploy freed capital, to at most
    # fill_max x its nominal size and never above the cap. Default None/1.0 =
    # original accounting.
    if gross_cap is not None and gross_cap_exact and len(ex):
        capg = float(gross_cap)
        fill = float(fill_max) if fill_max is not None else 1.0
        w_arr = ex["tranche_w"].to_numpy(float).copy()
        i0_arr = np.array([pos[d] for d in ex["fill_date"]])
        ie_arr = np.array([pos[d] for d in ex["exit_date"]])
        at_open = np.array([
            ie > i0 and ex_p == Ov[ie, cols[t]]
            for ie, i0, ex_p, t in zip(ie_arr, i0_arr, ex["exit_price"], ex["ticker"])])
        rel_arr = np.where(at_open, ie_arr, ie_arr + 1)
        rel_heap: list[tuple[int, float]] = []
        live = 0.0
        k = 0
        n_rows = len(ex)
        while k < n_rows:
            j = k
            while j < n_rows and i0_arr[j] == i0_arr[k]:
                j += 1
            while rel_heap and rel_heap[0][0] <= i0_arr[k]:
                live -= heapq.heappop(rel_heap)[1]
            intended = float(w_arr[k:j].sum())
            allowed = max(0.0, capg - live)
            s = 1.0 if intended <= allowed else (allowed / intended if intended > 0 else 0.0)
            if fill > 1.0 and 0.0 < intended < allowed:
                s = min(fill, allowed / intended)      # re-deploy freed capital
            if s != 1.0:
                w_arr[k:j] *= s
            for r in range(k, j):
                if w_arr[r] > 0:
                    heapq.heappush(rel_heap, (int(rel_arr[r]), float(w_arr[r])))
            live += intended * s
            k = j
        ex = ex.assign(tranche_w=w_arr)
        ex = ex[ex["tranche_w"] > 1e-12]

    # 4) mark-to-market daily P&L per position -> book daily returns (compounded
    #    on the tranche budget; costs at entry+exit legs are inside exit_ret_net)
    #
    # net_moo_costs: entries fill MOO, and vertical exits leave MOO at the SAME
    # open print — a live order file nets the two per ticker, so only the NET
    # traded notional pays the leg cost. Per-tranche accounting otherwise charges
    # a persistent name a full round trip every h sessions for re-entering
    # itself, which at short h is the dominant (and fictional) cost.
    # Intraday barrier exits (upper/lower/censored) cannot net against a MOO
    # entry and always pay their leg. Default False = original accounting.
    pnl = np.zeros(len(dates))
    leg = cost_model.leg_frac()
    # (day, ticker) MOO legs that open a lot / close a lot at the same print. For
    # a short sleeve the roles are reversed (open = sell short, close = buy to
    # cover) but the netting is the same: only the NET notional pays the leg.
    buy_open: dict[tuple[int, int], float] = {}    # MOO legs opening a lot
    sell_open: dict[tuple[int, int], float] = {}   # MOO legs closing a lot
    cost = np.zeros(len(dates))
    borrow = np.zeros(len(dates))
    fee_frame = (cost_model.borrow_fee_frame(dates, O.columns).to_numpy()
                 if side < 0 else None)
    for r in ex.itertuples(index=False):
        i0, i1 = pos[r.fill_date], pos[r.exit_date]
        j = cols[r.ticker]
        path = Ov[i0:i1 + 1, j].copy()
        path[-1] = r.exit_price
        rets = np.diff(path) / path[:-1]
        if i1 > i0:
            contrib = r.tranche_w * rets
            if side < 0:
                contrib = -contrib
            pnl[i0 + 1:i1 + 1] += contrib
            if side < 0:
                # borrow for every session the short is held overnight (fill
                # i0 .. i1-1), charged with that session's mark at the per-name
                # fee known that day — the same day count as round_trip_frac
                borrow[i0 + 1:i1 + 1] += r.tranche_w * fee_frame[i0:i1, j] / 1e4 / 252.0
        else:   # same-session round trip: open->barrier within the fill session
            contrib = r.tranche_w * (r.exit_price / r.entry_price - 1)
            pnl[i0] += -contrib if side < 0 else contrib
        exit_at_open = i1 > i0 and r.exit_price == Ov[i1, j]
        if net_moo_costs:
            buy_open[(i0, j)] = buy_open.get((i0, j), 0.0) + r.tranche_w
            if exit_at_open:
                sell_open[(i1, j)] = sell_open.get((i1, j), 0.0) + r.tranche_w
            else:
                cost[i1] += r.tranche_w * leg
        else:
            # inline application preserves the original float summation order —
            # the default path stays bit-identical to the pre-netting engine
            pnl[i0] -= r.tranche_w * leg
            pnl[i1] -= r.tranche_w * leg
            cost[i0] += r.tranche_w * leg
            cost[i1] += r.tranche_w * leg
    if net_moo_costs:
        for (i, j), w in buy_open.items():
            net_w = w - sell_open.pop((i, j), 0.0)
            cost[i] += abs(net_w) * leg
        for (i, j), w in sell_open.items():   # MOO sells with no same-day buy
            cost[i] += w * leg
        pnl -= cost
    if side < 0:
        pnl -= borrow
        cost += borrow
    daily = pd.Series(pnl, index=dates)
    equity = (1 + daily).cumprod() * nav0
    return {"daily_net": daily, "equity": equity, "trades": ex, "pdt_log": pdt_log,
            "n_trades": int(len(ex)),
            "avg_hold": float(ex["holding_days"].mean()),
            "cost_daily": pd.Series(cost, index=dates),
            "hit_counts": ex["barrier_hit"].value_counts().to_dict()}


def live_book(selection: pd.DataFrame, panel, sigma32: pd.DataFrame,
              cost_model: CostModel, cfg, day_budget_mult: pd.Series | None = None,
              meta_mult: pd.DataFrame | None = None, side: int = 1,
              gross_cap="cfg") -> dict:
    """The event-engine book to hold at the NEXT open, read off the ONE engine.

    side=-1 reads the SHORT sleeve's book: every lot is a short sale, its stop
    sits above the fill (or ratchets DOWN off the low since fill when the trail
    is on) and its profit-take below; `due_exits` are covers at the next open.
    `gross_cap` overrides the config's cap for this sleeve (sleeve_caps); the
    sentinel "cfg" keeps port.gross_cap.

    `selection` (decision dates x tickers, bool) covers a trailing window that
    ends at the panel's last session t. The engine is replayed over it with the
    config's options (exact cash cap, MOO netting, trailing stop — the same call
    stage3 makes) and the book at open t+1 is:

      holds      lots filled on or before t that no barrier has closed — the
                 engine reports them `censored` — with the stop level active for
                 the next session (the fixed M5.2 stop, or the trail ratchet off
                 the high since fill, whichever is higher) and their profit-take,
                 both also expressed vs the last close for the ticket;
      due_exits  open lots whose vertical falls at the next open (entered h or
                 more sessions before t): MOO sells. Their capital is re-used by
                 today's tranche, exactly as the exact cap treats at-open exits;
      entries    today's tranche (decision at t): tranche_weights / tranches x
                 budget(t), scaled down to fit gross_cap against the lots that
                 stay live — the engine's rule for the row it cannot replay
                 itself, because open t+1 is not on the tape yet.

    Weights are fractions of NAV at entry, the engine's own sizing basis."""
    dates = panel.adj_open.index
    pos = {d: i for i, d in enumerate(dates)}
    t, i_last = dates[-1], len(dates) - 1
    h = int(cfg.barrier.h_days)
    tranches = int(cfg.port.tranches)
    cap_name = float(cfg.port.single_name_cap)
    side = int(side)
    opts = engine_opts_from_cfg(cfg)
    if not (isinstance(gross_cap, str) and gross_cap == "cfg"):
        opts["gross_cap"] = gross_cap
    res = run_event_backtest(selection, panel, sigma32, cost_model, cfg,
                             meta_mult=meta_mult, day_budget_mult=day_budget_mult,
                             side=side, **opts)
    tr = res["trades"]
    cols = ["entry_date", "ticker", "fill_date", "entry_price", "tranche_w"]
    open_lots = tr[tr["barrier_hit"] == "censored"][cols].copy() if len(tr) \
        else pd.DataFrame(columns=cols)

    # per-lot levels for the next session
    m_b = float(cfg.barrier.m)
    thr_cap = cfg.barrier.get("thr_cap_pct")
    trail_m = opts.get("trail_m")
    trail_on = trail_m is not None and float(trail_m) > 0
    H, C, Lo = panel.adj_high, panel.adj_close, panel.adj_low
    ent_idx, s_left, kinds, stops, pts, stop_pct, pt_pct = [], [], [], [], [], [], []
    for r in open_lots.itertuples(index=False):
        it, i0 = pos[r.entry_date], pos[r.fill_date]
        sig = float(sigma32.at[r.entry_date, r.ticker])
        thr = m_b * sig * np.sqrt(h)
        if thr_cap is not None:
            thr = min(thr, float(thr_cap))
        P0 = float(r.entry_price)
        if side > 0:
            stop, pt, kind = P0 * (1 - thr), P0 * (1 + thr), "fixed"
        else:                       # short: stop above the fill, profit-take below
            stop, pt, kind = P0 * (1 + thr), P0 * (1 - thr), "fixed"
        if trail_on:
            w_tr = float(trail_m) * sig * np.sqrt(h)
            if side > 0:
                hi = H[r.ticker].iloc[i0:i_last + 1]
                if hi.notna().any():
                    lvl = float(np.nanmax(hi.to_numpy())) * (1 - w_tr)
                    if lvl > stop:
                        stop, kind = lvl, "trail"
            else:                   # ratchet DOWN off the low since fill
                lo = Lo[r.ticker].iloc[i0:i_last + 1]
                if lo.notna().any():
                    lvl = float(np.nanmin(lo.to_numpy())) * (1 + w_tr)
                    if lvl < stop:
                        stop, kind = lvl, "trail"
        c = C[r.ticker].iloc[:i_last + 1].dropna()
        c_last = float(c.iloc[-1]) if len(c) else np.nan
        ent_idx.append(it)
        s_left.append(max(0, it + h - i_last))
        kinds.append(kind); stops.append(stop); pts.append(pt)
        stop_pct.append((stop / c_last - 1) * 100 if np.isfinite(c_last) else np.nan)
        pt_pct.append((pt / c_last - 1) * 100 if np.isfinite(c_last) else np.nan)
    open_lots = open_lots.assign(entry_idx=ent_idx, sessions_left=s_left, stop_kind=kinds,
                                 stop_level_adj=stops, pt_level_adj=pts,
                                 stop_vs_close_pct=stop_pct, pt_vs_close_pct=pt_pct)
    due = open_lots[open_lots["entry_idx"] <= i_last - h].reset_index(drop=True)
    keep = open_lots[open_lots["entry_idx"] > i_last - h].reset_index(drop=True)

    # today's tranche under the cap
    intended = pd.Series(dtype=float)
    if t in selection.index:
        meta_row = meta_mult.reindex(index=[t]).iloc[0] if meta_mult is not None else None
        w = tranche_weights(selection.loc[t], sigma32.loc[t], cap_name, tranches, meta_row)
        if w is not None:
            intended = w / tranches
    bud = float(day_budget_mult.get(t, 1.0)) if day_budget_mult is not None else 1.0
    intended = intended * bud
    scale = 1.0
    gc = opts.get("gross_cap")
    if gc is not None and len(intended):
        live = float(keep["tranche_w"].sum()) if len(keep) else 0.0
        allowed = max(0.0, float(gc) - live)
        tot = float(intended.sum())
        if tot > allowed:
            scale = allowed / tot if tot > 0 else 0.0
    entries = intended * scale
    entries = entries[entries > 1e-12]
    return {"as_of": t, "side": side, "entries": entries, "holds": keep,
            "due_exits": due, "budget": bud, "cap_scale": scale,
            "gross_next_open": float(entries.sum()) + (float(keep["tranche_w"].sum())
                                                        if len(keep) else 0.0),
            "trades": tr, "daily_net": res["daily_net"]}


# ----------------------------------------------------------------------------
# Long/short book = two sleeves of the ONE engine
# ----------------------------------------------------------------------------
def sleeve_caps(cfg) -> tuple[float | None, float]:
    """Per-sleeve live-gross caps. `port.long_gross_cap` defaults to
    `port.gross_cap` (the long-only book, unchanged); `port.short_gross_cap`
    defaults to 0 (no short sleeve). The adopted core105 split is 0.5 / 0.5 of
    the 1.0 cash cap: long + short live gross never exceeds NAV, so no cash is
    ever borrowed — the margin account only carries the share loan."""
    gc = cfg.port.get("gross_cap")
    lc = cfg.port.get("long_gross_cap", gc)
    sc = cfg.port.get("short_gross_cap", 0.0)
    return (None if lc is None else float(lc)), float(sc or 0.0)


def combine_sleeves(long_res: dict, short_res: dict | None) -> dict:
    """Long + short sleeve results -> one book in the engine's result shape.
    Daily returns add (both are fractions of NAV); trades concatenate, each row
    carrying its `side`. A None short sleeve returns the long result object
    itself (bit-identical). [IMPL simplification] the PDT counter runs per
    sleeve; with pdt.account_equity unset (>= $25k) it never binds."""
    if short_res is None:
        return long_res
    daily = long_res["daily_net"].add(short_res["daily_net"], fill_value=0.0)
    parts = [t for t in (long_res["trades"], short_res["trades"]) if len(t)]
    trades = pd.concat(parts, ignore_index=True) if parts else long_res["trades"]
    hits = dict(long_res.get("hit_counts", {}))
    for k, v in short_res.get("hit_counts", {}).items():
        hits[k] = hits.get(k, 0) + v
    out = {"daily_net": daily, "equity": (1 + daily).cumprod(), "trades": trades,
           "pdt_log": list(long_res.get("pdt_log", [])) + list(short_res.get("pdt_log", [])),
           "n_trades": int(len(trades)),
           "avg_hold": float(trades["holding_days"].mean()) if len(trades) else float("nan"),
           "hit_counts": hits,
           "sleeves": {"long": long_res, "short": short_res}}
    costs = [r["cost_daily"] for r in (long_res, short_res)
             if r.get("cost_daily") is not None]
    if costs:
        cd = costs[0]
        for c in costs[1:]:
            cd = cd.add(c, fill_value=0.0)
        out["cost_daily"] = cd
    return out


def run_long_short(sel_long: pd.DataFrame, sel_short: pd.DataFrame | None, panel,
                   sigma32: pd.DataFrame, cost_model: CostModel, cfg,
                   short_cap: float | None = None, **kw) -> dict:
    """The long/short book: a long sleeve over `sel_long` (kw as for
    run_event_backtest — its `gross_cap` is the LONG cap) plus, when `short_cap`
    > 0 and `sel_short` selects anything, a short sleeve over `sel_short` capped
    at `short_cap`, joined by combine_sleeves. The regime / vol-target budget
    (day_budget_mult) and the meta multiplier apply to both sleeves alike."""
    long_res = run_event_backtest(sel_long, panel, sigma32, cost_model, cfg,
                                  side=1, **kw)
    short_res = None
    if short_cap is not None and float(short_cap) > 0 and sel_short is not None \
            and bool(sel_short.to_numpy().any()):
        kw_s = dict(kw)
        kw_s["gross_cap"] = float(short_cap)
        short_res = run_event_backtest(sel_short, panel, sigma32, cost_model, cfg,
                                       side=-1, **kw_s)
    return combine_sleeves(long_res, short_res)
