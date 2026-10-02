"""Per-name buckets: one position per bucket, proceeds compound in the name's
own bucket, causal own-history signal, and the cycle fallback."""
import numpy as np
import pandas as pd
from types import SimpleNamespace

from src.backtest.costs import CostModel
from src.backtest.engines.buckets import (bucket_candidates, own_percentile,
                                          run_bucket_backtest)


class _B(dict):
    def __getattr__(self, k):
        return self[k]


def _cfg(h=10):
    return SimpleNamespace(barrier=_B(m=1.5, h_days=h, tie_break="stop_first",
                                      trail_m=None))


def test_own_percentile_is_causal(rng, synth_panel):
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    mask = s.notna()
    a = own_percentile(s, mask, window=60, min_periods=30)
    s2 = s.copy()
    s2.iloc[200:] = rng.random(s2.iloc[200:].shape)
    b = own_percentile(s2, mask, window=60, min_periods=30)
    pd.testing.assert_frame_equal(a.iloc[:200], b.iloc[:200])


def test_every_name_trades_under_own_history_signal(rng, synth_panel):
    # name T00 is ALWAYS cross-sectionally worst, but has its own good days
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    s["T00"] = s["T00"] * 0.01 - 1.0
    mask = s.notna()
    pct = own_percentile(s, mask, window=60, min_periods=30).iloc[60:]
    res = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                              CostModel(per_trade_bps=15), _cfg(), q=0.9)
    assert "T00" in set(res["trades"]["ticker"])
    assert res["stats"]["names_ever_traded"] == synth_panel.adj_close.shape[1]


def test_one_position_per_bucket_and_compounding(rng, synth_panel):
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    mask = s.notna()
    pct = own_percentile(s, mask, window=60, min_periods=30).iloc[60:]
    cm = CostModel(per_trade_bps=15)
    res = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                              cm, _cfg(), q=0.8, bucket0=10_000.0, whole_shares=False)
    tr = res["trades"]
    for t, g in tr.groupby("ticker"):
        g = g.sort_values("fill_date")
        # never two lots at once: the next entry decides at/after the exit
        assert (g["entry_date"].iloc[1:].to_numpy()
                >= g["exit_date"].iloc[:-1].to_numpy()).all()
        # bucket after the last trade = 10k compounded through every trade
        expect = 10_000.0
        for r in g.itertuples():
            inv = expect * (1 - cm.leg_frac())
            expect += inv * r.exit_ret_net
        st = res["state"][t]
        if st["lot"] is not None:        # a lot still open: its pot before entry
            assert abs(st["lot"]["pot_before"] - expect) < 1e-6
        else:
            assert abs(res["buckets"][t] - expect) < 1e-6
    # book NAV is the sum of the buckets; nothing deposited beyond 40 x 10k
    assert abs(res["nav"].iloc[-1] - sum(res["buckets"].values())) < 1e-6
    assert res["stats"]["deposited"] == 40 * 10_000.0


def test_fallback_forces_one_entry_per_cycle(rng, synth_panel):
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    mask = s.notna()
    pct = own_percentile(s, mask, window=60, min_periods=30).iloc[60:]
    # q above 1 -> no signal ever fires; only the fallback can enter
    res = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                              CostModel(per_trade_bps=15), _cfg(h=10), q=1.01,
                              cycle=40, fallback_pct=0.5, fallback_last=10)
    tr = res["trades"]
    assert (tr["kind"] == "fallback").all()
    assert tr.groupby(["ticker", "block"]).size().max() == 1
    assert res["stats"]["coverage_incl_held_mean"] > 0.95


def test_candidates_fallback_only_late_in_block():
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    pct = pd.DataFrame({"X": np.linspace(0, 0.89, 80)}, index=idx)
    c = bucket_candidates(pct, pct.notna(), q=0.9, cycle=40, fallback_pct=0.5,
                          fallback_last=5)
    k = [idx.get_loc(d) % 40 for d in c["date"]]
    assert all(x >= 35 for x in k)


def _spy(idx, start=400.0, drift=0.0):
    c = pd.Series(start * (1 + drift) ** np.arange(len(idx)), index=idx)
    return pd.DataFrame({"adj_open": c, "adj_close": c})


def test_parked_cash_earns_spy_and_pays_both_legs(synth_panel):
    idx = synth_panel.dates
    mask = pd.DataFrame(True, index=idx, columns=synth_panel.tickers)
    pct = pd.DataFrame(0.0, index=idx, columns=synth_panel.tickers).iloc[100:]
    cm = CostModel(per_trade_bps=15)
    leg = cm.leg_frac()
    # q above 1: never enters, the whole pot sits in SPY from the day after funding
    res = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                              cm, _cfg(), q=1.01, park=_spy(idx, drift=0.001))
    n_held = len(idx) - 1 - 101               # opens 101 .. last close
    expect = 10_000 * (1 - leg) * 1.001 ** n_held
    assert abs(res["buckets"]["T00"] - expect) < 1e-6
    assert all(s["parked"] and s["status"] == "flat" for s in res["state"].values())
    assert abs(res["parked_last"] - res["nav"].iloc[-1]) < 1e-6


def test_parking_off_vs_flat_spy_only_costs_legs(rng, synth_panel):
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    mask = s.notna()
    pct = own_percentile(s, mask, window=60, min_periods=30).iloc[60:]
    cm = CostModel(per_trade_bps=0)          # zero cost + flat SPY == no parking
    kw = dict(q=0.9, whole_shares=False)
    a = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                            cm, _cfg(), **kw)
    b = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                            cm, _cfg(), park=_spy(synth_panel.dates), **kw)
    pd.testing.assert_series_equal(a["nav"], b["nav"], check_exact=False, rtol=1e-10)


def test_live_state_statuses(rng, synth_panel):
    s = pd.DataFrame(rng.random(synth_panel.adj_close.shape),
                     index=synth_panel.dates, columns=synth_panel.tickers)
    mask = s.notna()
    pct = own_percentile(s, mask, window=60, min_periods=30).iloc[60:]
    res = run_bucket_backtest(pct, mask, synth_panel, synth_panel.adj_close * 0 + 0.02,
                              CostModel(per_trade_bps=15), _cfg(h=10), q=0.9,
                              park=_spy(synth_panel.dates))
    st = res["state"]
    assert set(st) == set(synth_panel.tickers)
    kinds = {v["status"] for v in st.values()}
    assert kinds <= {"flat", "holding", "due_exit", "entering"}
    assert "holding" in kinds or "due_exit" in kinds
    # NAV = the pots; a pot with a lot open is never also parked or entering
    assert abs(sum(v["pot"] for v in st.values()) - res["nav"].iloc[-1]) < 1e-6
    for v in st.values():
        if v["lot"] is not None:
            assert not v["parked"] and v["entering"] is None
        if v["status"] == "entering":
            last = pct.index[-1]
            assert pct.at[last, [k for k, x in st.items() if x is v][0]] >= 0.9 \
                or v["entering"] == "fallback"
