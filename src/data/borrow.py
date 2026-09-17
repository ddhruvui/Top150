"""D-10 borrow fees: the M1 table plus the watchlist names M1 does not carry.

The download system builds `m1/borrow_fees.parquet` from `data_borrow/history/`,
which holds the 517 equities and NOT the ETFs. SPY and QQQ (and BRK-B) are fetched
separately into `data_borrow/watchlist/history/<TICKER>.json`, same row schema.
Since core105 trades SPY and QQQ, their real fees have to come from there instead
of the GC default.

Read-only, and no fetching: these files are already on the source volume, pulled
into /scratch by the pod prefetch (BORROW_DIR).

`data_borrow/watchlist/history_v2/` also exists (an all-time v2 backfill under an
`observations` key). It is NOT read here: it ends earlier than the free series
(2026-07-08 vs 2026-09-11 for SPY) and starts the same day, so it would only ever
make the table staler.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pandas as pd

COLS = ["ticker", "date", "fee_bps_yr"]


def watchlist_fees(borrow_dir: str | Path | None = None) -> pd.DataFrame:
    """Daily fees for the watchlist names (SPY, QQQ, ...) — empty if absent."""
    d = str(borrow_dir or os.environ.get("BORROW_DIR", "") or "")
    if not d:
        return pd.DataFrame(columns=COLS)
    hist = Path(d) / "watchlist" / "history"
    rows = []
    for p in sorted(glob.glob(str(hist / "*.json"))):
        try:
            recs = json.load(open(p))
        except (OSError, ValueError) as e:
            print(f"!! unreadable borrow file {p}: {e}", flush=True)
            continue
        if not isinstance(recs, list):
            continue
        t = Path(p).stem
        for r in recs:
            if isinstance(r, dict) and r.get("fee_bps_yr") is not None:
                rows.append({"ticker": str(r.get("ticker") or t),
                             "date": r.get("date"), "fee_bps_yr": r.get("fee_bps_yr")})
    if not rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["fee_bps_yr"] = pd.to_numeric(df["fee_bps_yr"], errors="coerce")
    return df.dropna(subset=["date", "fee_bps_yr"])[COLS]


def borrow_table(m1_fees: pd.DataFrame | None,
                 borrow_dir: str | Path | None = None) -> pd.DataFrame:
    """M1 fees + watchlist fees. M1 wins on a (ticker, date) it already has: it is
    the vetted layer, and the watchlist tree only has to fill what it lacks."""
    m1 = (m1_fees if m1_fees is not None else pd.DataFrame(columns=COLS))
    if len(m1):
        m1 = m1.loc[:, [c for c in COLS if c in m1.columns]].copy()
        m1["date"] = pd.to_datetime(m1["date"], errors="coerce")
    wl = watchlist_fees(borrow_dir)
    if not len(wl):
        return m1
    if len(m1):
        have = set(zip(m1["ticker"].astype(str), m1["date"]))
        wl = wl[[(t, d) not in have
                 for t, d in zip(wl["ticker"].astype(str), wl["date"])]]
        extra = sorted(set(wl["ticker"].astype(str)) - set(m1["ticker"].astype(str)))
    else:
        extra = sorted(set(wl["ticker"].astype(str)))
    if extra:
        print(f"borrow: +{len(wl):,} watchlist rows covering {extra} "
              f"(not in the M1 table)", flush=True)
    out = pd.concat([m1, wl], ignore_index=True) if len(wl) else m1
    return out.sort_values(["ticker", "date"]).reset_index(drop=True)
