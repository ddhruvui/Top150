"""C-08 — THE cost model (G-07/G-15): one implementation serving backtests,
baselines, meta-labeling outcomes, and live estimation.

  cost_leg   = notional x (per_trade_bps + slippage_bps)/1e4
  borrow_day = short_notional x fee_bps_yr/1e4/252
               per-name fee from the iBorrowDesk table where it has one for that
               name on/before the date, else the GC default (cost.borrow_gc_bps_yr,
               0.3%/yr on core105). Charged on SHORT legs only.
  short_div  = dividend liability on short positions
"""
from __future__ import annotations

import pandas as pd


class CostModel:
    def __init__(self, per_trade_bps: float = 15.0, slippage_bps: float = 0.0,
                 borrow_gc_bps_yr: float = 50.0,
                 borrow_table: pd.DataFrame | None = None):
        """borrow_table: optional long df (date, ticker, fee_bps_yr) for hard-to-borrow names."""
        self.per_trade_bps = float(per_trade_bps)
        self.slippage_bps = float(slippage_bps)
        self.borrow_gc_bps_yr = float(borrow_gc_bps_yr)
        self._borrow = None
        if borrow_table is not None and len(borrow_table):
            b = borrow_table.copy()
            b["date"] = pd.to_datetime(b["date"])
            # The vendor leaves NULL fees on days it has no quote; keeping them
            # would return NaN for a name that has a perfectly good fee the day
            # before, and NaN silently poisons every cost downstream.
            b["fee_bps_yr"] = pd.to_numeric(b["fee_bps_yr"], errors="coerce")
            b = b[b["fee_bps_yr"].notna()]
            self._borrow = (b.set_index(["ticker", "date"])["fee_bps_yr"].sort_index()
                            if len(b) else None)

    # ---- per-leg / per-trip fractions -------------------------------------
    def leg_frac(self) -> float:
        return (self.per_trade_bps + self.slippage_bps) / 1e4

    def borrow_fee_bps(self, ticker: str | None = None, date=None) -> float:
        if self._borrow is not None and ticker is not None and date is not None:
            try:
                s = self._borrow.loc[ticker]
                s = s.loc[:pd.to_datetime(date)]
                if len(s):
                    v = float(s.iloc[-1])          # last quote on/before the date
                    if v == v:                     # not NaN
                        return v
            except KeyError:
                pass                               # not in the table (ETFs, pre-2015)
        return self.borrow_gc_bps_yr

    def borrow_fee_frame(self, dates, tickers) -> pd.DataFrame:
        """Wide (date x ticker) fee_bps_yr — the vectorized twin of
        borrow_fee_bps for engines that price a whole panel: the last quote on
        or before each date where the table has one, else the GC default."""
        dates = pd.DatetimeIndex(dates)
        out = pd.DataFrame(self.borrow_gc_bps_yr, index=dates, columns=list(tickers),
                           dtype=float)
        if self._borrow is None:
            return out
        wide = (self._borrow.reset_index()
                .pivot_table(index="date", columns="ticker", values="fee_bps_yr",
                             aggfunc="last"))
        keep = [t for t in tickers if t in wide.columns]
        if not keep:
            return out
        wide = wide[keep]
        # carry a quote forward across sessions it does not fall on; dates before
        # a name's first quote stay at the GC default (same as borrow_fee_bps)
        wide = (wide.reindex(wide.index.union(dates)).sort_index().ffill()
                .reindex(dates).fillna(self.borrow_gc_bps_yr))
        out.loc[:, keep] = wide.to_numpy()
        return out

    def borrowable(self, dates, tickers, max_bps_yr: float | None) -> pd.DataFrame:
        """§I step 4 — bool frame: the name's borrow fee on that date is at or
        below `max_bps_yr` (hard-to-borrow beyond the threshold -> skip). None
        -> everything is borrowable."""
        fees = self.borrow_fee_frame(dates, tickers)
        if max_bps_yr is None:
            return pd.DataFrame(True, index=fees.index, columns=fees.columns)
        return fees.le(float(max_bps_yr))

    def round_trip_frac(self, side: int = 1, holding_days: int = 0,
                        ticker: str | None = None, date=None,
                        short_div_frac: float = 0.0) -> float:
        """Total round-trip cost as a fraction of entry notional (M5-02 net labels)."""
        c = 2.0 * self.leg_frac()
        if side < 0:
            c += self.borrow_fee_bps(ticker, date) / 1e4 / 252.0 * max(0, holding_days)
            c += short_div_frac
        return c
