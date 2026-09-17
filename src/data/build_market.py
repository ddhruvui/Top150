#!/usr/bin/env python3
"""Whole-market panel + survivorship-free universe (G-05/BP1) from eod_bulk.

Runs ON the pod (the day-files only exist on the volume). Steps:

 1. data/eod_bulk/US/<DATE>.json  ->  market_prices/part-YYYY.parquet
    (date, ticker, open, high, low, close, adjusted_close, volume) — every
    listed AND delisted US name, the survivorship-free price record.
 2. 63d rolling median dollar volume per name -> monthly top-N membership with
    10% hysteresis + min_price filter (Q-003 mechanics, next-session inclusion
    applied downstream) -> universe_membership.parquet (date, ticker  rows at
    monthly refresh granularity).
    FIXED-LIST MODE: when the config named by SYSTEM_CONFIG carries
    universe.tickers, that list IS the universe — no ranking, no hysteresis, no
    min_price, no fund exclusion — and each name is a member from the first
    month-end it has prices (never back-dated to before it listed).
 3. Workset = every name ever selected  (+ Sharadar SP500 ever-members)  ->
    workset_prices/part-YYYY.parquet — the compact panel Stage 1+ actually loads.
    In fixed-list mode the workset is exactly the list.

Outputs land in MARKET_DIR (default /workspace/results/Core105/m1x105). EODHD `adjusted_close` is
the fallback total-return factor source for names Sharadar doesn't cover; the
M1 adjustment_factors override where present (handled at panel-build time).

Env: EOD_BULK_DIR, MARKET_DIR, M1_DIR, UNIVERSE_SIZE, MIN_PRICE, SYSTEM_CONFIG.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

BULK_DIR = Path(os.environ.get("EOD_BULK_DIR", "/workspace/data/eod_bulk/US"))
# Never the volume-root m1x/: on the mounted data volume that is the download
# system's parsed tree, which this repo only reads.
MARKET_DIR = Path(os.environ.get("MARKET_DIR", "/workspace/results/Core105/m1x105"))
# Read location for the per-year market_prices parts. Defaults to this build's
# own output; point it at an EXISTING build (e.g. the production m1x pulled
# read-only over S3) together with SKIP_BULK=1 to re-derive membership/workset
# at a different UNIVERSE_SIZE without re-parsing the eod_bulk day-files.
MP_DIR = Path(os.environ.get("MARKET_PRICES_DIR", str(MARKET_DIR / "market_prices")))
M1_DIR = Path(os.environ.get("M1_DIR", "/workspace/m1"))
NASDAQ_DIR = Path(os.environ.get("NASDAQ_DIR", "/workspace/data_nasdaq"))
UNIVERSE_SIZE = int(os.environ.get("UNIVERSE_SIZE", "1000"))
MIN_PRICE = float(os.environ.get("MIN_PRICE", "5.0"))
HYSTERESIS = float(os.environ.get("HYSTERESIS", "0.10"))
DV_WINDOW = int(os.environ.get("DV_WINDOW", "63"))
PRUNE_K = int(os.environ.get("PRUNE_K", "3000"))
# ENTITIES_PATH (m1 entities.parquet): when set, ranking considers only names
# with a Sharadar entity whose category is not a fund/note — the same G-05/D-13
# discipline membership_mask applies later, moved up so fund tickers don't
# occupy universe slots (matters at small UNIVERSE_SIZE).
ENTITIES_PATH = os.environ.get("ENTITIES_PATH", "")

KEEP = ["date", "ticker", "open", "high", "low", "close", "adjusted_close", "volume"]


def _fixed_universe() -> list[str] | None:
    """universe.tickers from SYSTEM_CONFIG, or None for the dollar-volume ranking.

    The list lives in the hashed config on purpose: config_hash is the SHA-256 of
    that file, so changing the universe forces a full refit downstream.
    """
    cfg_path = os.environ.get("SYSTEM_CONFIG", "")
    if not cfg_path:
        return None
    p = Path(cfg_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[2] / cfg_path
    if not p.exists():
        print(f"WARN SYSTEM_CONFIG={cfg_path} not found — using the ranking path",
              flush=True)
        return None
    import yaml
    cfg = yaml.safe_load(p.read_text()) or {}
    raw = ((cfg.get("universe") or {}).get("tickers")) or None
    if raw is None:
        return None
    # YAML 1.1 turns an unquoted ON into True (ON Semiconductor) — the config
    # quotes every ticker, and a stray bool here means someone unquoted one.
    bad = [t for t in raw if not isinstance(t, str) or not t.strip()]
    if bad:
        sys.exit(f"FATAL: universe.tickers holds non-string entries {bad!r} — "
                 "quote every ticker in the config (YAML reads ON/NO as booleans)")
    out, seen = [], set()
    for t in (str(x).strip().upper() for x in raw):
        if t not in seen:
            seen.add(t); out.append(t)
    return out


def _load_json(p: str):
    try:
        if p.endswith(".gz"):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"WARN unreadable {p}: {e}", flush=True)
        return None


def step1_market_prices() -> list[int]:
    """Day-files -> per-year parquet. Skips years already built and complete."""
    (MARKET_DIR / "market_prices").mkdir(parents=True, exist_ok=True)
    files = sorted(glob.glob(str(BULK_DIR / "*.json"))
                   + glob.glob(str(BULK_DIR / "*.json.gz")))
    by_year: dict[int, list[str]] = defaultdict(list)
    for p in files:
        d = os.path.basename(p).split(".")[0]
        if len(d) == 10:
            by_year[int(d[:4])].append(p)
    years = sorted(by_year)
    marker = MARKET_DIR / "market_prices" / "_built.json"
    built = json.loads(marker.read_text()) if marker.exists() else {}
    for y in years:
        n_files = len(by_year[y])
        if str(y) in built and built[str(y)] == n_files:
            continue
        frames = []
        for p in by_year[y]:
            rows = _load_json(p)
            if not rows:
                continue
            df = pd.DataFrame(rows)
            code = df.get("code", df.get("ticker"))
            date = df.get("date")
            if date is None:      # some vintages carry only the filename date
                date = os.path.basename(p).split(".")[0]
            out = pd.DataFrame({
                "date": date, "ticker": code,
                "open": pd.to_numeric(df.get("open"), errors="coerce"),
                "high": pd.to_numeric(df.get("high"), errors="coerce"),
                "low": pd.to_numeric(df.get("low"), errors="coerce"),
                "close": pd.to_numeric(df.get("close"), errors="coerce"),
                "adjusted_close": pd.to_numeric(df.get("adjusted_close"), errors="coerce"),
                "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
            })
            frames.append(out.dropna(subset=["close"]))
        if frames:
            yr = pd.concat(frames, ignore_index=True)
            yr["date"] = yr["date"].astype(str).str[:10]
            yr = yr.drop_duplicates(["date", "ticker"], keep="last")
            yr[KEEP].to_parquet(MARKET_DIR / "market_prices" / f"part-{y}.parquet",
                                index=False)
            built[str(y)] = n_files
            marker.write_text(json.dumps(built))
            print(f"OK market_prices {y}: {len(yr):,} rows from {n_files} day-files",
                  flush=True)
    return years


def _eligible_stocks() -> set[str] | None:
    """ENTITIES_PATH -> tickers rankable as stocks (dot and dash spellings)."""
    if not ENTITIES_PATH:
        return None
    ents = pd.read_parquet(ENTITIES_PATH)
    cat = ents.get("category", pd.Series(dtype=str)).fillna("")
    # same categories as src/data/market.py fund_tickers (standalone script — no src import)
    is_fund = cat.str.contains("ETF|ETN|ETD|CEF|IDX|Fund", case=False, regex=True)
    stocks = set(ents.loc[~is_fund, "ticker"].astype(str))
    stocks |= {t.replace(".", "-") for t in stocks}
    print(f"eligible-stock filter: {len(stocks):,} entity names (funds/aliens excluded)",
          flush=True)
    return stocks


def step2_universe_fixed(years: list[int], tickers: list[str]) -> pd.DataFrame:
    """The configured list IS the universe; membership starts at first price."""
    frames = []
    for y in years:
        p = MP_DIR / f"part-{y}.parquet"
        if not p.exists():
            continue
        frames.append(pd.read_parquet(p, columns=["date", "ticker"],
                                      filters=[("ticker", "in", tickers)]))
    if not frames:
        sys.exit(f"FATAL: no market_prices parts under {MP_DIR}")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    first = px.groupby(px["ticker"].astype(str))["date"].min()
    missing = [t for t in tickers if t not in first.index]
    if missing:
        sys.exit(f"FATAL: {len(missing)} configured ticker(s) have no prices on the "
                 f"tape at all: {missing} — fix universe.tickers (tape spelling, "
                 "e.g. BRK-B not BRK.B) or wait for the download system to cover them")
    sess = pd.DatetimeIndex(sorted(px["date"].unique()))
    me = pd.DatetimeIndex(sess.to_series().groupby([sess.year, sess.month]).max())
    rows = [{"refresh_date": d, "ticker": t} for d in me for t in tickers if first[t] <= d]
    mem = pd.DataFrame(rows)
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    mem.to_parquet(MARKET_DIR / "universe_membership.parquet", index=False)
    late = {t: str(first[t].date()) for t in tickers if first[t] > me[0]}
    print(f"universe_membership (FIXED list): {len(mem):,} rows over {len(me)} "
          f"refreshes, {mem['ticker'].nunique()} names; {len(late)} joined after the "
          f"first refresh", flush=True)
    if late:
        print("  first price: " + ", ".join(f"{t}@{d}" for t, d in sorted(late.items())),
              flush=True)
    return mem


def step2_universe(years: list[int]) -> pd.DataFrame:
    """Monthly top-N by 63d median dollar volume, hysteresis, min_price."""
    eligible = _eligible_stocks()
    cols = ["date", "ticker", "close", "volume"]
    dv_parts, px_me_parts = [], []
    for y in years:
        p = MP_DIR / f"part-{y}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=cols)
        if eligible is not None:
            df = df[df["ticker"].isin(eligible)]
        df["date"] = pd.to_datetime(df["date"])
        df["dv"] = df["close"] * df["volume"]
        # PRUNE: a name outside this year's top PRUNE_K by median dv cannot reach a
        # 63d-median top-UNIVERSE_SIZE rank; 3x buffer, logged [IMPL memory guard]
        keep = (df.groupby("ticker")["dv"].median()
                  .nlargest(max(PRUNE_K, UNIVERSE_SIZE * 3)).index)
        df = df[df["ticker"].isin(keep)]
        # per-year pivots, float32 — full-market wide in float64 would be ~10 GB
        dv_parts.append(df.pivot_table(index="date", columns="ticker", values="dv",
                                       aggfunc="last").astype(np.float32))
        pxy = df.pivot_table(index="date", columns="ticker", values="close",
                             aggfunc="last").astype(np.float32)
        px_me_parts.append(pxy.groupby([pxy.index.year, pxy.index.month]).tail(1))
        del df, pxy
    wide = pd.concat(dv_parts).sort_index()
    del dv_parts
    px_me = pd.concat(px_me_parts).sort_index()
    del px_me_parts
    print(f"dv panel: {wide.shape[0]:,} sessions x {wide.shape[1]:,} names", flush=True)
    # rolling median in COLUMN CHUNKS, keeping only month-end rows (4 GB pod budget)
    me_mask = wide.index.isin(
        wide.index.to_series().groupby([wide.index.year, wide.index.month]).max())
    me_rows = wide.index[me_mask]
    med_cols = []
    CHUNK = 4000
    for c0 in range(0, wide.shape[1], CHUNK):
        block = wide.iloc[:, c0:c0 + CHUNK]
        med_cols.append(block.rolling(DV_WINDOW, min_periods=DV_WINDOW // 2)
                        .median().loc[me_rows].astype(np.float32))
    me = pd.concat(med_cols, axis=1)
    del med_cols, wide
    members = []
    current: set[str] = set()
    for d, row in me.iterrows():
        m = row.dropna()
        m = m[px_me.loc[d].reindex(m.index) >= MIN_PRICE]
        if m.empty:
            continue
        rank = m.rank(ascending=False, method="first")
        entrants = set(rank[rank <= UNIVERSE_SIZE].index)
        stay = {t for t in current if rank.get(t, np.inf) <= UNIVERSE_SIZE * (1 + HYSTERESIS)}
        current = entrants | stay
        members.append(pd.DataFrame({"refresh_date": d, "ticker": sorted(current)}))
    mem = pd.concat(members, ignore_index=True)
    MARKET_DIR.mkdir(parents=True, exist_ok=True)   # SKIP_BULK runs never hit step1's mkdir
    mem.to_parquet(MARKET_DIR / "universe_membership.parquet", index=False)
    print(f"universe_membership: {len(mem):,} rows over "
          f"{mem['refresh_date'].nunique()} refreshes, "
          f"{mem['ticker'].nunique():,} distinct names ever", flush=True)
    return mem


def step3_workset(years: list[int], mem: pd.DataFrame, fixed: bool = False) -> None:
    workset = set(mem["ticker"].unique())
    # A fixed universe is exactly itself: no SP500 union, which would drag in
    # hundreds of names the book must never hold.
    sp = None if fixed else _load_json(str(NASDAQ_DIR / "SP500" / "SHARADAR.json"))
    if sp:
        workset |= {r.get("ticker") for r in sp if r.get("ticker")}
    print(f"workset: {len(workset):,} names", flush=True)
    (MARKET_DIR / "workset_prices").mkdir(parents=True, exist_ok=True)
    for y in years:
        p = MP_DIR / f"part-{y}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        df = df[df["ticker"].isin(workset)]
        df.to_parquet(MARKET_DIR / "workset_prices" / f"part-{y}.parquet", index=False)
    (MARKET_DIR / "_manifest.json").write_text(json.dumps({
        "universe_size": UNIVERSE_SIZE, "min_price": MIN_PRICE,
        "hysteresis": HYSTERESIS, "dv_window": DV_WINDOW,
        "workset_names": len(workset),
        "market_prices_dir": str(MP_DIR),
        "universe_mode": "fixed_list" if fixed else "top_dollar_volume",
        "eligible_stock_filter": bool(ENTITIES_PATH) and not fixed}))
    print("workset_prices written", flush=True)


def main() -> int:
    if os.environ.get("SKIP_BULK"):
        years = sorted(int(Path(p).stem.split("-")[1])
                       for p in glob.glob(str(MP_DIR / "part-*.parquet")))
        if not years:
            print(f"FATAL: SKIP_BULK set but no market_prices parts at {MP_DIR}",
                  file=sys.stderr)
            return 1
        print(f"SKIP_BULK: reusing {len(years)} year-parts from {MP_DIR}", flush=True)
    else:
        if not BULK_DIR.exists():
            print(f"FATAL: no eod_bulk at {BULK_DIR}", file=sys.stderr)
            return 1
        years = step1_market_prices()
        if not years:
            print("FATAL: no day-files parsed", file=sys.stderr)
            return 1
    fixed = _fixed_universe()
    if fixed:
        print(f"universe: FIXED list of {len(fixed)} names from "
              f"{os.environ.get('SYSTEM_CONFIG')} (no ranking, no fund exclusion)",
              flush=True)
        mem = step2_universe_fixed(years, fixed)
    else:
        mem = step2_universe(years)
    step3_workset(years, mem, fixed=bool(fixed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
