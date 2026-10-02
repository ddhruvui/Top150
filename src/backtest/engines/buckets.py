"""Per-name buckets (2026-10-02, experiment lever `bucket`): every name owns its
own sub-account and compounds on its own.

Each name is funded with `bucket0` (e.g. $10,000) the first session it is in
the membership mask. A bucket holds at most ONE position at a time: when it is
flat and its entry signal fires at close t, the WHOLE bucket buys whole shares
at the open of t+1 (MOO) and exits through the ONE M5.2 barrier engine (stop /
profit-take / trail / vertical, G-15). The proceeds stay in that name's bucket:
GOOGL makes $1,000 in a trade -> its next trade invests $11,000. A signal that
fires while the bucket is still holding is a HOLD; once flat, the next signal
re-enters, so a name may trade several times inside one cycle.

The entry signal is per-name, not cross-sectional ("option A"): today's
ensemble score against the name's OWN trailing history (`own_percentile`). A
name enters on its own best days, so KO competes with KO's past, not with
MSTR — a ranking that only ever admitted the top decile of the cross-section
left 54 of 103 names untraded since 2020.

`cycle`/`fallback_*` optionally guarantee coverage: a name that has not
entered in the current `cycle`-session block relaxes its bar to `fallback_pct`
over the block's last `fallback_last` sessions, and enters unconditionally on
the block's final session. Fallback entries are tagged `kind="fallback"`.

Book NAV = the sum of every bucket (cash + whole shares marked at the close).
Funding a new bucket is a deposit, not a return: daily_net is time-weighted
(V_t - deposit_t) / V_{t-1}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.labels.barriers import barrier_exits

DONE = ("upper", "lower", "vertical", "censored", "trail", "flat")


def own_percentile(score: pd.DataFrame, mask: pd.DataFrame, window: int = 252,
                   min_periods: int = 126) -> pd.DataFrame:
    """Percentile of today's score inside the name's own trailing `window`
    sessions (today included, nothing after it): 1.0 = the best reading this
    name has had in a year. Causal by construction."""
    s = score.where(mask)
    return s.rolling(window, min_periods=min_periods).rank(pct=True)


def bucket_candidates(pct: pd.DataFrame, mask: pd.DataFrame, q: float,
                      cycle: int | None = None, fallback_pct: float | None = None,
                      fallback_last: int = 0) -> pd.DataFrame:
    """Long frame of (date, ticker, kind) entry candidates, date-sorted.
    'signal' = own percentile >= q. 'fallback' rows (only with `cycle`) are
    the relaxed-bar sessions at the end of each cycle block; the engine takes
    one only for a name that has not yet entered in that block."""
    ok = mask.reindex_like(pct).fillna(False).astype(bool) & pct.notna()
    sig = ok & pct.ge(q)
    parts = [sig.stack().loc[lambda x: x].reset_index().iloc[:, :2]
             .set_axis(["date", "ticker"], axis=1).assign(kind="signal")]
    if cycle:
        n = len(pct.index)
        k = np.arange(n) % int(cycle)
        last = k == int(cycle) - 1
        late = k >= int(cycle) - max(1, int(fallback_last))
        bar = float(fallback_pct) if fallback_pct is not None else 1.1
        fb = ok & ~sig & (pd.DataFrame(np.broadcast_to(late[:, None], pct.shape),
                                       index=pct.index, columns=pct.columns)
                          & pct.ge(bar)
                          | pd.DataFrame(np.broadcast_to(last[:, None], pct.shape),
                                         index=pct.index, columns=pct.columns))
        fb = fb & ok
        parts.append(fb.stack().loc[lambda x: x].reset_index().iloc[:, :2]
                     .set_axis(["date", "ticker"], axis=1).assign(kind="fallback"))
    c = pd.concat(parts, ignore_index=True)
    return c.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)



def _spy_arrays(park, dates):
    """(open, close) numpy arrays of the parking instrument on the panel grid,
    forward-filled; None when parking is off."""
    if park is None:
        return None
    o = park["adj_open"].reindex(dates).ffill().bfill().to_numpy(float)
    c = park["adj_close"].reindex(dates).ffill().bfill().to_numpy(float)
    return o, c


def run_bucket_backtest(pct: pd.DataFrame, mask: pd.DataFrame, panel,
                        sigma32: pd.DataFrame, cost_model: CostModel, cfg,
                        q: float = 0.90, bucket0: float = 10_000.0,
                        m: float | None = None, h: int | None = None,
                        trail_m: float | None = None,
                        cycle: int | None = None,
                        fallback_pct: float | None = None,
                        fallback_last: int = 0,
                        whole_shares: bool = True,
                        park: pd.DataFrame | None = None) -> dict:
    """pct: own-percentile frame (decision date x ticker); its first row is the
    book's start (pots funded, cycle blocks counted from it). Returns the
    experiment-harness result dict (daily_net, trades, cost_daily, n_trades,
    avg_hold, hit_counts) plus `buckets` (end value per name), `stats`
    (coverage per cycle, invested fraction, concentration) and `state` (each
    pot at the last session: the live ticket reads it).

    park: a frame with adj_open/adj_close (SPY) — a flat pot's cash is parked
    in it: bought at the open after the pot is funded or exits, sold at the
    open its next lot fills, one cost leg each way. A lot still open at the
    last session (`censored`) keeps its pot busy: it is marked at the last
    close, and is the HOLD / due-exit row of the live ticket."""
    dates = panel.adj_open.index
    pos = {d: i for i, d in enumerate(dates)}
    cols = {t: j for j, t in enumerate(panel.adj_open.columns)}
    m_b = float(cfg.barrier.m) if m is None else float(m)
    h_b = int(cfg.barrier.h_days) if h is None else int(h)
    if trail_m is None:
        trail_m = cfg.barrier.get("trail_m")
    leg = cost_model.leg_frac()
    cyc = int(cycle) if cycle else 40          # coverage is always reported per 40
    n = len(dates)
    i_last = n - 1
    SP = _spy_arrays(park, dates)

    cand = bucket_candidates(pct, mask, q, cycle, fallback_pct, fallback_last)
    cand["side"] = 1
    if len(cand):
        ex = barrier_exits(cand[["date", "ticker", "side"]], panel.adj_open,
                           panel.adj_high, panel.adj_low, panel.adj_close, sigma32,
                           cost_model, m=m_b, h=h_b,
                           tie_break=str(cfg.barrier.tie_break), trail_m=trail_m)
        ex["kind"] = cand["kind"].to_numpy()
        ex = ex[ex["barrier_hit"].isin(DONE)]
    else:
        ex = pd.DataFrame(columns=["entry_date", "ticker", "kind"])
    # today's candidates (decision at the last close): no fill on the tape yet
    t_last = dates[-1]
    today = cand[cand["date"] == t_last].set_index("ticker")["kind"] if len(cand) \
        else pd.Series(dtype=object)

    C = panel.adj_close.ffill().to_numpy()
    RO = panel.raw_open.to_numpy()
    test0 = pos[pct.index[0]]

    def block(i):
        return (i - test0) // cyc

    mk = mask.reindex(index=pct.index, columns=panel.adj_open.columns).fillna(False)
    fund = {t: pos[mk.index[mk[t].to_numpy(bool).argmax()]]
            for t in mk.columns if mk[t].any()}

    value = np.full((n, len(cols)), np.nan)    # pot value per (day, name)
    invested = np.zeros(n)                     # in its stock
    parked = np.zeros(n)                       # in SPY
    deposits = np.zeros(n)
    cost = np.zeros(n)
    taken, state = [], {}
    groups = {t: g for t, g in ex.groupby("ticker", sort=False)}

    for t, f0 in fund.items():
        j = cols[t]
        g = groups.get(t, ex.iloc[:0])
        deposits[f0] += bucket0
        value[f0, j] = bucket0
        cash = float(bucket0)
        free_from, last_blk, cur = f0, None, f0 + 1
        p_at = f0 + 1                          # open the flat cash parks at
        open_lot = None

        def flat(a, b, cash, p_at):
            """Value the pot over [a, b) while it holds no lot. With parking,
            the cash buys SPY at open p_at (one leg) and is marked at the
            close; returns what is available at open b (SPY sold, one leg),
            or None when it is still parked at the last session."""
            if SP is None or p_at is None or p_at >= b:
                if a < b:
                    value[a:b, j] = cash
                return cash
            if a < p_at:
                value[a:p_at, j] = cash
            u = cash * (1 - leg) / SP[0][p_at]
            cost[p_at] += cash * leg
            k0 = max(a, p_at)
            v = u * SP[1][k0:b]
            value[k0:b, j] = v
            parked[k0:b] += v
            if b >= n:
                return None
            proceeds = u * SP[0][b]
            cost[b] += proceeds * leg
            return proceeds * (1 - leg)

        for r in g.sort_values("entry_date", kind="stable").itertuples(index=False):
            i_dec = pos[r.entry_date]
            if i_dec < free_from:
                continue                       # still holding (or pre-funding)
            b = block(i_dec)
            if r.kind == "fallback" and b == last_blk:
                continue                       # this block already traded
            i0, i1 = pos[r.fill_date], pos[r.exit_date]
            cash = flat(cur, i0, cash, p_at)
            px = RO[i0, j]
            if whole_shares and np.isfinite(px) and px > 0:
                frac = np.floor(cash * (1 - leg) / px) * px / cash
            else:
                frac = 1.0 - leg
            if frac <= 0:
                p_at, cur = i0, i0             # too small for one share: stay flat
                continue
            inv = cash * frac
            censored = r.barrier_hit == "censored" and i1 >= i_last
            end = i_last + 1 if censored else i1
            mark = C[i0:end, j] / r.entry_price
            value[i0:end, j] = cash - inv * (1 + leg) + inv * mark
            invested[i0:end] += inv * mark
            cost[i0] += inv * leg
            rec = {**r._asdict(), "bucket_before": cash, "notional": inv,
                   "block": b, "open": censored}
            if censored:
                open_lot = {"entry_date": r.entry_date, "fill_date": r.fill_date,
                            "entry_price": float(r.entry_price), "notional": inv,
                            "cash_left": cash - inv * (1 + leg), "kind": r.kind,
                            "pot_before": cash,
                            "entry_idx": i_dec}
                cash = float(value[i_last, j])
                free_from, last_blk, cur = n, b, n
                taken.append(rec)
                break
            cash = cash + inv * float(r.exit_ret_net)
            value[i1, j] = cash
            cost[i1] += inv * leg
            taken.append(rec)
            free_from, last_blk, cur = i1, b, i1 + 1
            p_at = i1 + 1
        if open_lot is None:
            flat(cur, n, cash, p_at)
        value[:f0, j] = np.nan
        # ---- the pot at the last close, for the live ticket ----
        b_now = block(i_last)
        st = {"pot": float(value[i_last, j]), "funded": str(dates[f0].date()),
              "traded_this_cycle": last_blk == b_now, "status": "flat",
              "parked": bool(SP is not None and open_lot is None and p_at <= i_last),
              "lot": None, "entering": None}
        if open_lot is not None:
            due = open_lot["entry_idx"] <= i_last - h_b
            st.update(status="due_exit" if due else "holding", lot=open_lot)
        elif t in today.index:
            k = today[t] if not isinstance(today[t], pd.Series) else today[t].iloc[0]
            if k == "signal" or not st["traded_this_cycle"]:
                st.update(status="entering", entering=k)
        state[t] = st

    V = np.nansum(value, axis=1)
    V_prev = np.r_[np.nan, V[:-1]]
    with np.errstate(divide="ignore", invalid="ignore"):
        dn = np.where(V_prev > 0, (V - deposits) / V_prev - 1.0, 0.0)
    daily = pd.Series(dn, index=dates)
    nav = pd.Series(V, index=dates)
    tr = pd.DataFrame(taken)
    if len(tr):
        # weight of the position in the whole book at entry (harness metrics)
        tr["tranche_w"] = tr["notional"] / nav.reindex(tr["fill_date"]).to_numpy()
    done = tr[~tr["open"]] if len(tr) else tr

    stats = {}
    if len(tr):
        n_blk = block(i_last) + 1
        blocks = tr.assign(b=[block(pos[d]) for d in tr["entry_date"]]) \
            .groupby("b")["ticker"].nunique()
        elig = pd.Series({b: int(mk.iloc[b * cyc:(b + 1) * cyc].any().sum())
                          for b in range(n_blk)})
        cov = (blocks.reindex(elig.index, fill_value=0) / elig.replace(0, np.nan)).dropna()
        # a name still holding a lot from the previous block is in play too
        live = np.zeros((n_blk, len(cols)), bool)
        for a, z, t in zip(tr["entry_date"], tr["exit_date"], tr["ticker"]):
            live[max(0, block(pos[a])):min(n_blk - 1, block(pos[z])) + 1, cols[t]] = True
        cov_held = pd.Series(live.sum(axis=1), index=range(n_blk)) / elig.replace(0, np.nan)
        per_name = tr.groupby("ticker").size()
        end_v = pd.Series(value[-1], index=list(cols)).dropna()
        navs = nav.reindex(pct.index).replace(0, np.nan)
        is_sig = done["kind"] == "signal"
        stats = {
            "cycle_sessions": cyc,
            "coverage_per_cycle_mean": float(cov.mean()),
            "coverage_per_cycle_min": float(cov.min()),
            "coverage_after_warmup_min": float(cov.iloc[1:].min()) if len(cov) > 1 else None,
            "cycles_full_coverage": float((cov >= 0.999).mean()),
            "coverage_incl_held_mean": float(cov_held.dropna().mean()),
            "coverage_incl_held_min": float(cov_held.dropna().min()),
            "names_ever_traded": int(per_name.size),
            "names_funded": int(len(fund)),
            "trades_per_name_per_cycle": float(len(tr) / max(1, len(fund)) / n_blk),
            "fallback_share": float((tr["kind"] == "fallback").mean()),
            "win_rate_signal": float((done.loc[is_sig, "exit_ret_net"] > 0).mean()),
            "win_rate_fallback": (float((done.loc[~is_sig, "exit_ret_net"] > 0).mean())
                                  if (~is_sig).any() else None),
            "avg_ret_signal": float(done.loc[is_sig, "exit_ret_net"].mean()),
            "avg_ret_fallback": (float(done.loc[~is_sig, "exit_ret_net"].mean())
                                 if (~is_sig).any() else None),
            "invested_frac_mean": float((pd.Series(invested, index=dates)
                                         .reindex(pct.index) / navs).mean()),
            "parked_frac_mean": float((pd.Series(parked, index=dates)
                                       .reindex(pct.index) / navs).mean()),
            "deposited": float(deposits.sum()),
            "end_nav": float(V[-1]),
            "largest_bucket_share": float(end_v.max() / end_v.sum()),
            "top5_buckets": {k: round(float(v), 2) for k, v in end_v.nlargest(5).items()},
            "bottom5_buckets": {k: round(float(v), 2) for k, v in end_v.nsmallest(5).items()},
            "buckets_below_start": int((end_v < bucket0).sum()),
        }
    return {"daily_net": daily, "equity": (1 + daily).cumprod(), "nav": nav,
            "trades": done,
            "n_trades": int(len(done)),
            "avg_hold": float(done["holding_days"].mean()) if len(done) else float("nan"),
            "hit_counts": done["barrier_hit"].value_counts().to_dict() if len(done) else {},
            "cost_daily": pd.Series(cost, index=dates) / nav.shift(1).replace(0, np.nan),
            "buckets": {k: float(v) for k, v in
                        pd.Series(value[-1], index=list(cols)).dropna().items()},
            "parked_last": float(parked[-1]), "invested_last": float(invested[-1]),
            "cycle": {"block": int(block(i_last)), "session_in_cycle": int((i_last - test0) % cyc) + 1,
                      "cycle_sessions": cyc},
            "state": state, "stats": stats}


def bucket_book_on(cfg) -> bool:
    """port.book: buckets switches stage3 / predict / experiments' baseline
    from the shared decile book to per-name buckets. Absent = shared book."""
    return str(cfg.port.get("book", "shared")).lower() == "buckets"


def run_bucket_book(ens: pd.DataFrame, mask: pd.DataFrame, panel,
                    sigma32: pd.DataFrame, cost_model: CostModel, cfg,
                    spy: pd.DataFrame | None = None,
                    start=None, pct_rows: pd.DataFrame | None = None) -> dict:
    """The configured bucket book (port.bucket_* keys) over an ensemble frame.
    `start`: first decision date (pots funded, cycles counted from it);
    default = the first date the own-history percentile exists.
    `pct_rows`: stored per-day percentile rows (the live book's frozen
    decisions) that override the recomputed ones on their dates."""
    p = cfg.port
    pct = own_percentile(ens, mask, int(p.get("bucket_window", 252)),
                         int(p.get("bucket_min_periods", 126)))
    if pct_rows is not None and len(pct_rows):
        rows = pct_rows.reindex(columns=pct.columns)
        pct = pd.concat([rows, pct[~pct.index.isin(rows.index)]]).sort_index()
    pct = pct.dropna(how="all")
    pct = pct[pct.index.isin(panel.adj_open.index)]   # rows the tape still covers
    if start is not None:
        pct = pct.loc[pd.Timestamp(start):]
    park = spy if str(p.get("bucket_park", "none")).upper() == "SPY" else None
    cyc = p.get("bucket_cycle")
    return run_bucket_backtest(
        pct, mask, panel, sigma32, cost_model, cfg,
        q=float(p.get("bucket_q", 0.90)), bucket0=float(p.get("bucket_unit", 10_000)),
        cycle=int(cyc) if cyc else None,
        fallback_pct=p.get("bucket_fallback_pct"),
        fallback_last=int(p.get("bucket_fallback_last", 0)),
        whole_shares=True, park=park)
