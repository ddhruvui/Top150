#!/usr/bin/env python3
"""Rank and compare experiment variants (src/pipeline/experiments.py output).

    python3 tools/exp_compare.py <experiments_report.json> [--anchor NAME]
                                 [--out reports/exp_short/<round>] [--tag TAG]

Writes <out>/summary.md (ranked table + deltas vs the anchor) and copies the
report JSON beside it, so a sweep's result lives in git separately from the
production bundle under reports/top150. Research tooling, not financial advice.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _pct(x, d=1):
    return "" if x is None else f"{x * 100:.{d}f}%"


def _f(x, d=2):
    return "" if x is None else f"{x:.{d}f}"


def _period(r, key, field):
    p = (r.get("periods") or {}).get(key) or {}
    return p.get(field)


def _exit_mix(r):
    hc = r.get("hit_counts") or {}
    n = sum(hc.values()) or 1
    order = ["upper", "lower", "trail", "flat", "vertical", "censored"]
    return " ".join(f"{k[:4]} {hc[k] / n * 100:.0f}%" for k in order if hc.get(k))


def rows_for(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        out.append({
            "name": r["name"],
            "sharpe": r.get("sharpe_net"), "cagr": r.get("cagr"), "mdd": r.get("mdd"),
            "vol": r.get("ann_vol"), "hold": r.get("avg_hold"),
            "trades": r.get("n_trades"), "win": r.get("win_rate"),
            "gross": r.get("avg_gross"), "cost_yr": r.get("cost_nav_per_yr"),
            "l3_cagr": _period(r, "last3y", "cagr"), "l3_sr": _period(r, "last3y", "sharpe"),
            "l5_cagr": _period(r, "last5y", "cagr"),
            "h": r.get("h"), "cost_bps": r.get("cost_bps"),
            "members": len(r.get("members") or []),
            "exits": _exit_mix(r),
            "levers": ", ".join(f"{k}={r[k]}" for k in
                                ("trail_m", "flat_k", "trend", "conv_weight",
                                 "skip_earnings", "top_n", "exit_rank", "sent_gate")
                                if r.get(k) not in (None, False)),
        })
    return out


def render(report: dict, anchor: str | None, tag: str) -> str:
    res = sorted(report["results"], key=lambda r: -(r.get("sharpe_net") or -9))
    rows = rows_for(res)
    a = next((x for x in rows if x["name"] == anchor), None) if anchor else None
    hdr = ["#", "variant", "SR", "CAGR", "MDD", "vol", "hold", "trades", "win",
           "gross", "cost/yr", "3y CAGR", "3y SR", "5y CAGR", "h", "bps", "mem",
           "exit mix", "levers"]
    lines = [f"# Experiment round {tag}", "",
             f"- stamp: `{json.dumps(report.get('stamp'), default=str)}`",
             f"- variants: {len(rows)} · trials ledger N: {report.get('n_trials_ledger')}",
             (f"- anchor: **{anchor}** — SR {_f(a['sharpe'])}, CAGR {_pct(a['cagr'])}, "
              f"MDD {_pct(a['mdd'])}, hold {_f(a['hold'], 1)}" if a else "- anchor: none"),
             "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for i, x in enumerate(rows, 1):
        lines.append("| " + " | ".join([
            str(i), x["name"], _f(x["sharpe"]), _pct(x["cagr"]), _pct(x["mdd"]),
            _pct(x["vol"]), _f(x["hold"], 1), f"{x['trades']:,}" if x["trades"] else "",
            _pct(x["win"]), _f(x["gross"]), _pct(x["cost_yr"]), _pct(x["l3_cagr"]),
            _f(x["l3_sr"]), _pct(x["l5_cagr"]), str(x["h"] or ""), str(x["cost_bps"] or "15"),
            str(x["members"]), x["exits"], x["levers"]]) + " |")
    if a:
        lines += ["", f"## Deltas vs {anchor}", "",
                  "| variant | dSR | dCAGR | dMDD | dhold | d3y CAGR |", "|---|---|---|---|---|---|"]
        for x in rows:
            if x["name"] == anchor:
                continue
            d = lambda k, f=lambda v: f"{v:+.2f}": (f(x[k] - a[k]) if x[k] is not None and a[k] is not None else "")
            lines.append("| " + " | ".join([
                x["name"], d("sharpe"), d("cagr", lambda v: f"{v * 100:+.1f}pp"),
                d("mdd", lambda v: f"{v * 100:+.1f}pp"), d("hold", lambda v: f"{v:+.1f}"),
                d("l3_cagr", lambda v: f"{v * 100:+.1f}pp")]) + " |")
    lines += ["", "_Net of the per-variant cost assumption; walk-forward, scored window only. "
              "Research tooling under the repo's own gates — not financial advice._"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--anchor", default="H0_book_all7")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    rep = json.loads(Path(a.report).read_text())
    tag = a.tag or Path(a.report).parent.name
    md = render(rep, a.anchor, tag)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.md").write_text(md)
        dst = out / "experiments_report.json"
        if Path(a.report).resolve() != dst.resolve():
            shutil.copy(a.report, dst)
        print(f"wrote {out / 'summary.md'}")
    else:
        print(md)


if __name__ == "__main__":
    main()
