#!/usr/bin/env python3
"""Is the SOURCE tape ready to compute against?

This repo does not download anything — a separate system owns every vendor tree
on crimtr8kbf. This is the read-only gate that answers whether that system has
finished for the session, BEFORE we spend a pod computing against a half-filled
tape. It reads each tree's `_run.json` manifest and nothing else; it never
writes, and it cannot (srcvol refuses any mutating operation).

The manifest is the real evidence of completion, not the presence of files: it
is written only when a fetcher reaches its end, and it carries per-job results.

Usage: verify_source.py [FLOOR_ISO]
  FLOOR_ISO  manifests older than this are reported STALE (pass the time the
             upstream run started; without it freshness is not checked).
Exit 0 only if every tree is fresh with zero hard failures.
"""
import json, os, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TREES = ["data", "data_nasdaq", "data_tiingo", "data_borrow", "data_calendar", "data_finbert"]
FLOOR = sys.argv[1] if len(sys.argv) > 1 else None
TMP = os.environ.get("TMPDIR", "/tmp")


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


floor = ts(FLOOR) if FLOOR else None
stale, failed = [], []
for tree in TREES:
    dst = os.path.join(TMP, f"_run_{tree}.json")
    r = subprocess.run([os.path.join(HERE, "srcvol"), "cp", f"{tree}/_run.json", dst, "--quiet"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{tree:16s} MANIFEST MISSING"); stale.append(tree); continue
    d = json.load(open(dst))
    ended = d.get("ended_at", "")
    e = ts(ended)
    fresh = floor is None or (e is not None and e >= floor)
    res = d.get("results") or []
    if isinstance(res, dict):
        res = list(res.values())
    ok = sum(1 for x in res if x.get("ok"))
    bad = [x for x in res if not x.get("ok")]
    added = sum(int(x.get("added") or 0) for x in res
                if isinstance(x.get("added"), (int, float)))
    if not fresh:
        stale.append(tree)
    print(f"{tree:16s} {'FRESH' if fresh else 'STALE':6s} ended={ended:32s} "
          f"jobs={len(res):5d} ok={ok:5d} fail={len(bad):4d} added={added}")
    # Tiingo logs budget overruns as DEFER: non-fatal by design, resumed next run.
    defer = [x for x in bad if "DEFER" in str(x.get("error", "")).upper()]
    hard = [x for x in bad if x not in defer]
    if defer:
        print(f"{'':16s}   deferred(budget)={len(defer)}  (non-fatal, resumes next run)")
    for x in hard[:12]:
        print(f"{'':16s}   FAIL {x.get('symbol')}/{x.get('dataset')}: {str(x.get('error'))[:110]}")
    if len(hard) > 12:
        print(f"{'':16s}   ... +{len(hard) - 12} more")
    if hard:
        failed.append((tree, len(hard)))

print()
print("STALE:", stale or "none")
print("HARD FAILURES:", failed or "none")
sys.exit(1 if (stale or failed) else 0)
