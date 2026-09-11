#!/usr/bin/env python3
"""Publish the report bundle to MongoDB — the last step of the mirror.

Reads reports/<bundle>/*.json (what tools/build_reports.py wrote) and upserts it
into the database the deployed API reads, so a number on the deployed UI always
equals the number the pipeline produced. Nothing is recomputed here.

Collections (database MONGO_DB, default Top150):

    reports       one document per section:
                  { _id: "<bundle>/<section>", bundle, section, data, built_utc, published_utc }
    trades        one document per backtest trade in the sample. The live
                  `version` is stamped on reports/<bundle>/trades_sample, and the
                  API only reads rows of that version — so a publish in progress
                  (new rows in, old rows not yet gone) is invisible to readers.
    predictions   every published book keyed by its close date — the history the
                  files alone never keep: { _id: "<bundle>/<as_of_close>", ... }
    paper_books   the paper book. Seeded ONCE from the local file (--seed-paper)
                  if no document exists yet; the API owns it from then on.

    python3 tools/publish_mongo.py --src reports/top150 --bundle top150
    python3 tools/publish_mongo.py --dry-run            # show what would go up
    python3 tools/publish_mongo.py --exclude suggestions  # research refresh: leave the
                                                          # book (and its history) untouched

Environment (shell, else repo-root .env): MONGO_URI (Atlas's literal
`<db_password>` placeholder is filled from DB_PASSWORD), MONGO_DB, BUNDLE.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SECTIONS = ["summary", "equity", "suggestions", "trades_summary", "manifest",
            "calendar", "config"]           # + trades_sample, handled separately
TRADE_CHUNK = 1000

# The Atlas cluster the deployed API actually reads. A mis-pointed MONGO_URI
# still publishes "successfully": on 2026-09-11 the daily book landed on a
# retired cluster, the pod logged publish=0, and the UI served a 3-session-old
# book until someone noticed. Fail loudly instead of silently.
# Override with MONGO_HOST_EXPECT; set it empty to disable the check.
EXPECT_HOST_DEFAULT = "stockscluster.7njjp80.mongodb.net"


# ------------------------------------------------------------------ env
def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines; the real environment always wins over the file."""
    try:
        text = path.read_text()
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k, v)


def uri_host(uri: str) -> str:
    """Host[:port] out of a mongodb+srv URI, without the credentials."""
    m = re.search(r"@([^/?,]+)", uri)
    return m.group(1) if m else ""


def mongo_uri() -> str:
    uri = os.environ.get("MONGO_URI", "")
    if not uri:
        sys.exit("MONGO_URI is not set (shell or .env at the repo root)")
    pw = os.environ.get("DB_PASSWORD")
    filled = uri.replace("<db_password>", urllib.parse.quote_plus(pw)) if pw else uri
    expect = os.environ.get("MONGO_HOST_EXPECT", EXPECT_HOST_DEFAULT).strip()
    host = uri_host(filled)
    if expect and expect not in host:
        sys.exit(
            f"refusing to publish: MONGO_URI names cluster {host!r}, not the\n"
            f"expected {expect!r}. The deployed API reads the expected cluster, so\n"
            "publishing elsewhere succeeds silently and leaves the UI stale.\n"
            "Fix MONGO_URI in the repo-root .env, or set MONGO_HOST_EXPECT to the\n"
            "new host (empty string disables this check)."
        )
    return filled


def connect():
    from pymongo import MongoClient
    kw = {"serverSelectionTimeoutMS": 15000}
    try:                       # macOS Python builds lack the Atlas CA chain
        import certifi
        kw["tlsCAFile"] = certifi.where()
    except ImportError:
        pass
    client = MongoClient(mongo_uri(), **kw)
    client.admin.command("ping")
    return client


# ------------------------------------------------------------- publishing
def read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def kb(obj) -> str:
    return f"{len(json.dumps(obj)) / 1024:7.1f} KB"


def ensure_indexes(db) -> None:
    key = [("bundle", 1), ("version", 1)]
    for extra in ("seq", "ticker", "entry_date", "barrier_hit", "exit_ret_net",
                  "ensemble_rank"):
        db.trades.create_index(key + [(extra, 1)])
    db.predictions.create_index([("bundle", 1), ("as_of_close", -1)])
    db.reports.create_index([("bundle", 1), ("section", 1)])


