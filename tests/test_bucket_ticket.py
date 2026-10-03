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


def test_pots_history_rebuilds_each_pot(tmp_path):
    import sys
    sys.path.insert(0, "tools")
    from build_reports import build_pots_history
    d = pd.to_datetime
    tr = pd.DataFrame({
        "ticker": ["A", "A", "B"],
        "entry_date": d(["2020-01-02", "2020-03-02", "2020-01-02"]),
        "fill_date": d(["2020-01-03", "2020-03-03", "2020-01-03"]),
        "exit_date": d(["2020-02-03", "2021-01-04", "2020-02-03"]),
        "bucket_before": [10_000.0, 10_990.0, 10_000.0],
        "notional": [9_900.0, 10_880.0, 9_900.0],
        "exit_ret_net": [0.1, -0.5, -0.2],
    })
    tr.to_parquet(tmp_path / "stage3_trades_ungated.parquet")
    h = build_pots_history(tmp_path)
    a = next(x for x in h["stocks"] if x["ticker"] == "A")
    assert a["end_value"] == round(10_990 - 0.5 * 10_880, 2)
    assert a["trades"] == 2 and a["wins"] == 1
    assert [p[1] for p in h["paths"]["A"]] == [10_000.0, 10_990.0, a["end_value"]]
    assert h["total"]["start_value"] == 20_000
    assert abs(h["total"]["end_value"] - (a["end_value"] + 8_020.0)) < 0.01
    assert h["book"][-1]["value"] == round(h["total"]["end_value"], 2)


def _cat_panel(panel, n=None):
    """The production panel: ticker columns are a CategoricalIndex."""
    from src.data.panel import Panel
    cols = pd.CategoricalIndex(panel.tickers, name="ticker")
    f = {k: getattr(panel, k).iloc[:n].set_axis(cols, axis=1)
         for k in ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
                   "raw_volume", "raw_close", "raw_open", "quarantined")}
    return Panel(sessions=panel.sessions[:n], **f)


def test_second_daily_run_reads_the_first_runs_file(rng, synth_panel, tmp_path):
    # 2026-10-02: day 2's predict died reading day 1's bucket_signals.parquet
    # (categorical column metadata). Two consecutive runs on the real layout.
    cm = CostModel(per_trade_bps=15)
    full = _cat_panel(synth_panel)
    ens = _ens(rng, synth_panel).set_axis(full.tickers, axis=1)
    mask = ens.notna()
    cfg = _cfg(str(synth_panel.dates[300].date()))
    day1 = _cat_panel(synth_panel, -1)
    a = bucket_book_live(ens.iloc[:-1], mask.iloc[:-1], day1,
                         day1.adj_close * 0 + 0.02, cm, cfg, None, tmp_path)
    pd.read_parquet(tmp_path / "bucket_signals.parquet")      # plain readable file
    b = bucket_book_live(ens, mask, full, full.adj_close * 0 + 0.02, cm, cfg, None,
                         tmp_path)
    rows = frozen_rows(tmp_path)
    assert len(rows) == len(synth_panel.dates) - 300
    assert rows.index[0] == synth_panel.dates[300]
    # day 1's decisions are kept verbatim on day 2
    pd.testing.assert_frame_equal(a["rows"], rows.iloc[:-1], check_freq=False)
    T = bucket_ticket(b["res"], full, full.adj_close * 0 + 0.02, cfg, ens.iloc[-1], None)
    assert len(T["pots"]) == len(synth_panel.tickers)


def test_reads_a_legacy_categorical_file(rng, synth_panel, tmp_path):
    cols = pd.CategoricalIndex(synth_panel.tickers, name="ticker")
    df = pd.DataFrame(rng.random((5, len(cols))), columns=cols,
                      index=synth_panel.dates[:5])
    df.to_parquet(tmp_path / "bucket_signals.parquet")       # how day 1 wrote it
    rows = frozen_rows(tmp_path)
    assert list(rows.columns) == [str(c) for c in synth_panel.tickers]
    np.testing.assert_allclose(rows.to_numpy(), df.to_numpy())
    assert (rows.index == synth_panel.dates[:5]).all()
