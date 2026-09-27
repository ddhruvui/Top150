"""Fixed-list universe (configs/system_core105.yaml): the configured tickers ARE
the universe. Covers the config read, membership construction and the two ways a
list can be wrong (a ticker absent from the tape, a ticker YAML turned into a bool).
"""
import importlib
import json

import pandas as pd
import pytest
import yaml

bm = importlib.import_module("src.data.build_market")

TAPE = {                      # ticker -> first session on the synthetic tape
    "AAPL": "2024-01-02",
    "ON": "2024-01-02",       # unquoted in YAML this is the boolean true
    "SPY": "2024-01-02",      # an ETF: kept, unlike in the ranking path
    "ARM": "2024-06-03",      # lists mid-sample -> member only from then on
}


def _write_tape(tmp_path):
    sessions = pd.bdate_range("2024-01-02", "2024-08-30")
    rows = []
    for t, first in TAPE.items():
        for d in sessions[sessions >= pd.Timestamp(first)]:
            rows.append({"date": d, "ticker": t, "open": 10.0, "high": 11.0,
                         "low": 9.0, "close": 10.0, "adjusted_close": 10.0,
                         "volume": 1_000_000})
    mp = tmp_path / "market_prices"
    mp.mkdir()
    pd.DataFrame(rows).to_parquet(mp / "part-2024.parquet", index=False)
    return mp


def _config(tmp_path, tickers, quoted=True):
    body = "universe:\n  size: %d\n  tickers:\n" % len(tickers)
    for t in tickers:
        body += ('    - "%s"\n' % t) if quoted else ("    - %s\n" % t)
    p = tmp_path / "system_test.yaml"
    p.write_text(body)
    return p


def test_config_list_is_read_verbatim(tmp_path, monkeypatch):
    p = _config(tmp_path, ["AAPL", "ON", "SPY", "aapl"])
    monkeypatch.setenv("SYSTEM_CONFIG", str(p))
    assert bm._fixed_universe() == ["AAPL", "ON", "SPY"]      # upper-cased, deduped


def test_no_config_list_means_the_ranking_path(tmp_path, monkeypatch):
    p = tmp_path / "plain.yaml"
    p.write_text("universe:\n  size: 150\n")
    monkeypatch.setenv("SYSTEM_CONFIG", str(p))
    assert bm._fixed_universe() is None
    monkeypatch.delenv("SYSTEM_CONFIG")
    assert bm._fixed_universe() is None


def test_unquoted_on_is_a_bool_and_is_rejected(tmp_path, monkeypatch):
    """YAML 1.1: `- ON` parses as True. Fail loudly instead of dropping the name."""
    p = _config(tmp_path, ["AAPL", "ON"], quoted=False)
    assert yaml.safe_load(p.read_text())["universe"]["tickers"] == ["AAPL", True]
    monkeypatch.setenv("SYSTEM_CONFIG", str(p))
    with pytest.raises(SystemExit) as e:
        bm._fixed_universe()
    assert "quote every ticker" in str(e.value)


def test_membership_starts_at_first_price(tmp_path, monkeypatch):
    mp = _write_tape(tmp_path)
    out = tmp_path / "m1x"
    monkeypatch.setattr(bm, "MP_DIR", mp)
    monkeypatch.setattr(bm, "MARKET_DIR", out)
    tickers = ["AAPL", "ON", "SPY", "ARM"]
    mem = bm.step2_universe_fixed([2024], tickers)

    assert set(mem["ticker"]) == set(tickers)                  # SPY kept: no fund rule
    refreshes = sorted(mem["refresh_date"].unique())
    assert len(refreshes) == 8                                 # Jan..Aug month-ends
    first_row = mem[mem["refresh_date"] == refreshes[0]]
    assert set(first_row["ticker"]) == {"AAPL", "ON", "SPY"}   # ARM had not listed
    arm = sorted(mem[mem["ticker"] == "ARM"]["refresh_date"])
    assert str(arm[0].date()) >= "2024-06-03" and len(arm) == 3
    assert (out / "universe_membership.parquet").exists()


def test_ticker_absent_from_the_tape_is_fatal(tmp_path, monkeypatch):
    mp = _write_tape(tmp_path)
    monkeypatch.setattr(bm, "MP_DIR", mp)
    monkeypatch.setattr(bm, "MARKET_DIR", tmp_path / "m1x")
    with pytest.raises(SystemExit) as e:
        bm.step2_universe_fixed([2024], ["AAPL", "BRK.B"])     # wrong spelling
    assert "BRK.B" in str(e.value)


def test_workset_is_exactly_the_list(tmp_path, monkeypatch):
    mp = _write_tape(tmp_path)
    out = tmp_path / "m1x"
    monkeypatch.setattr(bm, "MP_DIR", mp)
    monkeypatch.setattr(bm, "MARKET_DIR", out)
    sp500 = tmp_path / "nasdaq" / "SP500"
    sp500.mkdir(parents=True)
    (sp500 / "SHARADAR.json").write_text(json.dumps([{"ticker": "XOM"}]))
    monkeypatch.setattr(bm, "NASDAQ_DIR", tmp_path / "nasdaq")

    mem = bm.step2_universe_fixed([2024], ["AAPL", "ON"])
    bm.step3_workset([2024], mem, fixed=True)
    ws = pd.read_parquet(out / "workset_prices" / "part-2024.parquet")
    assert set(ws["ticker"]) == {"AAPL", "ON"}                 # no SP500 union
    man = json.loads((out / "_manifest.json").read_text())
    assert man["universe_mode"] == "fixed_list" and man["workset_names"] == 2


def test_shipped_core105_config_is_the_list_we_expect():
    cfg = yaml.safe_load(open("configs/system_core105.yaml"))
    t = cfg["universe"]["tickers"]
    assert all(isinstance(x, str) for x in t), "a ticker was parsed as a bool"
    assert len(t) == len(set(t)) == cfg["universe"]["size"] == 103
    for name in ("ON", "T", "BRK-B"):
        assert name in t
    for name in ("SPY", "QQQ"):         # removed 2026-09-27: the ranking only ever shorted them
        assert name not in t
    assert "BRK.B" not in t                                    # tape spelling