def publish(db, src: Path, bundle: str, dry: bool, seed_paper: Path | None,
            exclude: set[str] = frozenset()) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = read_json(src / "manifest.json") or {}
    built = manifest.get("built_utc")
    print(f"bundle {bundle!r} from {src}  (built {built or '?'})")

    docs = {}
    for name in SECTIONS:
        if name in exclude:
            print(f"  -- {name:15s} excluded, left as published")
            continue
        data = read_json(src / f"{name}.json")
        if data is None:
            print(f"  -- {name:15s} missing, skipped")
            continue
        docs[name] = data
        print(f"  ok {name:15s} {kb(data)}")
    # a manifest must not describe a book this publish did not write
    if "suggestions" in exclude and "manifest" in docs:
        (docs["manifest"].get("sections") or {}).pop("suggestions", None)

    sample = None if "trades_sample" in exclude else read_json(src / "trades_sample.json")
    rows = (sample or {}).get("rows") or []
    if "trades_sample" in exclude:
        print(f"  -- {'trades_sample':15s} excluded, left as published")
    elif sample:
        print(f"  ok {'trades_sample':15s} {kb(sample)}  -> {len(rows):,} trade rows")
    else:
        print("  -- trades_sample   missing (run stage3 + FULL_MIRROR=1)")
    if not docs and not sample:
        print("nothing to publish")
        return 1

    sug = docs.get("suggestions")
    if dry:
        print("dry run — nothing written")
        return 0

    ensure_indexes(db)

    # 1. trade rows under a fresh version (readers still see the old version)
    version = now
    if sample:
        for i in range(0, len(rows), TRADE_CHUNK):
            chunk = [{"bundle": bundle, "version": version, "seq": i + j, **r}
                     for j, r in enumerate(rows[i:i + TRADE_CHUNK])]
            db.trades.insert_many(chunk, ordered=False)
        docs["trades_sample"] = {"n_total": sample.get("n_total"), "note": sample.get("note"),
                                 "version": version, "n_rows": len(rows)}

    # 2. section documents — flipping trades_sample.version is the atomic switch
    for name, data in docs.items():
        db.reports.replace_one(
            {"_id": f"{bundle}/{name}"},
            {"_id": f"{bundle}/{name}", "bundle": bundle, "section": name, "data": data,
             "built_utc": built, "published_utc": now},
            upsert=True)

    # 3. retire the previous ledger version
    if sample:
        gone = db.trades.delete_many({"bundle": bundle, "version": {"$ne": version}})
        if gone.deleted_count:
            print(f"  retired {gone.deleted_count:,} rows of the previous ledger version")

    # 4. prediction history — one document per close, never overwritten by a
    #    later publish of the SAME close unless the content changed
    if sug and sug.get("as_of_close"):
        as_of = sug["as_of_close"]
        db.predictions.replace_one(
            {"_id": f"{bundle}/{as_of}"},
            {"_id": f"{bundle}/{as_of}", "bundle": bundle, "as_of_close": as_of,
             "n_names": len(sug.get("buys_or_increases") or []),
             "stamp": sug.get("stamp"), "training": sug.get("training"),
             "data": sug, "built_utc": built, "published_utc": now},
            upsert=True)
        n_hist = db.predictions.count_documents({"bundle": bundle})
        print(f"  ok predictions     {as_of} recorded ({n_hist} closes in history)")

    # 5. one-time paper-book seed from the pre-Mongo local file
    if seed_paper is not None:
        if db.paper_books.find_one({"_id": bundle}):
            print("  -- paper book      already in Mongo, local file not used")
        else:
            book = read_json(seed_paper)
            if book:
                db.paper_books.insert_one({"_id": bundle, **book})
                print(f"  ok paper book      seeded from {seed_paper} "
                      f"({len(book.get('positions', []))} positions)")
            else:
                print(f"  -- paper book      no seed file at {seed_paper}; the API starts one")

    # readback — the deployed UI will show exactly this
    s = db.reports.find_one({"_id": f"{bundle}/summary"}) or {}
    n_live = db.trades.count_documents({"bundle": bundle, "version": version}) if sample else 0
    print(f"published {len(docs)} sections"
          + (f" + {n_live:,} trades" if sample else "")
          + f" -> db {db.name!r}; summary verdict "
          f"{((s.get('data') or {}).get('gates') or {}).get('verdict')} "
          f"(generated {(s.get('data') or {}).get('generated_utc')})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=None, help="bundle dir (default reports/<bundle>)")
    ap.add_argument("--bundle", default=None, help="bundle name (default $BUNDLE or top150)")
    ap.add_argument("--db", default=None, help="database (default $MONGO_DB or Top150)")
    ap.add_argument("--seed-paper", default=str(REPO / "app/backend/data/paper_book.json"),
                    help="local paper book to seed Mongo with, once ('' to skip)")
    ap.add_argument("--exclude", default="",
                    help="comma-separated sections to leave untouched (e.g. suggestions)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    exclude = {s.strip() for s in args.exclude.split(",") if s.strip()}
    unknown = exclude - set(SECTIONS) - {"trades_sample"}
    if unknown:
        sys.exit(f"--exclude: unknown section(s) {sorted(unknown)}; known: {SECTIONS + ['trades_sample']}")

    load_dotenv(REPO / ".env")
    bundle = args.bundle or os.environ.get("BUNDLE") or "top150"
    src = Path(args.src) if args.src else REPO / "reports" / bundle
    if not src.is_dir():
        sys.exit(f"no bundle directory at {src}")
    seed = Path(args.seed_paper) if args.seed_paper else None

    if args.dry_run:
        return publish(None, src, bundle, True, seed, exclude)
    client = connect()
    db = client[args.db or os.environ.get("MONGO_DB") or "Top150"]
    try:
        return publish(db, src, bundle, False, seed, exclude)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
