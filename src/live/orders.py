"""M18 — nightly order generation (§H, §I, BP16). RESEARCH/PAPER SIDE.

Turns M14 target weights into an order FILE (shares from RAW prices, G-03/M14-01)
with the M5.2 barrier orders attached. Actual submission to IBKR (ib_async) is a
separate, deliberately manual step: this module never places trades on its own.

Order sequence (§2.3 step 9): diff targets vs current book -> desired d-shares
using raw close [IMPL: floor(dw x NAV / raw_close)] -> PDT pre-check -> MOO
orders + GTC stop/profit-take for new entries -> vertical-barrier MOO schedule.

Trailing stop (barrier.trail_m, adopted 2026-09-08): the engine ratchets the
stop to high_since_fill x (1 - trail_m*sigma_entry*sqrt(h)) using the level
known at the prior close. Live, that is a plain GTC STP order whose stop price
is REPLACED every night: `trailing_stops()` emits one SELL STP per held
position at max(fixed stop, trailing level), computed from the position's own
fill price, entry sigma and running high (the paper book records all three).
A native broker TRAIL order is deliberately not used — it would trail intraday
on the last print, which is not what was backtested.

Short sleeve (2026-09-17): a NEGATIVE target weight is a short sale — SELL MOO
to open, with a BUY STP above the reference price as the M5.2 stop and a BUY
LMT below it as the profit-take; the vertical exit is a BUY MOO cover. The
nightly re-peg lowers a short's GTC stop to low_since_fill x (1 + trail),
never above the fixed stop (the mirror of the long ratchet). Requires a
margin account (G-14: a cash account cannot short).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.compliance import PDTCounter


@dataclass
class Order:
    ticker: str
    action: str            # BUY / SELL
    quantity: int
    order_type: str        # MOO / STP / LMT
    tif: str               # DAY / GTC
    limit_price: float | None = None
    stop_price: float | None = None
    note: str = ""


def whole_shares(weight: float, nav: float, price: float) -> int:
    """Whole shares for a weight slot — floor(|w| x NAV / price), signed by the
    side (a short is -|shares|). Never fractional: a slot that comes to less
    than one share is 0, and generate_orders then emits NO order for it
    (G-03: shares from raw prices; M14-01: weights become shares only here)."""
    if not np.isfinite(price) or price <= 0 or not np.isfinite(weight):
        return 0
    n = int(np.floor(abs(float(weight)) * float(nav) / float(price)))
    return -n if weight < 0 else n


def generate_orders(target_weights: pd.Series, current_shares: pd.Series,
                    raw_close: pd.Series, nav: float, sigma32: pd.Series,
                    cfg, pdt: PDTCounter | None = None,
                    as_of=None) -> list[Order]:
    m, h = float(cfg.barrier.m), int(cfg.barrier.h_days)
    cap = cfg.barrier.get("thr_cap_pct")
    orders: list[Order] = []
    for t, w in target_weights.items():
        px = raw_close.get(t, np.nan)
        if not np.isfinite(px) or px <= 0:
            continue
        # WHOLE shares, rounded toward zero on either side (a short is -|shares|);
        # a slot under one share rounds to 0 and produces no order
        tgt_sh = whole_shares(w, nav, px)
        cur_sh = int(current_shares.get(t, 0))
        d = tgt_sh - cur_sh
        if d == 0:
            continue
        short_leg = d < 0 and tgt_sh < 0
        orders.append(Order(t, "BUY" if d > 0 else "SELL", abs(d), "MOO", "DAY",
                            note=f"target_w={w:.4f}"
                                 + (" (short sale)" if short_leg else "")))
        if cur_sh == 0 and d != 0:           # new entry: attach barrier orders (§G)
            thr = m * float(sigma32.get(t, np.nan)) * np.sqrt(h)
            if cap is not None:
                thr = min(thr, float(cap))
            if not np.isfinite(thr):
                continue
            if d > 0:                        # long: stop below, profit-take above
                orders.append(Order(t, "SELL", abs(d), "STP", "GTC",
                                    stop_price=round(px * (1 - thr), 2),
                                    note="M5.2 stop (re-peg to fill)"))
                orders.append(Order(t, "SELL", abs(d), "LMT", "GTC",
                                    limit_price=round(px * (1 + thr), 2),
                                    note=f"M5.2 profit-take; vertical MOO t+{h + 1}"))
            else:                            # short: stop above, profit-take below
                orders.append(Order(t, "BUY", abs(d), "STP", "GTC",
                                    stop_price=round(px * (1 + thr), 2),
                                    note="M5.2 stop, short cover (re-peg to fill)"))
                orders.append(Order(t, "BUY", abs(d), "LMT", "GTC",
                                    limit_price=round(px * (1 - thr), 2),
                                    note=f"M5.2 profit-take, short cover; "
                                         f"vertical BUY MOO t+{h + 1}"))
    return orders


def trail_width(sigma_entry: float, cfg) -> float | None:
    """Fractional trailing distance below the running high, or None when off."""
    tm = cfg.barrier.get("trail_m")
    if tm is None or float(tm) <= 0 or not np.isfinite(sigma_entry):
        return None
    return float(tm) * float(sigma_entry) * np.sqrt(int(cfg.barrier.h_days))


def stop_level(entry_price: float, sigma_entry: float, high_since_fill: float,
               cfg, side: int = 1) -> tuple[float, str]:
    """Tonight's stop for an open position: the fixed M5.2 stop, ratcheted to
    the trailing level once that is tighter. For a long (side +1) the third
    argument is the HIGH since fill and the stop only ever rises; for a short
    (side -1) pass the LOW since fill and the stop only ever falls.
    Returns (price, 'fixed'|'trail')."""
    m, h = float(cfg.barrier.m), int(cfg.barrier.h_days)
    thr = m * float(sigma_entry) * np.sqrt(h)
    cap = cfg.barrier.get("thr_cap_pct")
    if cap is not None:
        thr = min(thr, float(cap))
    w = trail_width(sigma_entry, cfg)
    if int(side) < 0:
        fixed = float(entry_price) * (1 + thr)
        if w is None or not np.isfinite(high_since_fill):
            return fixed, "fixed"
        trail = float(high_since_fill) * (1 + w)          # off the running LOW
        return (trail, "trail") if trail < fixed else (fixed, "fixed")
    fixed = float(entry_price) * (1 - thr)
    if w is None or not np.isfinite(high_since_fill):
        return fixed, "fixed"
    trail = float(high_since_fill) * (1 - w)
    return (trail, "trail") if trail > fixed else (fixed, "fixed")


def trailing_stops(positions: pd.DataFrame, cfg) -> list[Order]:
    """Nightly re-peg of the GTC stop on every open position. `positions`
    columns: ticker, shares (negative = short), entry_price, sigma_entry,
    high_since_fill (raw-price basis, fill session onward) and, for shorts,
    low_since_fill. One SELL STP per long / BUY STP per short, REPLACING the
    standing stop; the note says whether it is the fixed or the trailing level."""
    orders: list[Order] = []
    if positions is None or not len(positions):
        return orders
    for r in positions.itertuples(index=False):
        sh = int(getattr(r, "shares", 0))
        if sh == 0:
            continue
        if sh > 0:
            px, kind = stop_level(r.entry_price, r.sigma_entry, r.high_since_fill, cfg)
            orders.append(Order(str(r.ticker), "SELL", sh, "STP", "GTC",
                                stop_price=round(px, 2),
                                note=f"M5.2 {kind} stop re-peg (replaces standing stop)"))
        else:
            low = getattr(r, "low_since_fill", np.nan)
            px, kind = stop_level(r.entry_price, r.sigma_entry, low, cfg, side=-1)
            orders.append(Order(str(r.ticker), "BUY", -sh, "STP", "GTC",
                                stop_price=round(px, 2),
                                note=f"M5.2 {kind} stop re-peg, short cover "
                                     f"(replaces standing stop)"))
    return orders


def write_order_file(orders: list[Order], out_path: str | Path, stamp: dict,
                     kill_switch_active: bool = False) -> None:
    payload = {"stamp": stamp, "kill_switch_active": kill_switch_active,
               "orders": [] if kill_switch_active else [asdict(o) for o in orders],
               "note": "Submission is manual. This file is research output, "
                       "not an instruction to trade."}
    Path(out_path).write_text(json.dumps(payload, indent=2))


def measure_slippage(fills: pd.DataFrame, official_open: pd.Series) -> pd.DataFrame:
    """Per fill: slip_bps = side x (fill - official_open)/official_open x 1e4 (§H).
    Rolling median feeds M15-03 once >= 60 fills exist."""
    df = fills.copy()
    op = official_open.reindex(df["ticker"]).to_numpy()
    df["slip_bps"] = np.sign(df["qty"]) * (df["price"] - op) / op * 1e4
    return df


def kill_switch(daily_pnl_frac: float, cfg) -> bool:
    """BP16: realized day loss <= -ops.max_daily_loss_pct x NAV -> halt new orders."""
    return daily_pnl_frac <= -float(cfg.ops.max_daily_loss_pct)


def decay_monitor(live_daily: pd.Series, backtest_sharpe: float,
                  window: int = 63) -> dict:
    """G-11/G-16: rolling 63d live Sharpe < 1/2 backtest for 2+ quarters ->
    retrain-or-retire."""
    from src.validation.metrics import sharpe
    if len(live_daily) < window:
        return {"status": "insufficient_history", "n": len(live_daily)}
    roll = live_daily.rolling(window).apply(
        lambda x: np.sqrt(252) * x.mean() / x.std() if x.std() > 0 else np.nan)
    breach = roll < 0.5 * backtest_sharpe
    consec = breach[::-1].cumprod().sum() if len(breach) else 0
    return {"status": "retire_or_retrain" if consec >= 126 else "healthy",
            "rolling_sharpe_last": float(roll.iloc[-1]) if np.isfinite(roll.iloc[-1]) else None,
            "sessions_in_breach": int(consec)}
