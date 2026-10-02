"""Daily prediction (§2.3 production sequence, research side).

CONTINUAL LEARNING: champions persist in a ModelStore on the volume. A daily run
warm-continues each champion on the newest labeled year (LightGBM init_model),
scores champion and challenger on the SAME purged validation window, and keeps
the better model — so learning accrues day over day instead of restarting. A
from-scratch full refit still happens every `continual.full_refit_sessions`
(= val.retrain_cadence) or whenever config/features change. In update mode only
a `panel_tail_years` slice of the panel is loaded, which is what keeps the
daily run short. Every fit, adopted or not, lands in the G-09 trials ledger.

Scores the most recent sessions, blends ranks, replays the M15 event engine
over the trailing window (the same call stage3 makes: exact cash cap, MOO
netting, trailing stop) and emits the book to hold at the NEXT open — open
lots with their live stop levels, lots whose vertical falls at the open, and
today's tranche sized under the cap — plus the suggestion report.

Short sleeve (2026-09-17, blueprint port.selection [MAY]): when the config sets
`port.short_selection`, the bottom of the same ranking is sold short under its
own cap (`port.short_gross_cap`), exits by the same barrier engine (stop above
the fill, trail ratcheting down off the low since fill, profit-take below), and
the ticket carries `shorts_or_increases` / `short_holds` / `covers_or_exits`
next to the long rows. Every row now states its `side` (+1 / -1). Without the
config keys the long-only ticket is unchanged.

Output is research tooling for the system's operator — not financial advice
(blueprint CAV: "nothing here guarantees profit").
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config, git_sha
from src.data.m1 import M1
from src.pipeline.common import admitted_from_report, prepare
from src.models.lgbm import LGBMHead
from src.models.store import ModelStore, decide_refit
from src.ensemble.rank import ensemble_rank, select_long, select_short
from src.portfolio.construct import vol_target_scale, hedge_enabled
from src.backtest.costs import CostModel
from src.backtest.engines.barriers_event import (engine_opts_from_cfg, run_event_backtest,
                                                 run_long_short, live_book, sleeve_caps)
from src.regime.overlay import regime_multiplier
from src.backtest.engines.buckets import bucket_book_on
from src.live.bucket_ticket import bucket_book_live, bucket_ticket
from src.validation.splits import _purge_embargo
from src.hpo.determinism import seed_everything, artifact_stamp
from src.hpo.ledger import TrialsLedger

WARM_SESSIONS = 90            # trailing replay window for the event-engine book: must
                              # cover h_days of open lots plus the vol-target warm-up


def _rk(x) -> str:
    """Rank column for the markdown ticket: signed number, or 'nan' when unscored."""
    return f"{float(x):+.3f}" if x is not None and np.isfinite(x) else "nan"


def _fnum(x, nd: int = 2):
    """Rounded number for the ticket; None when missing or non-finite."""
    try:
        return None if x is None or not np.isfinite(x) else round(float(x), nd)
    except TypeError:
        return None


def sleeve_ticket(lb: dict, side: int, ens_last: pd.Series, last_close: pd.Series,
                  thr: pd.Series, trail_w: pd.Series | None, h_bar: int) -> dict:
    """Ticket rows for ONE sleeve of the live book (side +1 long / -1 short):
    new lots (BUY / SHORT), open lots not entering today (HOLD / HOLD SHORT)
    and lots whose vertical falls at the next open (SELL / COVER). Barrier %s
    are signed so that fill x (1 + pct/100) is the level on either side: a
    short's stop is +thr ABOVE the fill and its profit-take -thr below; the
    trail % is the distance from the running high (long) or low (short)."""
    sgn = 1 if int(side) > 0 else -1
    entries, holds_df, due_df = lb["entries"], lb["holds"], lb["due_exits"]
    held_w = holds_df.groupby("ticker")["tranche_w"].sum() if len(holds_df) \
        else pd.Series(dtype=float)
    trail_on = trail_w is not None
    new_rows, hold_rows, exit_rows = [], [], []

    def _lots(g):
        return [{"entry_date": str(r.entry_date.date()),
                 "fill_date": str(r.fill_date.date()),
                 "weight": round(float(r.tranche_w), 5),
                 "sessions_left": int(r.sessions_left),
                 "stop_kind": r.stop_kind,
                 "stop_vs_close_pct": _fnum(r.stop_vs_close_pct),
                 "pt_vs_close_pct": _fnum(r.pt_vs_close_pct)}
                for r in g.itertuples(index=False)]

    for t, wt in entries.sort_values(ascending=False).items():
        # a name already held gets a NEW lot on top: target_weight is the total
        # to hold (held + new), new_lot_weight the increment, lots the open ones
        held_here = float(held_w.get(t, 0.0))
        g_held = holds_df[holds_df["ticker"] == t].sort_values("entry_date") \
            if len(holds_df) else holds_df
        new_rows.append({
            "ticker": t, "side": sgn, "action": "BUY" if sgn > 0 else "SHORT",
            "target_weight": round(float(wt) + held_here, 5),
            "new_lot_weight": round(float(wt), 5),
            "current_weight": round(held_here, 5),
            "lots": _lots(g_held) or None,
            "ensemble_rank": _fnum(ens_last.get(t, np.nan), 4),
            "last_close": _fnum(last_close.get(t, np.nan)),
            "stop_pct": _fnum(-sgn * float(thr.get(t, np.nan)) * 100),
            "profit_take_pct": _fnum(sgn * float(thr.get(t, np.nan)) * 100),
            "trail_pct": _fnum(float(trail_w.get(t, np.nan)) * 100) if trail_on else None,
            "levels_basis": "fill",
            "max_hold_sessions": h_bar, "sessions_left": h_bar,
            "lot": ("new tranche (fills at the next open)" if sgn > 0
                    else "new short tranche (sold short at the next open)")})
    for t, g in (holds_df.groupby("ticker") if len(holds_df) else []):
        if t in entries.index:
            continue                      # carried on its new-lot row above
        g = g.sort_values("entry_date")
        # the ticket prices levels off the last close: the most binding lot's
        # stop (closest to the close on the stop side) and the nearest profit-take
        stop_b = g["stop_vs_close_pct"].max() if sgn > 0 else g["stop_vs_close_pct"].min()
        pt_b = g["pt_vs_close_pct"].min() if sgn > 0 else g["pt_vs_close_pct"].max()
        hold_rows.append({
            "ticker": t, "side": sgn, "action": "HOLD" if sgn > 0 else "HOLD SHORT",
            "target_weight": round(float(g["tranche_w"].sum()), 5),
            "current_weight": round(float(g["tranche_w"].sum()), 5),
            "ensemble_rank": _fnum(ens_last.get(t, np.nan), 4),
            "last_close": _fnum(last_close.get(t, np.nan)),
            "stop_pct": _fnum(float(stop_b)),
            "profit_take_pct": _fnum(float(pt_b)),
            "trail_pct": _fnum(float(trail_w.get(t, np.nan)) * 100) if trail_on else None,
            "levels_basis": "last_close",
            "max_hold_sessions": h_bar,
            "sessions_left": int(g["sessions_left"].min()),
            "lots": _lots(g)})
    for t, g in (due_df.groupby("ticker") if len(due_df) else []):
        when = ", ".join(str(x.date()) for x in g["entry_date"])
        exit_rows.append({
            "ticker": t, "side": sgn, "action": "SELL" if sgn > 0 else "COVER",
            "target_weight": 0.0,
            "current_weight": round(float(g["tranche_w"].sum()), 5),
            "last_close": _fnum(last_close.get(t, np.nan)),
            "reason": (f"vertical barrier: MOO sell at the next open (entered {when})"
                       if sgn > 0 else
                       f"vertical barrier: MOO cover (buy back) at the next open "
                       f"(entered {when})"),
            "lots": [{"entry_date": str(r.entry_date.date()),
                      "weight": round(float(r.tranche_w), 5)}
                     for r in g.itertuples(index=False)]})
    gross = float(entries.sum()) + float(held_w.sum())
    return {"new": new_rows, "holds": hold_rows, "exits": exit_rows, "held_w": held_w,
            "in_book": set(entries.index) | set(held_w.index), "gross": gross}


_EMPTY_SLEEVE = {"new": [], "holds": [], "exits": [], "held_w": pd.Series(dtype=float),
                 "in_book": set(), "gross": 0.0}


def _gru_member(n, lgbm_head, mode, champion, store, cfg, feats, labels_wide,
                train_dates, valid_dates, score_dates, tickers, seed, train_through,
                config_hash, stamp, ledger, persist: bool, keep_files: int):
    """gru_h{n} for the live ensemble -> (scores over score_dates, heads_info row).

    Full refit: fit on this horizon's LGBM head's top features — the M6->M7
    contract stage 2 uses — over the last val.train_years before the valid year,
    early-stopped on predict's valid year, and store it. Update: score the stored
    champion on ITS OWN feature list; GRU heads are frozen between full refits."""
    from src.models.gru import SequenceStore, make_sequences, predict_gru, train_gru
    lookback = int(cfg.gru.lookback)
    if mode == "update":
        models, meta = champion
        cols = list(meta["feature_names"])
        info = {"mode": "frozen", "adopted": True,
                "valid_rank_ic": float(meta.get("valid_rank_ic", float("nan"))),
                "full_train_through": meta.get("full_train_through"), "features": cols}
    else:
        cols = lgbm_head.top_importance(int(cfg.gru.n_features))
        seqs = SequenceStore(feats[cols], cols, lookback=lookback)
        tr = train_dates[-252 * int(cfg.val.train_years):]
        models, ginfo = train_gru(make_sequences(seqs, tr), make_sequences(seqs, valid_dates),
                                  labels_wide, len(cols), cfg, seed)
        del seqs
        ric = float(np.mean([s["best_valid_ric"] for s in ginfo["seeds"]]))
        ledger.append(f"gru_h{n}", {"mode": "full_refit", "train_through": train_through},
                      config_hash, "valid_rank_ic", ric, note="predict_full_refit")
        if persist:
            store.save_gru(n, models, cols, {
                "mode": "full_refit", "parent": None, "train_through": train_through,
                "full_train_through": train_through, "valid_rank_ic": ric,
                "config_hash": config_hash, "stamp": stamp}, keep_files=keep_files)
        epochs = [int(s["epochs"]) for s in ginfo["seeds"]]
        info = {"mode": "full_refit", "adopted": True, "valid_rank_ic": ric,
                "epochs": epochs, "features": cols}
        print(f"gru_h{n}: valid RIC {ric:.4f} ({len(models)} seeds, epochs {epochs})",
              flush=True)
    seqs = SequenceStore(feats[cols], cols, lookback=lookback)
    gp = predict_gru(models, make_sequences(seqs, score_dates), tickers)
    return gp.reindex(index=score_dates, columns=tickers), info


def run_predict(m1_dir: str, eod_dir: str, out_dir: str, config_path: str | None = None,
                max_tickers: int | None = None, market_dir: str | None = None,
                positions_csv: str | None = None, model_dir: str | None = None,
                refit: str | None = None) -> dict:
    cfg, config_hash = load_config(config_path)
    seed = int(cfg.seed["global"])
    seed_everything(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    try:
        cc = cfg.continual
    except AttributeError:
        cc = None
    store = ModelStore(model_dir or os.environ.get("MODEL_DIR")
                       or (cc.model_dir if cc else "models"))
    sessions_all = M1(m1_dir).sessions()
    # M10-03 (2026-09-27): rank with the members stage 2 admitted, read back from
    # its report, so the live book is built from the same members as the research
    # book the gates judged — GRU heads included (a full refit fits them, a daily
    # run only scores them). No report -> the pre-2026-09-27 book: every LGBM head.
    scores_dir = os.environ.get("SCORES_DIR")
    admitted = (admitted_from_report(Path(scores_dir) / "stage2_report.json")
                if scores_dir else None)
    if admitted is None:
        print(f"!! no stage2_report.json under SCORES_DIR={scores_dir!r} — M10-03 "
              f"unknown: every LGBM head, no GRU", flush=True)
    gru_horizons = [n for n in cfg.labels.horizons
                    if admitted is not None and f"gru_h{n}" in admitted]
    mode, why = decide_refit(cfg, store, config_hash, sessions_all, cfg.labels.horizons,
                             forced=refit or os.environ.get("REFIT"),
                             gru_horizons=gru_horizons)
    since = None
    if mode == "update":
        i_now = int(sessions_all.searchsorted(pd.Timestamp.today().normalize(),
                                              side="right"))
        tail = int(252 * float(cc.panel_tail_years))
        since = sessions_all[max(0, i_now - tail)]
    print(f"refit mode: {mode} — {why}"
          + (f" | panel tail since {since.date()}" if since is not None else ""),
          flush=True)

    d = prepare(cfg, m1_dir, eod_dir, market_dir, max_tickers, since=since)

    champs, gru_champs = {}, {}
    if mode == "update":
        for n in cfg.labels.horizons:
            champs[n] = store.load_champion(cfg, n, seed)
        for n in gru_horizons:
            gru_champs[n] = store.load_gru(n)
        feat_cols = list(d["feats"].columns)
        bad = [n for n, c in champs.items()
               if c is None or c[1]["feature_names"] != feat_cols]
        bad += [f"gru_h{n}" for n, g in gru_champs.items()
                if g is None or not set(g[1]["feature_names"]) <= set(feat_cols)]
        if bad:
            # feature set drifted since the champions were trained — a warm continue
            # would silently mis-map columns, so fall back to a full refit on full data
            print(f"champion/feature mismatch on heads {bad} — falling back to full "
                  f"refit", flush=True)
            mode, why, champs, gru_champs = "full", "feature set changed after prep", {}, {}
            if since is not None:
                del d
                import gc
                gc.collect()
                since = None
                d = prepare(cfg, m1_dir, eod_dir, market_dir, max_tickers)

    if d["health"]["blocking"]:
        raise RuntimeError(f"Q-004 BLOCKING failure: {d['health']}")
    panel, mask, feats, ys = d["panel"], d["mask"], d["feats"], d["ys"]
    sigma32, spy, idx_blk = d["sigma32"], d["spy"], d["idx_blk"]
    dates = panel.dates
    label_span = 1 + max(cfg.labels.horizons)
    embargo = int(cfg.val.embargo_days)

    # ---- final training fold: labeled history, last year = early-stop valid ----
    # full mode trains on everything before the valid year; update mode warm-continues
    # the champion on only the newest `update_train_sessions` of that zone (purged the
    # same way), which with the tail panel is what makes the daily run cheap
    n_labeled = len(dates) - label_span
    valid_iv = [(n_labeled - 252, n_labeled - 1)]
    zone_end = n_labeled - 252
    zone_start = max(0, zone_end - int(cc.update_train_sessions)) if mode == "update" \
        else 0
    tr_idx = _purge_embargo(dates, np.arange(zone_start, zone_end), valid_iv,
                            label_span, 0)
    train_dates, valid_dates = dates[tr_idx], dates[n_labeled - 252:n_labeled]
    f_dates = feats.index.get_level_values("date")
    Xtr = feats[f_dates.isin(train_dates)]
    Xva = feats[f_dates.isin(valid_dates)]
    n_score = max(WARM_SESSIONS, 2 * int(cfg.barrier.h_days) + 21)
    if bucket_book_on(cfg):
        # the bucket signal ranks today's score in the name's own trailing year
        n_score = max(n_score, int(cfg.port.get("bucket_window", 252)) + 5)
    score_dates = dates[-n_score:]
    Xsc = feats[f_dates.isin(score_dates)]

    ledger = TrialsLedger()
    train_through = str(pd.Timestamp(dates[n_labeled - 1]).date())
    scores = {}
    heads_info = {}
    for n in cfg.labels.horizons:
        ytr, yva = ys[n].reindex(Xtr.index), ys[n].reindex(Xva.index)
        ok_tr, ok_va = ytr.notna(), yva.notna()
        Xva_ok, yva_ok = Xva[ok_va.values], yva[ok_va]
        stamp = artifact_stamp(config_hash, d["m1"].data_snapshot_id(), git_sha(), seed)
        if mode == "update":
            champ_head, champ_meta = champs[n]
            head = LGBMHead(cfg, n, seed).fit(
                Xtr[ok_tr.values], ytr[ok_tr], Xva_ok, yva_ok,
                init_booster=champ_head.booster,
                num_boost_round=int(cc.update_boost_rounds),
                learning_rate=float(cc.update_learning_rate))
            ric_new = head.valid_rank_ic(Xva_ok, yva_ok)
            ric_champ = champ_head.valid_rank_ic(Xva_ok, yva_ok)
            adopted = bool(np.isfinite(ric_new)
                           and (not np.isfinite(ric_champ) or ric_new > ric_champ))
            ledger.append(f"lgbm_h{n}", {"mode": "warm_update",
                                         "parent": champ_meta["model_file"],
                                         "train_through": train_through},
                          config_hash, "valid_rank_ic", ric_new,
                          note="predict_warm_update"
                               + ("_adopted" if adopted else "_rejected"))
            if adopted:
                store.save_champion(head, {
                    "mode": "warm_update", "parent": champ_meta["model_file"],
                    "train_through": train_through,
                    "full_train_through": champ_meta["full_train_through"],
                    "valid_rank_ic": ric_new, "config_hash": config_hash,
                    "stamp": stamp}, keep_files=int(cc.keep_model_files))
            else:
                head = champ_head
            heads_info[f"lgbm_h{n}"] = {
                "mode": "warm_update", "adopted": adopted,
                "valid_rank_ic": ric_new if adopted else ric_champ,
                "challenger_rank_ic": ric_new, "champion_rank_ic": ric_champ,
                "n_trees": int(head.booster.num_trees()),
                "top_features": head.top_importance(10)}
            print(f"h{n}: champion {ric_champ:.4f} vs challenger {ric_new:.4f} -> "
                  f"{'ADOPTED' if adopted else 'kept champion'}", flush=True)
        else:
            head = LGBMHead(cfg, n, seed).fit(Xtr[ok_tr.values], ytr[ok_tr],
                                              Xva_ok, yva_ok)
            ric = head.valid_rank_ic(Xva_ok, yva_ok)
            ledger.append(f"lgbm_h{n}", {"mode": "full_refit",
                                         "train_through": train_through},
                          config_hash, "valid_rank_ic", ric, note="predict_full_refit")
            if cc is not None and bool(cc.enabled):
                store.save_champion(head, {
                    "mode": "full_refit", "parent": None,
                    "train_through": train_through,
                    "full_train_through": train_through,
                    "valid_rank_ic": ric, "config_hash": config_hash,
                    "stamp": stamp}, keep_files=int(cc.keep_model_files))
            heads_info[f"lgbm_h{n}"] = {
                "mode": "full_refit", "adopted": True,
                "valid_rank_ic": ric,
                "best_iter": int(head.booster.best_iteration),
                "top_features": head.top_importance(10)}
            print(f"h{n}: valid RIC {ric:.4f}", flush=True)
        p = head.predict(Xsc)
        scores[f"lgbm_h{n}"] = p.unstack("ticker").reindex(index=score_dates,
                                                           columns=panel.tickers)
        if n in gru_horizons:
            scores[f"gru_h{n}"], heads_info[f"gru_h{n}"] = _gru_member(
                n, head, mode, gru_champs.get(n), store, cfg, feats, d["labels"][n],
                train_dates, valid_dates, score_dates, panel.tickers, seed,
                train_through, config_hash, stamp, ledger,
                persist=cc is not None and bool(cc.enabled),
                keep_files=int(cc.keep_model_files) if cc is not None else 6)

    # ---- live-tradability screen [IMPL]: the centered-window tape hygiene of
    # build_panel cannot protect the LAST bars (no future context), so the
    # prediction-time selection additionally requires: a live Sharadar entity
    # (isdelisted == N), a fresh tape (traded within 2 sessions), a last close
    # inside [0.25x, 4x] of its trailing 21d median, and a sane sigma32 (>= 0.5%
    # daily — stale tapes fake near-zero vol and grab outsized inverse-vol
    # weights). Applies only to the live path, never to backtests. ----
    ents = d["m1"].entities()
    live_ok = set(ents.loc[ents.get("isdelisted", "N").astype(str) != "Y",
                           "ticker"].astype(str))
    live_ok |= {t.replace(".", "-") for t in live_ok}
    t_last_all = panel.dates[-1]
    trail_med = panel.raw_close.rolling(21, min_periods=10).median().iloc[-1]
    lvl_ratio = panel.raw_close.iloc[-1] / trail_med
    fresh = panel.raw_close.iloc[-3:].notna().any()
    sane_sigma = sigma32.iloc[-1] >= 0.005
    tradable = (pd.Series([str(t) in live_ok for t in panel.tickers],
                          index=panel.tickers)
                & lvl_ratio.between(0.25, 4.0) & fresh & sane_sigma)
    n_dropped = int((~tradable).sum())
    print(f"live screen: {n_dropped} names not currently tradable-quality "
          f"(delisted/stale/level-shifted/zero-vol)", flush=True)
    mask = mask & pd.DataFrame(
        np.broadcast_to(tradable.values, (len(mask), len(tradable))),
        index=mask.index, columns=mask.columns)

    # ---- ensemble -> top-N selection -> the EVENT-ENGINE book at the next open ----
    # The ticket used to come from the Stage-1 fixed 15-tranche rotation
    # (construct_targets): a 15-session smear of top-N membership that the
    # backtest never traded. It now replays the ONE event engine (G-15) over
    # the trailing window with the adopted engine options (exact cash cap,
    # MOO netting, trailing stop) — the same call stage3 makes — and reads the
    # book to hold at open t+1 straight off it: open lots, lots whose vertical
    # falls at the next open, and today's tranche sized under the cap.
    m = mask.loc[score_dates]
    live = {k: v for k, v in scores.items() if admitted is None or k in admitted} or scores
    print(f"live ensemble members: {sorted(live)}", flush=True)
    ens = ensemble_rank(live, m)
    if bucket_book_on(cfg):
        cm_b = CostModel(per_trade_bps=float(cfg.cost.per_trade_bps),
                         borrow_gc_bps_yr=float(cfg.cost.borrow_gc_bps_yr),
                         borrow_table=d.get("borrow"))
        header = {
            "stamp": artifact_stamp(config_hash, d["m1"].data_snapshot_id(), git_sha(), seed),
            "training": {
                "mode": mode, "reason": why, "train_through": train_through,
                "panel_tail_since": str(since.date()) if since is not None else None,
                "adopted": {k: bool(v.get("adopted", True)) for k, v in heads_info.items()},
                "ensemble_members": sorted(live),
                "full_refit_cadence_sessions": int(cc.full_refit_sessions) if cc else None},
            "heads": heads_info}
        return _bucket_predict(out, ens, mask, panel, sigma32, cm_b, cfg, d["spy"], header)
    sel = select_long(ens, m, cfg)
    print(f"selection: {cfg.port.get('selection', 'top_decile_long')} "
          f"(N={cfg.port.get('top_n', 20)}) -> event-engine live book", flush=True)
    # The live event-engine book has no index leg at all. Say so either way, and
    # say it LOUDLY when the config asks for one: silently trading unhedged while
    # the config (and the stage reports) assume a hedge is the failure this
    # setting is now wired to prevent.
    if hedge_enabled(cfg):
        print(f"!! port.hedge={cfg.port.get('hedge')!r} but the live book has NO hedge "
              f"leg — the event engine trades single names only. Set port.hedge: none "
              f"to make the config match what is traded.", flush=True)
    else:
        print("hedge: none (no SPY index leg)", flush=True)
    hedge_w = 0.0
    cm = CostModel(per_trade_bps=float(cfg.cost.per_trade_bps),
                   borrow_gc_bps_yr=float(cfg.cost.borrow_gc_bps_yr),
                   borrow_table=d.get("borrow"))
    # ---- short sleeve (2026-09-17, blueprint [MAY]): the bottom of the SAME
    # ranking sold short under its own cap, exiting through the same barrier
    # engine. §I step 4: a name whose borrow fee is above the threshold today is
    # skipped and logged. All-off (long-only ticket) without the config keys.
    long_cap, short_cap = sleeve_caps(cfg)
    max_borrow = cfg.port.get("short_max_borrow_bps_yr")
    borrowable = cm.borrowable(score_dates, panel.tickers, max_borrow)
    sel_short = select_short(ens, m, cfg, borrowable)
    short_on = short_cap > 0 and bool(sel_short.to_numpy().any())
    htb_skipped: list[str] = []
    if short_on:
        raw_last = select_short(ens, m, cfg).iloc[-1]
        htb_skipped = sorted(str(t) for t in raw_last.index[raw_last & ~sel_short.iloc[-1]])
        print(f"short sleeve: {cfg.port.get('short_selection')} "
              f"(N={cfg.port.get('short_n')}), caps long {long_cap} / short {short_cap}"
              + (f"; hard-to-borrow skipped today: {htb_skipped}" if htb_skipped else ""),
              flush=True)
    else:
        print("short sleeve: off (long-only book)", flush=True)
    # M13 regime overlay + M14 vol targeting scale the ENTERING tranche, exactly
    # as stage3 does: a pre-run over the window feeds the causal vol-target scale
    gm = regime_multiplier(idx_blk, float(cfg.regime.vol_threshold_ann),
                           float(cfg.regime.gross_multiplier_risk_off)) \
        .reindex(score_dates).fillna(1.0)
    eng_kw = engine_opts_from_cfg(cfg)
    eng_kw["gross_cap"] = long_cap
    pre = run_long_short(sel, sel_short, panel, sigma32, cm, cfg, short_cap=short_cap,
                         day_budget_mult=gm, **eng_kw)
    vt = vol_target_scale(pre["daily_net"].loc[score_dates[0]:],
                          float(cfg.port.vol_target_ann),
                          float(cfg.port.vol_target_scale_cap))
    budget = (gm * vt.reindex(score_dates).fillna(1.0)).clip(lower=0.0)
    lb = live_book(sel, panel, sigma32, cm, cfg, day_budget_mult=budget, side=1,
                   gross_cap=long_cap)
    lb_s = (live_book(sel_short, panel, sigma32, cm, cfg, day_budget_mult=budget,
                      side=-1, gross_cap=short_cap) if short_on else None)
    t_last = score_dates[-1]
    assert lb["as_of"] == t_last
    entries, holds_df, due_df = lb["entries"], lb["holds"], lb["due_exits"]
    print(f"live book @ {t_last.date()}: {len(entries)} entering "
          f"(gross {float(entries.sum()):.3f}, budget {lb['budget']:.2f}, cap scale "
          f"{lb['cap_scale']:.2f}), {len(holds_df)} open lots "
          f"(gross {float(holds_df['tranche_w'].sum()) if len(holds_df) else 0.0:.3f}), "
          f"{len(due_df)} lots due at the open", flush=True)
    if lb_s is not None:
        assert lb_s["as_of"] == t_last
        print(f"short book @ {t_last.date()}: {len(lb_s['entries'])} entering "
              f"(gross {float(lb_s['entries'].sum()):.3f}, cap scale "
              f"{lb_s['cap_scale']:.2f}), {len(lb_s['holds'])} open short lots "
              f"(gross {float(lb_s['holds']['tranche_w'].sum()) if len(lb_s['holds']) else 0.0:.3f}), "
              f"{len(lb_s['due_exits'])} lots to cover at the open", flush=True)

    # ---- barrier levels for NEW entries (M5.2 parameters, % vs the fill) ----
    m_bar, h_bar = float(cfg.barrier.m), int(cfg.barrier.h_days)
    thr = m_bar * sigma32.loc[t_last] * np.sqrt(h_bar)
    cap = cfg.barrier.get("thr_cap_pct")
    if cap is not None:
        thr = thr.clip(upper=float(cap))
    trail_m = cfg.barrier.get("trail_m")
    trail_on = trail_m is not None and float(trail_m) > 0
    trail_w = (float(trail_m) * sigma32.loc[t_last] * np.sqrt(h_bar)) if trail_on else None
    last_close = panel.raw_close.loc[t_last]
    ens_last = ens.loc[t_last]

    L = sleeve_ticket(lb, 1, ens_last, last_close, thr, trail_w, h_bar)
    S = sleeve_ticket(lb_s, -1, ens_last, last_close, thr, trail_w, h_bar) \
        if lb_s is not None else dict(_EMPTY_SLEEVE)
    buys, holds, sells = L["new"], L["holds"], L["exits"]
    shorts, short_holds, covers = S["new"], S["holds"], S["exits"]
    held_w, held_w_s = L["held_w"], S["held_w"]

    # ---- diff vs the operator's own positions file (names outside the book);
    # weights are signed: a negative weight is a short position ----
    current = pd.Series(dtype=float)
    if positions_csv and Path(positions_csv).exists():
        pos_df = pd.read_csv(positions_csv)
        current = pos_df.set_index("ticker")["weight"] if "weight" in pos_df else \
            pd.Series(dtype=float)
    for t, cur in current.items():
        if abs(cur) <= 1e-6:
            continue
        if cur > 0 and t not in L["in_book"] and not any(x["ticker"] == t for x in sells):
            sells.append({"ticker": t, "side": 1, "action": "SELL", "target_weight": 0.0,
                          "current_weight": round(float(cur), 5),
                          "last_close": _fnum(last_close.get(t, np.nan)),
                          "reason": "held but not in the event-engine book"})
        elif cur < 0 and t not in S["in_book"] and not any(x["ticker"] == t for x in covers):
            covers.append({"ticker": t, "side": -1, "action": "COVER",
                           "target_weight": 0.0,
                           "current_weight": round(float(cur), 5),
                           "last_close": _fnum(last_close.get(t, np.nan)),
                           "reason": "held short but not in the short sleeve's book"})
    gross_book, gross_short = L["gross"], S["gross"]
    # rows are rounded to 5 dp: the ticket must still add up to each sleeve's book
    assert abs(sum(r["target_weight"] for r in buys + holds) - gross_book) < 1e-3, \
        (sum(r["target_weight"] for r in buys + holds), gross_book)
    assert abs(sum(r["target_weight"] for r in shorts + short_holds) - gross_short) < 1e-3, \
        (sum(r["target_weight"] for r in shorts + short_holds), gross_short)
    book_names = sorted(L["in_book"])
    short_names = sorted(S["in_book"])

    suggestions = {
        "as_of_close": str(t_last.date()),
        "execute_at": "next session MOO (G-02: signals from close t earn from open t+1)",
        "stamp": artifact_stamp(config_hash, d["m1"].data_snapshot_id(), git_sha(), seed),
        "training": {
            "mode": mode, "reason": why,
            "train_through": train_through,
            "panel_tail_since": str(since.date()) if since is not None else None,
            "adopted": {k: bool(v.get("adopted", True)) for k, v in heads_info.items()},
            "ensemble_members": sorted(live),
            "full_refit_cadence_sessions": int(cc.full_refit_sessions) if cc else None,
            "note": "warm_update continues the stored champion on the newest labeled "
                    "year; champion vs challenger judged on the same purged valid year",
        },
        "heads": heads_info,
        "portfolio": {"n_names": int(len(book_names)), "gross_long": round(gross_book, 5),
                      "entering_gross": round(float(entries.sum()), 5),
                      "held_gross": round(float(held_w.sum()), 5),
                      "due_exit_gross": round(float(due_df["tranche_w"].sum())
                                              if len(due_df) else 0.0, 5),
                      "budget_mult": round(float(lb["budget"]), 4),
                      "cap_scale": round(float(lb["cap_scale"]), 4),
                      "spy_hedge_weight": round(hedge_w, 4),
                      # short sleeve (positive numbers = short exposure as a
                      # fraction of NAV; net_exposure = long - short)
                      "n_short_names": int(len(short_names)),
                      "gross_short": round(gross_short, 5),
                      "short_entering_gross": round(float(lb_s["entries"].sum()), 5)
                      if lb_s is not None else 0.0,
                      "short_held_gross": round(float(held_w_s.sum()), 5),
                      "short_due_exit_gross": round(float(lb_s["due_exits"]["tranche_w"].sum())
                                                    if lb_s is not None and len(lb_s["due_exits"])
                                                    else 0.0, 5),
                      "short_cap_scale": round(float(lb_s["cap_scale"]), 4)
                      if lb_s is not None else None,
                      "gross_total": round(gross_book + gross_short, 5),
                      "net_exposure": round(gross_book - gross_short, 5)},
        "book_engine": {"engine": "M15 event engine replay (run_event_backtest + live_book)",
                        "window_sessions": int(len(score_dates)),
                        "options": {k: (None if v is None else v)
                                    for k, v in eng_kw.items()},
                        "short_sleeve": {
                            "enabled": short_on,
                            "selection": str(cfg.port.get("short_selection", "none")),
                            "short_n": cfg.port.get("short_n"),
                            "long_cap": long_cap, "short_cap": short_cap,
                            "max_borrow_bps_yr": max_borrow,
                            "hard_to_borrow_skipped_today": htb_skipped,
                            "note": "a short is a sale of borrowed shares: SELL MOO to "
                                    "open, BUY to cover; stop ABOVE the fill (the trail "
                                    "ratchets it down off the low since fill), "
                                    "profit-take below; the borrow fee accrues daily; "
                                    "margin account required (G-14)"},
                        "sizing": "weights are fractions of NAV at entry: "
                                  "inverse-vol within the entering tranche / tranches x "
                                  "regime x vol-target budget, scaled to each sleeve's "
                                  "cap (long + short live gross <= the cash cap)",
                        "note": "replaces the Stage-1 15-tranche rotation the ticket "
                                "used until 2026-09-08 — the book shown is the one "
                                "the backtest trades"},
        "buys_or_increases": buys,
        "holds": holds,
        "sells_or_exits": sells,
        "shorts_or_increases": shorts,
        "short_holds": short_holds,
        "covers_or_exits": covers,
        "exit_rules": {"engine": "M5.2 triple barrier", "m": m_bar, "h_sessions": h_bar,
                       "trail_m": float(trail_m) if trail_on else None,
                       "note": "stop/profit-take are % vs ACTUAL fill at next open; "
                               "vertical exit = MOO at t+h+1"
                               + ("; trailing stop: after each close raise the GTC "
                                  "stop to high_since_fill x (1 - trail_pct), never "
                                  "below the fixed stop" if trail_on else "")
                               + ("; shorts mirror this: stop above the fill, "
                                  "profit-take below, vertical = BUY MOO cover"
                                  + (", trail = lower the GTC buy-stop to "
                                     "low_since_fill x (1 + trail_pct), never above "
                                     "the fixed stop" if trail_on else "")
                                  if short_on else "")},
        "disclaimer": "Research output of an experimental system; NOT financial advice. "
                      "All performance claims require the G-11 gate evaluation first.",
    }
    (out / "suggestions.json").write_text(json.dumps(suggestions, indent=2, default=str))

    def _tp(row, sgn):
        tp = row.get("trail_pct")
        return f"{'-' if sgn > 0 else '+'}{tp}%" if tp is not None else "off"

    def _lvl(v, plus=False):
        return "" if v is None else (f"+{v}%" if plus and v >= 0 else f"{v}%")

    md = [f"# Event-engine book for next open (signals @ close {t_last.date()})", "",
          f"- Long: {len(book_names)} names, gross {gross_book:.2f} "
          f"(entering {float(entries.sum()):.2f} + held {float(held_w.sum()):.2f}), "
          f"budget x{lb['budget']:.2f}, cap scale x{lb['cap_scale']:.2f}"]
    if short_on:
        md.append(f"- Short: {len(short_names)} names, gross {gross_short:.2f} "
                  f"(entering {float(lb_s['entries'].sum()):.2f} + held "
                  f"{float(held_w_s.sum()):.2f}), cap scale x{lb_s['cap_scale']:.2f}; "
                  f"net exposure {gross_book - gross_short:+.2f}"
                  + (f"; hard-to-borrow skipped: {', '.join(htb_skipped)}"
                     if htb_skipped else ""))
    md += [f"- Heads valid RankIC: " + ", ".join(
               f"{k} {v['valid_rank_ic']:.3f}" for k, v in heads_info.items()),
           f"- Training: {mode} ({why})" + ("" if mode != "warm_update" and mode != "update"
               else " — " + ", ".join(
                   f"{k} {'adopted' if v.get('adopted') else 'kept champion'}"
                   for k, v in heads_info.items())), "",
           "| ticker | action | weight | rank | last close | stop % | PT % | trail % | "
           "sessions left | levels vs |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for sgn, new_rows, hold_rows, exit_rows in ((1, buys, holds, sells),
                                                (-1, shorts, short_holds, covers)):
        verb_new = "BUY" if sgn > 0 else "SHORT"
        verb_hold = "HOLD" if sgn > 0 else "HOLD SHORT"
        verb_exit = "SELL at open" if sgn > 0 else "COVER at open"
        for row in new_rows[:40]:
            held_txt = (" + held " + format(row['current_weight'], '.3%')
                        if row['current_weight'] else "")
            md.append(f"| {row['ticker']} | {verb_new} (new lot "
                      f"{row['new_lot_weight']:.3%}{held_txt}) | "
                      f"{row['target_weight']:.3%} | {_rk(row['ensemble_rank'])} | "
                      f"{row['last_close']} | {_lvl(row['stop_pct'], plus=True)} | "
                      f"{_lvl(row['profit_take_pct'], plus=True)} | {_tp(row, sgn)} | "
                      f"{row['sessions_left']} | fill |")
        for row in hold_rows[:60]:
            md.append(f"| {row['ticker']} | {verb_hold} ({len(row['lots'])} lot"
                      f"{'s' if len(row['lots']) != 1 else ''}) | {row['target_weight']:.3%} | "
                      f"{_rk(row['ensemble_rank'])} | {row['last_close']} | "
                      f"{_lvl(row['stop_pct'], plus=True)} | "
                      f"{_lvl(row['profit_take_pct'], plus=True)} | {_tp(row, sgn)} | "
                      f"{row['sessions_left']} | last close |")
        for row in exit_rows[:40]:
            md.append(f"| {row['ticker']} | {verb_exit} | 0 |  | {row['last_close']} |  |  |  "
                      f"| 0 | {row['reason'][:40]} |")
    md += ["", "_Vertical exit: MOO " + str(h_bar) + " sessions after entry."
           + (" Trailing stop: each night raise a long's stop to the high since fill "
              "minus trail %, never below the fixed stop" if trail_on else "")
           + ((" (a short's stop is lowered to the low since fill plus trail %, never "
               "above the fixed stop)." if trail_on else " ")
              + " SHORT = sell borrowed shares at the open; COVER = buy them back; a "
                "short's stop sits above the fill and its profit-take below."
              if short_on else ("." if trail_on else ""))
           + " HOLD rows price the most binding lot's levels off the last close. "
             "Research tooling, not financial advice._"]
    (out / "suggestions.md").write_text("\n".join(md))
    print(f"suggestions written: {len(buys)} buys/adds, {len(sells)} exits, "
          f"{len(holds)} holds"
          + (f"; {len(shorts)} shorts/adds, {len(covers)} covers, "
             f"{len(short_holds)} short holds" if short_on else ""), flush=True)
    return suggestions


def _bucket_predict(out: Path, ens: pd.DataFrame, mask: pd.DataFrame, panel,
                    sigma32: pd.DataFrame, cm, cfg, spy: pd.DataFrame,
                    header: dict) -> dict:
    """port.book: buckets — the per-name bucket book at the next open
    (src/live/bucket_ticket.py). Same suggestions schema as the shared book
    (buys/holds/sells), plus `parking` (the SPY leg) and `buckets` (pots)."""
    t_last = panel.dates[-1]
    lb = bucket_book_live(ens, mask, panel, sigma32, cm, cfg, spy, out)
    res = lb["res"]
    T = bucket_ticket(res, panel, sigma32, cfg, ens.loc[t_last], spy)
    p = cfg.port
    h_bar = int(cfg.barrier.h_days)
    trail_m = cfg.barrier.get("trail_m")
    trail_on = trail_m is not None and float(trail_m) > 0
    gross = sum(r["target_weight"] for r in T["buys"] + T["holds"])
    park_w = T["parking"]["target_weight"] if T["parking"] else 0.0
    cyc = res["cycle"]
    status = pd.Series([x["status"] for x in T["pots"]]).value_counts().to_dict()
    suggestions = {
        "as_of_close": str(t_last.date()),
        "execute_at": "next session MOO (G-02: signals from close t earn from open t+1)",
        **header,
        "portfolio": {"book": "buckets", "n_names": len(T["buys"]) + len(T["holds"]),
                      "gross_long": round(gross, 5),
                      "entering_gross": round(sum(r["target_weight"] for r in T["buys"]), 5),
                      "held_gross": round(sum(r["target_weight"] for r in T["holds"]), 5),
                      "due_exit_gross": round(sum(r["current_weight"] for r in T["sells"]), 5),
                      "parked_gross": round(park_w, 5),
                      "spy_hedge_weight": 0.0, "n_short_names": 0, "gross_short": 0.0,
                      "gross_total": round(gross, 5), "net_exposure": round(gross, 5),
                      "pots": len(T["pots"]), "pot_status": status,
                      "book_units": T["nav_units"]},
        "book_engine": {
            "engine": "per-name buckets (src/backtest/engines/buckets.py)",
            "bucket_start": str(lb["start"].date()),
            "unit": float(p.get("bucket_unit", 10_000)),
            "signal": f"ensemble score in the top {1 - float(p.get('bucket_q', 0.9)):.0%} "
                      f"of the name's own trailing {int(p.get('bucket_window', 252))} sessions",
            "cycle": {**cyc, "fallback_pct": p.get("bucket_fallback_pct"),
                      "fallback_last": p.get("bucket_fallback_last"),
                      "untraded_this_cycle": sorted(x["ticker"] for x in T["pots"]
                                                    if not x["traded_this_cycle"])},
            "park": str(p.get("bucket_park", "none")),
            "frozen_decision_rows": int(len(lb["rows"])),
            "sizing": "each pot is all-in its stock (whole shares) or flat; weights "
                      "are pot / book; a pot keeps its own P&L"},
        "buys_or_increases": T["buys"],
        "holds": T["holds"],
        "sells_or_exits": T["sells"],
        "shorts_or_increases": [], "short_holds": [], "covers_or_exits": [],
        "parking": T["parking"],
        "buckets": T["pots"],
        "bucket_performance": T["performance"],
        "exit_rules": {"engine": "M5.2 triple barrier", "m": float(cfg.barrier.m),
                       "h_sessions": h_bar,
                       "trail_m": float(trail_m) if trail_on else None,
                       "note": "stop/profit-take are % vs ACTUAL fill at next open; "
                               "vertical exit = MOO at t+h+1"
                               + ("; trailing stop: after each close raise the GTC "
                                  "stop to high_since_fill x (1 - trail_pct), never "
                                  "below the fixed stop" if trail_on else "")},
        "disclaimer": "Research output of an experimental system; NOT financial advice. "
                      "All performance claims require the G-11 gate evaluation first.",
    }
    (out / "suggestions.json").write_text(json.dumps(suggestions, indent=2, default=str))
    md = [f"# Bucket book for next open (signals @ close {t_last.date()})", "",
          f"- Pots: {len(T['pots'])} since {lb['start'].date()}; status {status}",
          f"- Cycle {cyc['block'] + 1}, session {cyc['session_in_cycle']}/"
          f"{cyc['cycle_sessions']}; not yet traded this cycle: "
          f"{len(suggestions['book_engine']['cycle']['untraded_this_cycle'])}",
          f"- In stocks {gross:.1%}" + (f", parked in SPY {park_w:.1%} "
                                       f"(change {T['parking']['delta_weight']:+.1%})"
                                       if T["parking"] else ""), "",
          "| ticker | action | weight | pot | stop % | PT % | sessions left |",
          "|---|---|---|---|---|---|---|"]
    for r in T["buys"]:
        md.append(f"| {r['ticker']} | BUY ({r['entry_kind']}) | {r['target_weight']:.3%} | "
                  f"{r['pot_value']:,.0f} | {r['stop_pct']} | {r['profit_take_pct']} | {h_bar} |")
    for r in T["holds"]:
        md.append(f"| {r['ticker']} | HOLD | {r['target_weight']:.3%} | {r['pot_value']:,.0f} | "
                  f"{r['stop_pct']} | {r['profit_take_pct']} | {r['sessions_left']} |")
    for r in T["sells"]:
        md.append(f"| {r['ticker']} | SELL at open | 0 |  |  |  | 0 |")
    (out / "suggestions.md").write_text("\n".join(md))
    print(f"bucket book @ {t_last.date()}: {len(T['buys'])} buys, {len(T['holds'])} holds, "
          f"{len(T['sells'])} exits; pots {status}; parked {park_w:.1%}", flush=True)
    return suggestions


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--m1", default=os.environ.get("M1_DIR", "/workspace/m1"))
    ap.add_argument("--eod", default=os.environ.get("EOD_DIR", "/workspace/data"))
    ap.add_argument("--out", default=os.environ.get("OUT_DIR", "artifacts/reports/predict"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--max-tickers", type=int, default=None)
    ap.add_argument("--market", default=os.environ.get("MARKET_DIR") or None)
    ap.add_argument("--positions", default=None)
    ap.add_argument("--model-dir", default=os.environ.get("MODEL_DIR") or None,
                    help="champion store for continual learning (volume-persistent)")
    ap.add_argument("--refit", default=os.environ.get("REFIT") or None,
                    choices=[None, "auto", "full", "update"],
                    help="auto: warm-update champions daily, full refit on cadence")
    args = ap.parse_args()
    run_predict(args.m1, args.eod, args.out, args.config, args.max_tickers,
                market_dir=args.market, positions_csv=args.positions,
                model_dir=args.model_dir, refit=args.refit)
