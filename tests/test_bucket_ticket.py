"""Live bucket ticket: frozen past decisions, schema the app reads, SPY leg."""
import numpy as np
import pandas as pd
from types import SimpleNamespace

from src.backtest.costs import CostModel
from src.live.bucket_ticket import bucket_book_live, bucket_ticket, frozen_rows


class _B(dict):
    def __getattr__(self, k):
        return self[k]


def _cfg(start):
    return SimpleNamespace(
        barrier=_B(m=1.5, h_days=10, tie_break="stop_first", trail_m=1.0),
        port=_B(book="buckets", bucket_q=0.9, bucket_window=60, bucket_min_periods=30,
                bucket_cycle=20, bucket_fallback_pct=0.5, bucket_fallback_last=5,
                bucket_park="SPY", bucket_unit=10_000, bucket_start=start))


def _spy(idx):
    c = pd.Series(400 * 1.0005 ** np.arange(len(idx)), index=idx)
    return pd.DataFrame({"adj_open": c, "adj_close": c, "raw_close": c})


def _ens(rng, panel):
    return pd.DataFrame(rng.random(panel.adj_close.shape), index=panel.dates,
                        columns=panel.tickers)


def test_ticket_schema_and_parking(rng, synth_panel, tmp_path):
    ens = _ens(rng, synth_panel)
    mask = ens.notna()
    cfg = _cfg(str(synth_panel.dates[200].date()))
    sig = synth_panel.adj_close * 0 + 0.02
    lb = bucket_book_live(ens, mask, synth_panel, sig, CostModel(per_trade_bps=15),
                          cfg, _spy(synth_panel.dates), tmp_path)
    T = bucket_ticket(lb["res"], synth_panel, sig, cfg, ens.iloc[-1], _spy(synth_panel.dates))
    assert len(T["pots"]) == synth_panel.adj_close.shape[1]
    # stocks + SPY target + exits' proceeds (parked next open) = the whole book
    w_stock = sum(r["target_weight"] for r in T["buys"] + T["holds"])
    w_exit = sum(x["pot_weight"] for x in T["pots"] if x["status"] == "due_exit")
    w_hold_cash = sum(x["pot_weight"] for x in T["pots"] if x["status"] == "holding") \
        - sum(r["target_weight"] for r in T["holds"])
    assert abs(w_stock + T["parking"]["target_weight"] + w_exit + w_hold_cash - 1) < 1e-3
    for r in T["buys"]:
        assert r["action"] == "BUY" and r["new_lot_weight"] == r["target_weight"]
        assert r["stop_pct"] < 0 < r["profit_take_pct"]
    for r in T["holds"]:
        assert r["lots"] and r["sessions_left"] <= 10
    assert (tmp_path / "bucket_signals.parquet").exists()


def test_past_decisions_are_frozen(rng, synth_panel, tmp_path):
    ens = _ens(rng, synth_panel)
    mask = ens.notna()
    cfg = _cfg(str(synth_panel.dates[250].date()))
    sig = synth_panel.adj_close * 0 + 0.02
    cm = CostModel(per_trade_bps=15)
    a = bucket_book_live(ens, mask, synth_panel, sig, cm, cfg, None, tmp_path)
    # the "refitted model" scores the past differently the next day
    ens2 = _ens(np.random.default_rng(7), synth_panel)
    ens2.iloc[-1] = ens.iloc[-1]
    b = bucket_book_live(ens2, mask, synth_panel, sig, cm, cfg, None, tmp_path)
    assert a["res"]["buckets"] == b["res"]["buckets"]
    assert len(frozen_rows(tmp_path)) == len(synth_panel.dates) - 250


def test_pot_performance_adds_up(rng, synth_panel, tmp_path):
    ens = _ens(rng, synth_panel)
    mask = ens.notna()
    cfg = _cfg(str(synth_panel.dates[200].date()))
    sig = synth_panel.adj_close * 0 + 0.02
    lb = bucket_book_live(ens, mask, synth_panel, sig, CostModel(per_trade_bps=15),
                          cfg, None, tmp_path)
    T = bucket_ticket(lb["res"], synth_panel, sig, cfg, ens.iloc[-1], None)
    P = T["performance"]
    n = len(T["pots"])
    assert P["start_value"] == 10_000 * n
    assert abs(P["value"] - sum(x["pot_value"] for x in T["pots"])) < 0.05 * n
    assert abs(P["pnl_pct"] - (P["value"] / P["start_value"] - 1)) < 1e-6
    for x in T["pots"]:
        assert abs(x["pnl_pct"] - (x["pot_value"] / 10_000 - 1)) < 1e-4
        assert x["wins"] <= x["trades_closed"]
        assert (x["open_ret_pct"] is None) == (x["status"] not in ("holding", "due_exit"))
    assert P["curve"][0]["date"] == str(synth_panel.dates[200].date())
    assert abs(P["curve"][-1]["value"] - P["value"]) < 0.05 * n
