"""M14 — portfolio construction & sizing (L6; BP7, BP14, §I).

Daily sequence after close t (targets fill at open t+1 — the engine owns the lag):
 1. selection: decile-10 names passing meta gate / universe / earnings-skip
 1b. short sleeve (2026-09-17, [MAY]): `short_sel` names enter a second rotating
    tranche book with NEGATIVE weights; the two sleeves are scaled by
    `long_budget` / `short_budget` (core105: 0.5 / 0.5 of the book). No short
    sleeve and long_budget 1.0 -> bit-identical to the long-only construction.
 2. tranche refresh: 1/`tranches` of the book turns over daily (Stage-1 fixed
    15-session rotation; Stage-3 barrier exits supersede)
 3. raw weights within the entering tranche: (1/sigma32) * meta_mult
 4. single-name cap (3%), excess redistributed once to uncapped names
 5. vol targeting — applied as a causal post-pass on realized book returns
    (EWMA lambda=0.94, scale cap 1.5) via `vol_target_scale`
 6. regime multiplier on ML-book gross
 7. no-trade bands: drop |dw| < 20% of target weight or < 10 bps NAV
 8. hedge leg: short SPY sized to -sum(w_i * beta_i), band-filtered
 9. sleeve merge: momentum sleeve keeps its own risk budget (30% gross)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HEDGE_COL = "__SPY_HEDGE__"


def construct_targets(decile: pd.DataFrame, mask: pd.DataFrame, sigma32: pd.DataFrame,
                      beta: pd.DataFrame | None, gross_mult: pd.Series | None,
                      tranches: int = 15, single_name_cap: float = 0.03,
                      no_trade_band: float = 0.20, nav_band: float = 10e-4,
                      meta_mult: pd.DataFrame | None = None,
                      earnings_block: pd.DataFrame | None = None,
                      hedge: bool = True,
                      short_sel: pd.DataFrame | None = None,
                      long_budget: float = 1.0,
                      short_budget: float = 0.0) -> pd.DataFrame:
    """Returns daily target weights (decision-date indexed) incl. HEDGE_COL.
    Short-sleeve weights are negative; the single-name cap applies to |w|."""
    dates = decile.index
    cols = decile.columns
    W = np.zeros((len(dates), len(cols)))
    live: list[np.ndarray] = []                       # rotating tranche weight vectors
    prev_final = np.zeros(len(cols))
    sig = sigma32.to_numpy()
    dec = decile.to_numpy()
    msk = mask.to_numpy()
    mm = meta_mult.reindex_like(decile).to_numpy() if meta_mult is not None else None
    eb = earnings_block.reindex_like(decile).to_numpy() if earnings_block is not None else None
    hedge_w = np.zeros(len(dates))
    B = beta.reindex_like(decile).to_numpy() if beta is not None else None
    ss = (short_sel.reindex_like(decile).fillna(False).to_numpy(bool)
          if short_sel is not None else None)
    live_s: list[np.ndarray] = []                     # the short sleeve's tranches

    def _tranche(i: int, sel: np.ndarray) -> np.ndarray:
        tw = np.zeros(len(cols))
        if sel.any():
            iv = 1.0 / sig[i][sel]
            if mm is not None:
                iv = iv * np.nan_to_num(mm[i][sel], nan=1.0)
            if iv.sum() > 0:
                tw[sel] = iv / iv.sum()               # tranche gross = 1
        return tw

    for i in range(len(dates)):
        ok = msk[i] & np.isfinite(sig[i]) & (sig[i] > 0)
        sel = (dec[i] == 10) & ok
        if eb is not None:
            sel &= ~(eb[i] > 0)                        # earnings-skip rule (F8 option)
        live.append(_tranche(i, sel))
        if len(live) > tranches:
            live.pop(0)
        book = np.sum(live, axis=0) / tranches         # fixed 1/15 rotation (Stage 1)
        if ss is not None:
            sel_s = ss[i] & ok
            if eb is not None:
                sel_s &= ~(eb[i] > 0)
            live_s.append(_tranche(i, sel_s))
            if len(live_s) > tranches:
                live_s.pop(0)
            book = book * long_budget \
                - (np.sum(live_s, axis=0) / tranches) * short_budget
        elif long_budget != 1.0:
            book = book * long_budget

        # ---- single-name cap on |w| with one redistribution pass ----
        mag = np.abs(book)
        over = mag > single_name_cap
        if over.any():
            excess = float((mag[over] - single_name_cap).sum())
            mag[over] = single_name_cap
            under = (mag > 0) & ~over
            if under.any() and excess > 0:
                room = single_name_cap - mag[under]
                add = np.minimum(room, excess * mag[under] / mag[under].sum())
                mag[under] += add
            book = np.where(book < 0, -mag, mag)

        if gross_mult is not None:
            book = book * float(gross_mult.iloc[i])

        # ---- no-trade bands vs yesterday's final book ----
        dw = book - prev_final
        small = (np.abs(dw) < no_trade_band * np.maximum(np.abs(book), 1e-12)) \
            | (np.abs(dw) < nav_band)
        keep = small & (prev_final != 0) & (book != 0)
        book[keep] = prev_final[keep]
        # names leaving the book entirely always trade to 0 (exit is never banded)
        # (signed weights: a name flipping long<->short always trades)
        W[i] = book
        prev_final = book.copy()

        if hedge and B is not None:
            b = np.nan_to_num(B[i], nan=1.0)
            h = -float((book * b).sum())
            if abs(h - hedge_w[i - 1] if i else h) >= no_trade_band * abs(h) or i == 0:
                hedge_w[i] = h
            else:
                hedge_w[i] = hedge_w[i - 1]

    out = pd.DataFrame(W, index=dates, columns=cols)
    if hedge and B is not None:
        out[HEDGE_COL] = hedge_w
    return out


def vol_target_scale(book_returns: pd.Series, target_ann: float = 0.12,
                     cap: float = 1.5, lam: float = 0.94) -> pd.Series:
    """Causal vol-target multiplier from realized book returns (step 5 [IMPL]):
    sigma_t = EWMA(lambda) std of past returns; scale = min(target/sigma, cap), shifted 1."""
    var = book_returns.pow(2).ewm(alpha=1 - lam, min_periods=20).mean()
    sig_ann = np.sqrt(var * 252)
    return (target_ann / sig_ann).clip(upper=cap).shift(1).fillna(1.0)


def merge_sleeve(ml_book: pd.DataFrame, sleeve: pd.DataFrame,
                 sleeve_budget: float = 0.30) -> pd.DataFrame:
    """Sleeve occupies its own risk budget beside the ML book [IMPL: gross split]."""
    sleeve = sleeve.reindex_like(ml_book.drop(columns=[HEDGE_COL], errors="ignore")).fillna(0.0)
    merged = ml_book.drop(columns=[HEDGE_COL], errors="ignore") * (1 - sleeve_budget) \
        + sleeve * sleeve_budget
    if HEDGE_COL in ml_book:
        merged[HEDGE_COL] = ml_book[HEDGE_COL] * (1 - sleeve_budget)
    return merged
