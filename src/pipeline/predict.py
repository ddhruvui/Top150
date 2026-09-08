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
from src.pipeline.common import prepare
from src.models.lgbm import LGBMHead
from src.models.store import ModelStore, decide_refit
from src.ensemble.rank import ensemble_rank, select_long
from src.portfolio.construct import vol_target_scale
from src.backtest.costs import CostModel
from src.backtest.engines.barriers_event import (engine_opts_from_cfg, run_event_backtest,
                                                 live_book)
from src.regime.overlay import regime_multiplier
from src.validation.splits import _purge_embargo
from src.hpo.determinism import seed_everything, artifact_stamp
from src.hpo.ledger import TrialsLedger

WARM_SESSIONS = 90            # trailing replay window for the event-engine book: must
                              # cover h_days of open lots plus the vol-target warm-up


def _rk(x) -> str:
    """Rank column for the markdown ticket: signed number, or 'nan' when unscored."""
    return f"{float(x):+.3f}" if x is not None and np.isfinite(x) else "nan"


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
    mode, why = decide_refit(cfg, store, config_hash, sessions_all, cfg.labels.horizons,
                             forced=refit or os.environ.get("REFIT"))
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

    champs = {}
    if mode == "update":
        for n in cfg.labels.horizons:
            champs[n] = store.load_champion(cfg, n, seed)
        feat_cols = list(d["feats"].columns)
        bad = [n for n, c in champs.items()
               if c is None or c[1]["feature_names"] != feat_cols]
        if bad:
            # feature set drifted since the champions were trained — a warm continue
            # would silently mis-map columns, so fall back to a full refit on full data
            print(f"champion/feature mismatch on heads {bad} — falling back to full "
                  f"refit", flush=True)
            mode, why, champs = "full", "feature set changed after prep", {}
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
    score_dates = dates[-max(WARM_SESSIONS, 2 * int(cfg.barrier.h_days) + 21):]
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
    ens = ensemble_rank(scores, m)
    sel = select_long(ens, m, cfg)
    print(f"selection: {cfg.port.get('selection', 'top_decile_long')} "
          f"(N={cfg.port.get('top_n', 20)}) -> event-engine live book", flush=True)
    hedge_mode = str(cfg.port.get("hedge", "short_SPY_beta_matched"))
    if hedge_mode == "none":
        print("hedge: none (cash book — no SPY short leg)", flush=True)
    hedge_w = 0.0
    cm = CostModel(per_trade_bps=float(cfg.cost.per_trade_bps),
                   borrow_gc_bps_yr=float(cfg.cost.borrow_gc_bps_yr))
    # M13 regime overlay + M14 vol targeting scale the ENTERING tranche, exactly
    # as stage3 does: a pre-run over the window feeds the causal vol-target scale
    gm = regime_multiplier(idx_blk, float(cfg.regime.vol_threshold_ann),
                           float(cfg.regime.gross_multiplier_risk_off)) \
        .reindex(score_dates).fillna(1.0)
    eng_kw = engine_opts_from_cfg(cfg)
    pre = run_event_backtest(sel, panel, sigma32, cm, cfg, day_budget_mult=gm, **eng_kw)
    vt = vol_target_scale(pre["daily_net"].loc[score_dates[0]:],
                          float(cfg.port.vol_target_ann),
                          float(cfg.port.vol_target_scale_cap))
    budget = (gm * vt.reindex(score_dates).fillna(1.0)).clip(lower=0.0)
    lb = live_book(sel, panel, sigma32, cm, cfg, day_budget_mult=budget)
    t_last = score_dates[-1]
    assert lb["as_of"] == t_last
    entries, holds_df, due_df = lb["entries"], lb["holds"], lb["due_exits"]
    print(f"live book @ {t_last.date()}: {len(entries)} entering "
          f"(gross {float(entries.sum()):.3f}, budget {lb['budget']:.2f}, cap scale "
          f"{lb['cap_scale']:.2f}), {len(holds_df)} open lots "
          f"(gross {float(holds_df['tranche_w'].sum()) if len(holds_df) else 0.0:.3f}), "
          f"{len(due_df)} lots due at the open", flush=True)

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

    def _f(x, nd=2):
        return None if x is None or not np.isfinite(x) else round(float(x), nd)

    held_w = holds_df.groupby("ticker")["tranche_w"].sum() if len(holds_df) \
        else pd.Series(dtype=float)
    buys, holds, sells = [], [], []
    for t, wt in entries.sort_values(ascending=False).items():
        buys.append({
            "ticker": t, "target_weight": round(float(wt), 5),
            "current_weight": round(float(held_w.get(t, 0.0)), 5),
            "ensemble_rank": _f(ens_last.get(t, np.nan), 4),
            "last_close": _f(last_close.get(t, np.nan)),
            "stop_pct": _f(-float(thr.get(t, np.nan)) * 100),
            "profit_take_pct": _f(float(thr.get(t, np.nan)) * 100),
            "trail_pct": _f(float(trail_w.get(t, np.nan)) * 100) if trail_on else None,
            "levels_basis": "fill",
            "max_hold_sessions": h_bar, "sessions_left": h_bar,
            "lot": "new tranche (fills at the next open)"})
    for t, g in (holds_df.groupby("ticker") if len(holds_df) else []):
        g = g.sort_values("entry_date")
        # the ticket prices levels off the last close: report the most binding
        # lot's stop (highest) and the nearest profit-take, both vs last close
        holds.append({
            "ticker": t, "target_weight": round(float(g["tranche_w"].sum()), 5),
            "current_weight": round(float(g["tranche_w"].sum()), 5),
            "ensemble_rank": _f(ens_last.get(t, np.nan), 4),
            "last_close": _f(last_close.get(t, np.nan)),
            "stop_pct": _f(float(g["stop_vs_close_pct"].max())),
            "profit_take_pct": _f(float(g["pt_vs_close_pct"].min())),
            "trail_pct": _f(float(trail_w.get(t, np.nan)) * 100) if trail_on else None,
            "levels_basis": "last_close",
            "max_hold_sessions": h_bar,
            "sessions_left": int(g["sessions_left"].min()),
            "lots": [{"entry_date": str(r.entry_date.date()),
                      "fill_date": str(r.fill_date.date()),
                      "weight": round(float(r.tranche_w), 5),
                      "sessions_left": int(r.sessions_left),
                      "stop_kind": r.stop_kind,
                      "stop_vs_close_pct": _f(r.stop_vs_close_pct),
                      "pt_vs_close_pct": _f(r.pt_vs_close_pct)}
                     for r in g.itertuples(index=False)]})
    for t, g in (due_df.groupby("ticker") if len(due_df) else []):
        sells.append({
            "ticker": t, "target_weight": 0.0,
            "current_weight": round(float(g["tranche_w"].sum()), 5),
            "last_close": _f(last_close.get(t, np.nan)),
            "reason": "vertical barrier: MOO sell at the next open (entered "
                      + ", ".join(str(x.date()) for x in g["entry_date"]) + ")",
            "lots": [{"entry_date": str(r.entry_date.date()),
                      "weight": round(float(r.tranche_w), 5)}
                     for r in g.itertuples(index=False)]})

    # ---- diff vs the operator's own positions file (names outside the book) ----
    current = pd.Series(dtype=float)
    if positions_csv and Path(positions_csv).exists():
        pos_df = pd.read_csv(positions_csv)
        current = pos_df.set_index("ticker")["weight"] if "weight" in pos_df else \
            pd.Series(dtype=float)
    in_book = set(entries.index) | set(held_w.index)
    for t, cur in current.items():
        if t not in in_book and abs(cur) > 1e-6 and not any(s["ticker"] == t for s in sells):
            sells.append({"ticker": t, "target_weight": 0.0,
                          "current_weight": round(float(cur), 5),
                          "last_close": _f(last_close.get(t, np.nan)),
                          "reason": "held but not in the event-engine book"})
    gross_book = float(entries.sum()) + float(held_w.sum())
    book_names = sorted(in_book)

    suggestions = {
        "as_of_close": str(t_last.date()),
        "execute_at": "next session MOO (G-02: signals from close t earn from open t+1)",
        "stamp": artifact_stamp(config_hash, d["m1"].data_snapshot_id(), git_sha(), seed),
        "training": {
            "mode": mode, "reason": why,
            "train_through": train_through,
            "panel_tail_since": str(since.date()) if since is not None else None,
            "adopted": {k: bool(v.get("adopted", True)) for k, v in heads_info.items()},
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
                      "spy_hedge_weight": round(hedge_w, 4)},
        "book_engine": {"engine": "M15 event engine replay (run_event_backtest + live_book)",
                        "window_sessions": int(len(score_dates)),
                        "options": {k: (None if v is None else v)
                                    for k, v in eng_kw.items()},
                        "sizing": "weights are fractions of NAV at entry: "
                                  "inverse-vol within the top-N tranche / tranches x "
                                  "regime x vol-target budget, scaled to the cash cap",
                        "note": "replaces the Stage-1 15-tranche rotation the ticket "
                                "used until 2026-09-08 — the book shown is the one "
                                "the backtest trades"},
        "buys_or_increases": buys,
        "holds": holds,
        "sells_or_exits": sells,
        "exit_rules": {"engine": "M5.2 triple barrier", "m": m_bar, "h_sessions": h_bar,
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

    md = [f"# Event-engine book for next open (signals @ close {t_last.date()})", "",
          f"- Names: {len(book_names)}, gross long {gross_book:.2f} "
          f"(entering {float(entries.sum()):.2f} + held {float(held_w.sum()):.2f}), "
          f"budget x{lb['budget']:.2f}, cap scale x{lb['cap_scale']:.2f}",
          f"- Heads valid RankIC: " + ", ".join(
              f"{k} {v['valid_rank_ic']:.3f}" for k, v in heads_info.items()),
          f"- Training: {mode} ({why})" + ("" if mode != "warm_update" and mode != "update"
              else " — " + ", ".join(
                  f"{k} {'adopted' if v.get('adopted') else 'kept champion'}"
                  for k, v in heads_info.items())), "",
          "| ticker | action | weight | rank | last close | stop % | PT % | trail % | "
          "sessions left | levels vs |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for row in buys[:40]:
        tp = row.get("trail_pct")
        md.append(f"| {row['ticker']} | BUY (new lot) | {row['target_weight']:.3%} | "
                  f"{_rk(row['ensemble_rank'])} | "
                  f"{row['last_close']} | {row['stop_pct']}% | +{row['profit_take_pct']}% | "
                  f"{'-' + str(tp) + '%' if tp is not None else 'off'} | {row['sessions_left']} | fill |")
    for row in holds[:60]:
        md.append(f"| {row['ticker']} | HOLD ({len(row['lots'])} lot"
                  f"{'s' if len(row['lots']) != 1 else ''}) | {row['target_weight']:.3%} | "
                  f"{_rk(row['ensemble_rank'])} | "
                  f"{row['last_close']} | {row['stop_pct']}% | +{row['profit_take_pct']}% | "
                  f"{'-' + str(row['trail_pct']) + '%' if row.get('trail_pct') is not None else 'off'} | "
                  f"{row['sessions_left']} | last close |")
    for row in sells[:40]:
        md.append(f"| {row['ticker']} | SELL at open | 0 |  | {row['last_close']} |  |  |  | 0 | "
                  f"{row['reason'][:40]} |")
    md += ["", "_Vertical exit: MOO " + str(h_bar) + " sessions after entry."
           + (" Trailing stop: each night raise the stop to the high since fill "
              "minus trail %, never below the fixed stop." if trail_on else "")
           + " HOLD rows price the most binding lot's levels off the last close. "
             "Research tooling, not financial advice._"]
    (out / "suggestions.md").write_text("\n".join(md))
    print(f"suggestions written: {len(buys)} buys/adds, {len(sells)} exits, "
          f"{len(holds)} holds", flush=True)
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
