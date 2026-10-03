"""Live ticket for the per-name bucket book (port.book: buckets, 2026-10-02).

The book is replayed with the ONE bucket engine (src/backtest/engines/buckets.py)
from `port.bucket_start` to the last close. Every pot starts at
`port.bucket_unit` that day. Past decisions are FROZEN: each run stores the own-history
percentile rows it decided on (`bucket_signals.parquet` next to the
suggestions), and the next run replays those stored rows instead of
recomputing them with refitted models — so a pot's history never changes
under it. Only today's row (decision at the last close) is recomputed and
overwritten on a same-day rerun.

The ticket reads each pot's state at the last close:
  entering   flat pot whose signal (or the cycle fallback) fires: BUY with the
             whole pot at the next open; its parked SPY is sold at that open.
  holding    one open lot: HOLD with today's stop / profit-take / trail.
  due_exit   the lot's vertical falls at the next open: SELL MOO.
  flat       cash, parked in SPY when port.bucket_park is SPY.
Weights are fractions of the book (the sum of all pots); the app turns them
into whole shares against its own NAV.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engines.barriers_event import lot_levels
from src.backtest.engines.buckets import run_bucket_book

SIGNALS_FILE = "bucket_signals.parquet"


def _f(x, nd=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if np.isfinite(x) else None


def _plain(df: pd.DataFrame) -> pd.DataFrame:
    """Plain str ticker columns and a `date` index. The panel's columns are a
    CategoricalIndex; written as-is, pandas 3 / pyarrow 23 cannot read the
    file back ("data type 'categorical' not understood", 2026-10-02)."""
    df = df.copy()
    df.columns = pd.Index([str(c) for c in df.columns], dtype=object)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index), name="date")
    return df.astype(float)


def frozen_rows(out_dir: Path) -> pd.DataFrame | None:
    p = Path(out_dir) / SIGNALS_FILE
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except (TypeError, KeyError, ValueError):
        # a file written with categorical column metadata: read the raw
        # columns and drop pandas' metadata, then restore the date index
        import pyarrow.parquet as pq
        df = pq.read_table(p).to_pandas(ignore_metadata=True)
        idx = next(c for c in ("date", "__index_level_0__") if c in df.columns)
        df = df.set_index(idx)
    return _plain(df)


def save_rows(out_dir: Path, stored: pd.DataFrame | None, pct: pd.DataFrame,
              start: pd.Timestamp, t_last: pd.Timestamp) -> pd.DataFrame:
    """Freeze every decision row from `start` to t_last: stored rows before
    t_last are kept as they are, missing ones are added from `pct`, and
    today's row is always the fresh one."""
    new = _plain(pct.loc[start:t_last])
    if stored is not None and len(stored):
        old = stored[stored.index < t_last].reindex(columns=new.columns)
        new = pd.concat([old, new[~new.index.isin(old.index)]]).sort_index()
    new.to_parquet(Path(out_dir) / SIGNALS_FILE)
    return new


def bucket_book_live(ens: pd.DataFrame, mask: pd.DataFrame, panel,
                     sigma32: pd.DataFrame, cm, cfg, spy: pd.DataFrame | None,
                     out_dir: Path) -> dict:
    from src.backtest.engines.buckets import own_percentile
    p = cfg.port
    t_last = panel.dates[-1]
    stored = frozen_rows(out_dir)
    if stored is not None and len(stored):
        start = stored.index.min()       # the book's real first decision day
    else:                                # first run: the configured day, or today
        start = min(pd.Timestamp(p.get("bucket_start") or t_last), t_last)
    pct_now = own_percentile(ens, mask, int(p.get("bucket_window", 252)),
                             int(p.get("bucket_min_periods", 126)))
    rows = save_rows(out_dir, stored, pct_now, start, t_last)
    res = run_bucket_book(ens, mask, panel, sigma32, cm, cfg, spy,
                          start=start, pct_rows=rows[rows.index < t_last])
    return {"res": res, "start": start, "rows": rows}


