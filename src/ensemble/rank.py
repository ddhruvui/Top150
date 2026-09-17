"""M10 — ensembling & score post-processing (BP7-BP9).

Per member, per day: scores -> cross-sectional fractional ranks (Q-017 rank mode,
C-11). Ensemble = equal-weight mean of member ranks [IMPL]; invariant to monotone
member-score transforms (T-06). Deciles cut per day over the masked universe;
decile 10 = top (M10-04).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.primitives.csnorm import cs_transform


def member_ranks(scores: dict[str, pd.DataFrame], mask: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {name: cs_transform(s, mask, mode="rank") for name, s in scores.items()}


def ensemble_rank(scores: dict[str, pd.DataFrame], mask: pd.DataFrame,
                  weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Weighted mean of per-day member ranks; equal weights by default (M10-02)."""
    ranks = member_ranks(scores, mask)
    if weights is None:
        weights = {k: 1.0 for k in ranks}
    tot = sum(weights.values())
    acc = None
    for k, r in ranks.items():
        w = weights.get(k, 0.0) / tot
        acc = r * w if acc is None else acc.add(r * w, fill_value=0.0)
    return acc.where(mask)


def select_long(ens: pd.DataFrame, mask: pd.DataFrame, cfg) -> pd.DataFrame:
    """Config-driven long selection (bool frame). Default `top_decile_long`
    reproduces deciles(...).eq(10) exactly; `top_n_long` takes the absolute
    top cfg.port.top_n names per day (aggressive concentrated books)."""
    if str(cfg.port.get("selection", "top_decile_long")) == "top_n_long":
        rk = ens.rank(axis=1, ascending=False, method="first")
        return rk.le(int(cfg.port.get("top_n", 20))) & mask
    return deciles(ens, mask).eq(10)


def select_short(ens: pd.DataFrame, mask: pd.DataFrame, cfg,
                 borrowable: pd.DataFrame | None = None) -> pd.DataFrame:
    """Config-driven SHORT selection (bool frame) — the single-name short sleeve
    the blueprint leaves as a [MAY] (port.selection: "short bottom decile if
    borrow economics allow"). `port.short_selection`:
      none           (default) an all-False frame -> the long-only book,
                     bit-identical to before the sleeve existed;
      bottom_decile  decile 1 of the ensemble rank (mirror of the long rule);
      bottom_n       the `port.short_n` lowest-ranked names per day.
    `borrowable` (bool frame, same shape) applies §I step 4: a name whose borrow
    fee is above `port.short_max_borrow_bps_yr` is skipped, never shorted."""
    mode = str(cfg.port.get("short_selection", "none"))
    if mode == "none":
        return pd.DataFrame(False, index=ens.index, columns=ens.columns)
    if mode == "bottom_n":
        rk = ens.rank(axis=1, ascending=True, method="first")
        sel = rk.le(int(cfg.port.get("short_n", 10))) & mask
    elif mode == "bottom_decile":
        sel = deciles(ens, mask).eq(1)
    else:
        raise ValueError(f"port.short_selection: unknown mode {mode!r}")
    if borrowable is not None:
        sel = sel & borrowable.reindex_like(sel).fillna(False).astype(bool)
    return sel.fillna(False).astype(bool)


def deciles(rank_frame: pd.DataFrame, mask: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Per-day decile of ensemble_rank over the masked universe; 10 = top (M10-04)."""
    x = rank_frame.where(mask)
    def cut(row):
        v = row.dropna()
        if len(v) < n:
            return row * np.nan
        # rank(method='first') before qcut: LGBM's L1 regularization emits few
        # distinct leaf values, and raw qcut with duplicates='drop' can lose the
        # top bin entirely (empty book). First-rank tie-break is deterministic
        # (G-10) and monotone-invariant (T-06).
        q = pd.qcut(v.rank(method="first"), n, labels=False) + 1
        return q.reindex(row.index)
    return x.apply(cut, axis=1)
