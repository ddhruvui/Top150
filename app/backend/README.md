# Top150 API

Report + paper-trading API for the Top-150 EOD swing/position trading system. A
read-only slice over the report bundle the research pipeline published to MongoDB,
plus the paper-trading book the blueprint requires before real capital (BP15).

Nothing is computed here: `tools/build_reports.py` (in the main repo) turns pipeline
artifacts into the bundle and `tools/publish_mongo.py` writes it to Mongo; this API
only reads and slices it, so a number on screen always equals the number the
pipeline produced.

This directory is a git subtree of [ddhruvui/Top150](https://github.com/ddhruvui/Top150)
(`app/backend`); edit there and push with `scripts/push_repos.sh`.

## Run

```bash
npm install
cp .env.example .env     # DB_PASSWORD + MONGO_URI
npm start                # http://localhost:8787/api/health
npm test                 # paper-book + session-logic regression suite (no database needed)
node smoke.mjs [url]     # hits every read endpoint, local or deployed
```

Without `MONGO_URI` — or with `REPORTS_DIR=<dir>` — it reads the JSON bundle from
disk instead (the monorepo's local console).

## Deploy (Vercel)

`api/index.js` exports the Express app as one function; `vercel.json` rewrites every
path to it, so the app's `/api/*` routes work unchanged. Framework preset *Other*, no
build step. Environment variables: `DB_PASSWORD`, `MONGO_URI`, `MONGO_DB=Top150`,
`BUNDLE=top150`, optionally `CORS_ORIGIN=https://<ui-host>`.

## Data layout (database `Top150`)

| collection | document |
|---|---|
| `reports` | `_id: "<bundle>/<section>"` — `summary`, `equity`, `suggestions`, `trades_summary`, `trades_sample` (meta), `manifest`, `calendar`, `config`; each with `data`, `built_utc`, `published_utc` |
| `trades` | one per backtest trade; `{bundle, version, seq, ...}` — the API reads only the `version` named by `reports/<bundle>/trades_sample` |
| `predictions` | `_id: "<bundle>/<as_of_close>"` — every published book, by close date |
| `paper_books` | `_id: "<bundle>"` — the paper book |

## Endpoints

`GET /api/health · today · summary · equity · suggestions · config · trades/summary ·
trades?limit&offset&exit&ticker&year&minRank&outcome&sortKey&sortDir`
`GET /api/paper · POST /api/paper/open · /api/paper/:id/fill · /api/paper/:id/close ·
DELETE /api/paper/:id · POST /api/paper/settings · /api/paper/reset`
