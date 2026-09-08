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
        tgt_sh = int(np.floor(w * nav / px))
        cur_sh = int(current_shares.get(t, 0))
        d = tgt_sh - cur_sh
        if d == 0:
            continue
        orders.append(Order(t, "BUY" if d > 0 else "SELL", abs(d), "MOO", "DAY",
                            note=f"target_w={w:.4f}"))
        if cur_sh == 0 and d > 0:            # new entry: attach barrier orders (§G)
            thr = m * float(sigma32.get(t, np.nan)) * np.sqrt(h)
            if cap is not None:
                thr = min(thr, float(cap))
            if np.isfinite(thr):
                orders.append(Order(t, "SELL", abs(d), "STP", "GTC",
                                    stop_price=round(px * (1 - thr), 2),
                                    note="M5.2 stop (re-peg to fill)"))
                orders.append(Order(t, "SELL", abs(d), "LMT", "GTC",
                                    limit_price=round(px * (1 + thr), 2),
                                    note=f"M5.2 profit-take; vertical MOO t+{h + 1}"))
    return orders


def trail_width(sigma_entry: float, cfg) -> float | None:
    """Fractional trailing distance below the running high, or None when off."""
    tm = cfg.barrier.get("trail_m")
    if tm is None or float(tm) <= 0 or not np.isfinite(sigma_entry):
        return None
    return float(tm) * float(sigma_entry) * np.sqrt(int(cfg.barrier.h_days))


def stop_level(entry_price: float, sigma_entry: float, high_since_fill: float,
               cfg) -> tuple[float, str]:
    """Tonight's stop for an open long: the fixed M5.2 stop, raised to the
    trailing level once that is higher. Returns (price, 'fixed'|'trail')."""
    m, h = float(cfg.barrier.m), int(cfg.barrier.h_days)
    thr = m * float(sigma_entry) * np.sqrt(h)
    cap = cfg.barrier.get("thr_cap_pct")
    if cap is not None:
        thr = min(thr, float(cap))
    fixed = float(entry_price) * (1 - thr)
    w = trail_width(sigma_entry, cfg)
    if w is None or not np.isfinite(high_since_fill):
        return fixed, "fixed"
    trail = float(high_since_fill) * (1 - w)
    return (trail, "trail") if trail > fixed else (fixed, "fixed")


def trailing_stops(positions: pd.DataFrame, cfg) -> list[Order]:
    """Nightly re-peg of the GTC stop on every open long. `positions` columns:
    ticker, shares, entry_price, sigma_entry, high_since_fill (raw-price basis,
    fill session onward). One SELL STP per position, REPLACING the standing
    stop; the note says whether it is the fixed or the trailing level."""
    orders: list[Order] = []
    if positions is None or not len(positions):
        return orders
    for r in positions.itertuples(index=False):
        sh = int(getattr(r, "shares", 0))
        if sh <= 0:
            continue
        px, kind = stop_level(r.entry_price, r.sigma_entry, r.high_since_fill, cfg)
        orders.append(Order(str(r.ticker), "SELL", sh, "STP", "GTC",
                            stop_price=round(px, 2),
                            note=f"M5.2 {kind} stop re-peg (replaces standing stop)"))
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