def bucket_ticket(res: dict, panel, sigma32: pd.DataFrame, cfg, ens_last: pd.Series,
                  spy: pd.DataFrame | None) -> dict:
    """Ticket sections in the shared suggestions schema (buys_or_increases /
    holds / sells_or_exits), plus `parking` and `buckets`."""
    st = res["state"]
    t_last = panel.dates[-1]
    nav = float(sum(v["pot"] for v in st.values())) or 1.0
    h = int(cfg.barrier.h_days)
    m_b = float(cfg.barrier.m)
    trail_m = cfg.barrier.get("trail_m")
    trail_on = trail_m is not None and float(trail_m) > 0
    sig_last = sigma32.loc[t_last]
    thr = m_b * sig_last * np.sqrt(h)
    if cfg.barrier.get("thr_cap_pct") is not None:
        thr = thr.clip(upper=float(cfg.barrier.get("thr_cap_pct")))
    last_close = panel.raw_close.ffill().loc[t_last]
    C = panel.adj_close.ffill().loc[t_last]

    unit = float(cfg.port.get("bucket_unit", 10_000))
    done = res.get("trades")
    done = done if done is not None and len(done) else None
    RO = panel.raw_open
    buys, holds, sells, pots = [], [], [], []
    for t in sorted(st, key=lambda k: -st[k]["pot"]):
        s = st[t]
        w = s["pot"] / nav
        g = done[done["ticker"] == t] if done is not None else None
        n_closed = int(len(g)) if g is not None else 0
        realized = float((g["notional"] * g["exit_ret_net"]).sum()) if n_closed else 0.0
        lot = s["lot"]
        open_ret = (float(C.get(t)) / lot["entry_price"] - 1) if lot is not None else None
        fill_px = (float(RO.at[pd.Timestamp(lot["fill_date"]), t])
                   if lot is not None else None)
        pots.append({"ticker": t, "pot_weight": round(w, 6), "pot_value": round(s["pot"], 2),
                     "start_value": unit,
                     "pnl": round(s["pot"] - unit, 2),
                     "pnl_pct": round(s["pot"] / unit - 1, 6),
                     "trades_closed": n_closed,
                     "wins": int((g["exit_ret_net"] > 0).sum()) if n_closed else 0,
                     "realized_pnl": round(realized, 2),
                     "open_entry_date": (str(pd.Timestamp(lot["entry_date"]).date())
                                         if lot is not None else None),
                     "open_fill_price": _f(fill_px),
                     "open_ret_pct": _f(open_ret, 6),
                     "last_close": _f(last_close.get(t)),
                     "status": s["status"], "traded_this_cycle": bool(s["traded_this_cycle"]),
                     "parked": bool(s["parked"]), "entering": s["entering"],
                     "funded": s["funded"]})
        if s["status"] == "entering":
            buys.append({
                "ticker": t, "side": 1, "action": "BUY",
                "target_weight": round(w, 5), "new_lot_weight": round(w, 5),
                "current_weight": 0.0, "lots": None,
                "ensemble_rank": _f(ens_last.get(t), 4),
                "last_close": _f(last_close.get(t)),
                "stop_pct": _f(-float(thr.get(t, np.nan)) * 100),
                "profit_take_pct": _f(float(thr.get(t, np.nan)) * 100),
                "trail_pct": (_f(float(trail_m) * float(sig_last.get(t, np.nan))
                                 * np.sqrt(h) * 100) if trail_on else None),
                "levels_basis": "fill", "max_hold_sessions": h, "sessions_left": h,
                "entry_kind": s["entering"], "pot_value": round(s["pot"], 2),
                "lot": ("whole pot (cycle fallback: no entry yet this cycle)"
                        if s["entering"] == "fallback"
                        else "whole pot (own-history signal)")})
            continue
        lot = s["lot"]
        if lot is None:
            continue
        lv = lot_levels(t, lot["entry_date"], lot["fill_date"], lot["entry_price"],
                        panel, sigma32, cfg, 1, trail_m)
        stock_w = lot["notional"] * float(C.get(t)) / lot["entry_price"] / nav
        lots = [{"entry_date": str(pd.Timestamp(lot["entry_date"]).date()),
                 "fill_date": str(pd.Timestamp(lot["fill_date"]).date()),
                 "weight": round(stock_w, 5), "sessions_left": int(lv["sessions_left"]),
                 "stop_kind": lv["stop_kind"],
                 "stop_vs_close_pct": _f(lv["stop_vs_close_pct"]),
                 "pt_vs_close_pct": _f(lv["pt_vs_close_pct"])}]
        if s["status"] == "due_exit":
            sells.append({"ticker": t, "side": 1, "action": "SELL", "target_weight": 0.0,
                          "current_weight": round(stock_w, 5),
                          "last_close": _f(last_close.get(t)),
                          "reason": f"vertical barrier: MOO sell at the next open "
                                    f"(entered {lots[0]['entry_date']}); proceeds "
                                    f"stay in its pot",
                          "lots": [{"entry_date": lots[0]["entry_date"],
                                    "weight": lots[0]["weight"]}]})
        else:
            holds.append({"ticker": t, "side": 1, "action": "HOLD",
                          "target_weight": round(stock_w, 5),
                          "current_weight": round(stock_w, 5),
                          "ensemble_rank": _f(ens_last.get(t), 4),
                          "last_close": _f(last_close.get(t)),
                          "stop_pct": lots[0]["stop_vs_close_pct"],
                          "profit_take_pct": lots[0]["pt_vs_close_pct"],
                          "trail_pct": (_f(float(trail_m) * float(sigma32.at[
                              pd.Timestamp(lot["entry_date"]), t]) * np.sqrt(h) * 100)
                              if trail_on else None),
                          "levels_basis": "last_close", "max_hold_sessions": h,
                          "sessions_left": lots[0]["sessions_left"], "lots": lots,
                          "pot_value": round(s["pot"], 2)})

    parking = None
    if spy is not None and str(cfg.port.get("bucket_park", "none")).upper() == "SPY":
        cur = sum(v["pot"] for v in st.values() if v["parked"]) / nav
        tgt = sum(v["pot"] for v in st.values() if v["status"] == "flat") / nav
        px = spy["raw_close"].reindex(panel.dates).ffill().loc[t_last] \
            if "raw_close" in spy else spy["adj_close"].reindex(panel.dates).ffill().loc[t_last]
        parking = {"ticker": "SPY", "target_weight": round(tgt, 5),
                   "current_weight": round(cur, 5), "delta_weight": round(tgt - cur, 5),
                   "last_close": _f(px),
                   "note": "idle pot cash is parked in SPY: sold at the open a pot "
                           "buys its stock, bought at the open after a pot exits"}
    deposited = unit * len(st)
    nav_s = res["nav"]
    curve_from = pd.Timestamp(min(v["funded"] for v in st.values())) if st else t_last
    curve = nav_s.loc[curve_from:]
    perf = {"start_value": deposited, "value": round(nav, 2),
            "pnl": round(nav - deposited, 2),
            "pnl_pct": round(nav / deposited - 1, 6) if deposited else None,
            "winners": sum(1 for x in pots if x["pnl"] > 0),
            "losers": sum(1 for x in pots if x["pnl"] < 0),
            "invested": round(sum(v["pot"] for v in st.values() if v["lot"] is not None), 2),
            "trades_closed": sum(x["trades_closed"] for x in pots),
            "realized_pnl": round(sum(x["realized_pnl"] for x in pots), 2),
            # the whole book's value per close since the pots were funded
            "curve": [{"date": str(d.date()), "value": round(float(v), 2)}
                      for d, v in curve.items()]}
    return {"buys": buys, "holds": holds, "sells": sells, "parking": parking,
            "pots": pots, "nav_units": round(nav, 2), "performance": perf}
