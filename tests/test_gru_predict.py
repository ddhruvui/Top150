"""GRU heads in the live book (2026-09-27). The research book stage 3 judges has
always ranked with GRU members; the book predict traded had none. Now a full
refit fits them next to the LGBM heads and stores them as champions, and a daily
run scores the stored models on their OWN features — frozen until the next full
refit. Predict ranks with the members stage 2 admitted, read back from its report.
"""
import numpy as np
import pandas as pd
import pytest

from src.config import Cfg, load_config
from src.models.gru import GRUHead
from src.models.lgbm import LGBMHead
from src.models.store import ModelStore, decide_refit
from src.pipeline.common import admitted_from_report
from src.pipeline.predict import _gru_member


@pytest.fixture(scope="module")
def cfg_hash():
    return load_config("configs/system_core105.yaml")


def _small(cfg):
    d = cfg.to_dict()
    d["gru"].update(lookback=5, n_features=3, seed_ensemble=2, early_stop_patience=2)
    d["val"]["train_years"] = 1
    return Cfg(d)


def _data(rng, n_dates=90, n_names=12, n_feats=5):
    dates = pd.bdate_range("2024-01-01", periods=n_dates)
    names = pd.Index([f"T{i:02d}" for i in range(n_names)])
    idx = pd.MultiIndex.from_product([dates, names], names=["date", "ticker"])
    X = pd.DataFrame(rng.normal(size=(len(idx), n_feats)).astype(np.float32), index=idx,
                     columns=[f"f{j}" for j in range(n_feats)])
    y = X["f0"] - 0.5 * X["f1"] + rng.normal(0, 0.5, len(idx))
    return dates, names, X, y


class _Ledger:
    def __init__(self):
        self.rows = []

    def append(self, *a, **k):
        self.rows.append(a)


class _Head:
    """An LGBM head's only role for the GRU: rank the input features."""
    def top_importance(self, k):
        return ["f0", "f1", "f2"][:k]


def _recent_meta(sessions, config_hash):
    recent = str(sessions[max(0, sessions.searchsorted(
        pd.Timestamp.today().normalize()) - 3)].date())
    return {"mode": "full_refit", "parent": None, "train_through": recent,
            "full_train_through": recent, "valid_rank_ic": 0.03,
            "config_hash": config_hash, "stamp": {}}


def test_full_refit_stores_the_gru_and_a_daily_run_scores_it_unchanged(tmp_path, rng,
                                                                        cfg_hash):
    cfg, config_hash = cfg_hash
    cfg = _small(cfg)
    dates, names, X, y = _data(rng)
    store, ledger = ModelStore(tmp_path), _Ledger()
    kw = dict(store=store, cfg=cfg, feats=X, labels_wide=y.unstack("ticker"),
              train_dates=dates[:60], valid_dates=dates[60:80], score_dates=dates[-15:],
              tickers=names, seed=7, train_through=str(dates[79].date()),
              config_hash=config_hash, stamp={}, ledger=ledger, persist=True,
              keep_files=6)

    full, info = _gru_member(20, _Head(), "full", None, **kw)
    assert info["mode"] == "full_refit" and info["features"] == ["f0", "f1", "f2"]
    assert full.shape == (15, len(names)) and full.notna().all().all()
    assert [r[0] for r in ledger.rows] == ["gru_h20"]         # every fit is a G-09 trial
    meta = store.champion_meta("gru_h20")
    assert meta["feature_names"] == ["f0", "f1", "f2"] and meta["config_hash"] == config_hash
    assert meta["n_seeds"] == 2

    # the daily run never consults the (possibly warm-updated) LGBM head
    daily, info2 = _gru_member(20, None, "update", store.load_gru(20), **kw)
    assert info2["mode"] == "frozen"
    pd.testing.assert_frame_equal(daily, full)


def test_a_missing_or_stale_gru_champion_forces_a_full_refit(tmp_path, rng, cfg_hash):
    cfg, config_hash = cfg_hash
    store = ModelStore(tmp_path)
    sessions = pd.date_range("2024-01-01", periods=700, freq="B")
    meta = _recent_meta(sessions, config_hash)
    dates, _, X, y = _data(rng, n_dates=120, n_names=20)
    f = X.index.get_level_values("date")
    tr, va = f.isin(dates[:90]), f.isin(dates[90:])
    store.save_champion(LGBMHead(cfg, 20, 1).fit(X[tr], y[tr], X[va], y[va],
                                                 num_boost_round=20), meta)
    assert decide_refit(cfg, store, config_hash, sessions, [20])[0] == "update"

    mode, why = decide_refit(cfg, store, config_hash, sessions, [20], gru_horizons=[20])
    assert mode == "full" and "GRU" in why                  # admitted, never fitted

    gru = [GRUHead(3, 8, 1, 0.0)]
    store.save_gru(20, gru, ["f0", "f1", "f2"], meta)
    assert decide_refit(cfg, store, config_hash, sessions, [20],
                        gru_horizons=[20])[0] == "update"
    store.save_gru(20, gru, ["f0", "f1", "f2"], dict(meta, config_hash="deadbeef"))
    assert decide_refit(cfg, store, config_hash, sessions, [20],
                        gru_horizons=[20])[0] == "full"      # fitted under another config


def test_predict_reads_stage2s_admission_back_from_its_report(tmp_path):
    rep = tmp_path / "stage2_report.json"
    assert admitted_from_report(rep) is None
    # the 2026-09-27 rerun's stage 2 decision
    rep.write_text('{"members": {"lgbm_h5": {"RankIC": NaN}, "lgbm_h20": {"RankIC": 0.05},'
                   ' "lgbm_h60": {"RankIC": 0.036}, "gru_h5": {"RankIC": 0.021},'
                   ' "gru_h20": {"RankIC": 0.025}, "cnn_I5R20": {"RankIC": 0.0025}}}')
    assert admitted_from_report(rep) == {"lgbm_h20", "lgbm_h60", "gru_h5", "gru_h20"}
    rep.write_text('{"members": {"a": {"RankIC": 0.001}, "b": {"RankIC": NaN}}}')
    assert admitted_from_report(rep) == {"a", "b"}          # none pass -> all, like stage 3
