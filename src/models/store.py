"""Champion model store — the continual-learning half of the predict job.

Boosters persist on the network volume between daily runs so learning CONTINUES
instead of restarting: each day the champion is warm-continued on the newest
labeled window (LightGBM init_model), both models are scored on the SAME purged
validation window, and the better one keeps the crown. A full from-scratch refit
happens on the `continual.full_refit_sessions` cadence (= val.retrain_cadence)
or whenever config/features change, so drift can never accumulate unchecked.

Layout under MODEL_DIR (pods: /workspace/results/Core105/models; the config's
`continual.model_dir` is only the fallback when MODEL_DIR is unset):
    lgbm_h{n}/champion.json            pointer + meta of the reigning model
    lgbm_h{n}/model-<through>-<mode>.txt   booster text, truncated at best_iteration
    gru_h{n}/champion.json             pointer + meta (input features, architecture)
    gru_h{n}/model-<through>-full_refit.pt   the seed ensemble's state dicts

GRU heads (2026-09-27) are fitted only by a full refit — ~1 h of CPU for three
horizons — and are frozen between full refits; the daily run only scores them.

Every fit — adopted or rejected — is appended to the G-09 trials ledger by the
caller: a rejected challenger is still an evaluated configuration in DSR's N.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.models.lgbm import LGBMHead

CHAMPION = "champion.json"


class ModelStore:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)

    def _head_dir(self, name: str) -> Path:
        d = self.root / name
        # S3-FUSE volumes drop empty dirs (see TrialsLedger) — materialize with .keep
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".keep"
        if not keep.exists():
            try:
                keep.write_text("")
            except OSError:
                pass
        return d

    def champion_meta(self, name: str) -> dict | None:
        p = self.root / name / CHAMPION
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def load_champion(self, cfg, horizon: int, seed: int) -> tuple[LGBMHead, dict] | None:
        import lightgbm as lgb
        name = f"lgbm_h{horizon}"
        meta = self.champion_meta(name)
        if meta is None:
            return None
        mp = self.root / name / meta["model_file"]
        if not mp.exists():
            return None
        booster = lgb.Booster(model_str=mp.read_text())
        return LGBMHead.from_booster(cfg, horizon, seed, booster,
                                     meta["feature_names"]), meta

    def save_champion(self, head: LGBMHead, meta: dict, keep_files: int = 6) -> dict:
        """Persist `head` as the new champion. meta must carry mode/train_through/
        full_train_through/valid_rank_ic plus the G-10 stamp fields."""
        assert head.booster is not None
        name = f"lgbm_h{head.horizon}"
        d = self._head_dir(name)
        fname = f"model-{meta['train_through']}-{meta['mode']}.txt"
        best = head.booster.best_iteration
        # truncate at best_iteration so a reload scores exactly what was validated
        head.booster.save_model(str(d / fname),
                                num_iteration=best if best and best > 0 else None)
        meta = dict(meta)
        meta.update({"model_file": fname, "feature_names": list(head.feature_names),
                     "n_trees": int(head.booster.num_trees()),
                     "saved_utc": datetime.now(timezone.utc).isoformat()})
        (d / CHAMPION).write_text(json.dumps(meta, indent=2, default=str))
        self._prune(d, keep_files)
        return meta

    def save_gru(self, horizon: int, models: list, features: list[str], meta: dict,
                 keep_files: int = 6) -> dict:
        """Persist a GRU seed ensemble as gru_h{n}'s champion: the state dicts, the
        architecture, and the input features it was trained on (its own list — a
        later warm-updated LGBM head may rank its features differently)."""
        import torch
        name = f"gru_h{horizon}"
        d = self._head_dir(name)
        fname = f"model-{meta['train_through']}-{meta['mode']}.pt"
        g = models[0].gru
        arch = {"n_features": len(features), "hidden": int(g.hidden_size),
                "layers": int(g.num_layers), "dropout": float(g.dropout)}
        torch.save({"state_dicts": [m.state_dict() for m in models], "arch": arch,
                    "features": list(features)}, d / fname)
        meta = dict(meta)
        meta.update({"model_file": fname, "feature_names": list(features), "arch": arch,
                     "n_seeds": len(models),
                     "saved_utc": datetime.now(timezone.utc).isoformat()})
        (d / CHAMPION).write_text(json.dumps(meta, indent=2, default=str))
        self._prune(d, keep_files, pattern="model-*.pt")
        return meta

    def load_gru(self, horizon: int) -> tuple[list, dict] | None:
        import torch
        from src.models.gru import GRUHead
        name = f"gru_h{horizon}"
        meta = self.champion_meta(name)
        if meta is None:
            return None
        mp = self.root / name / meta["model_file"]
        if not mp.exists():
            return None
        blob = torch.load(mp, map_location="cpu", weights_only=True)
        a = blob["arch"]
        models = []
        for sd in blob["state_dicts"]:
            m = GRUHead(a["n_features"], a["hidden"], a["layers"], a["dropout"])
            m.load_state_dict(sd)
            m.eval()
            models.append(m)
        return models, meta

    def _prune(self, d: Path, keep_files: int, pattern: str = "model-*.txt") -> None:
        models = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime)
        current = None
        meta = self.champion_meta(d.name)
        if meta:
            current = meta.get("model_file")
        for p in models[:-keep_files] if keep_files > 0 else []:
            if p.name != current:
                try:
                    p.unlink()
                except OSError:
                    pass


def decide_refit(cfg, store: ModelStore, config_hash: str, sessions: pd.DatetimeIndex,
                 horizons, forced: str | None = None,
                 gru_horizons=()) -> tuple[str, str]:
    """('full'|'update', reason). 'update' only when every head has a champion whose
    config matches and whose last FULL fit is inside the refit cadence — warm updates
    stack on a full fit, they never replace one indefinitely. `gru_horizons` are the
    GRU heads the live ensemble needs: only a full refit fits those, so a missing or
    stale one forces it."""
    forced = (forced or "auto").lower()
    try:
        cc = cfg.continual
        enabled = bool(cc.enabled)
    except AttributeError:
        return "full", "no continual config block"
    if forced == "full":
        return "full", "REFIT=full forced"
    if not enabled:
        return "full", "continual.enabled is false"
    metas = [store.champion_meta(f"lgbm_h{n}") for n in horizons]
    if any(m is None for m in metas):
        return "full", "no stored champion for every head"
    gru_metas = [store.champion_meta(f"gru_h{n}") for n in gru_horizons]
    if any(m is None for m in gru_metas):
        return "full", "no stored GRU champion for every admitted GRU head"
    metas = metas + gru_metas
    if any(m.get("config_hash") != config_hash for m in metas):
        return "full", "config_hash changed since champion was trained"
    oldest_full = min(pd.Timestamp(m["full_train_through"]) for m in metas)
    # age = NEWLY LABELED sessions since the last full fit, not calendar sessions:
    # train_through always trails today by the label span (labels need 61 forward
    # sessions), so measuring against today would read >= 61 and force a full
    # refit every single day
    label_span = 1 + max(horizons)
    i_now = int(sessions.searchsorted(pd.Timestamp.today().normalize(), side="right")) - 1
    age = (i_now - label_span) - int(sessions.searchsorted(oldest_full))
    if forced != "update" and age >= int(cc.full_refit_sessions):
        return "full", f"last full fit {age} sessions old (cadence {int(cc.full_refit_sessions)})"
    return "update", f"warm update on champions (last full fit {age} sessions old)"
