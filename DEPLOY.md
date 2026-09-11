# Deploying the research console

The console is three pieces, each created by hand once, then fed automatically:

| piece | where | repo / source | what it holds |
|---|---|---|---|
| **MongoDB Atlas**, database `Top150` | Atlas | filled by `tools/publish_mongo.py` | the published report bundle, the trade ledger sample, prediction history, the paper book |
| **API** (`app/backend`) | Vercel, one serverless function — **https://top150-be.vercel.app** | [ddhruvui/Top150BE](https://github.com/ddhruvui/Top150BE) `main` | reads Mongo; owns the paper book |
| **UI** (`app/frontend`) | Render static site — **https://top150fe.onrender.com** | [ddhruvui/Top150FE](https://github.com/ddhruvui/Top150FE) `main` | React build that calls the API |

All code lives in [ddhruvui/Top150](https://github.com/ddhruvui/Top150); the two deploy
repos are git subtrees of it (`scripts/push_repos.sh` keeps all three in step).
**No `.env` is ever committed** — every tree ignores `.env` and `.env.*`, and the push
script refuses to run if one is tracked.

## 0. Atlas (one time)

- A database user with `readWrite` on `Top150` — the one in `MONGO_URI`.
- **Network Access → allow `0.0.0.0/0`.** Vercel functions have no fixed egress IP, so
  an allow-list cannot name them. This also covers the laptop that runs the publish.
- Nothing to create by hand: the publisher creates the collections and indexes.

## 1. Publish the bundle (from this repo)

```bash
cp .env.example .env        # fill DB_PASSWORD and MONGO_URI (the <db_password> placeholder is fine)
python3 tools/publish_mongo.py --src reports/top150 --bundle top150
```

Prints one line per section and a read-back of what the UI will show. From now on
`mirror_top150.sh` runs this itself as its last step (`PUBLISH_MONGO=0` skips it).
The first publish also seeds the Mongo paper book from the old local
`app/backend/data/paper_book.json`, once.

## 2. API on Vercel

1. **Add New → Project → Import** `ddhruvui/Top150BE`, production branch `main`.
2. Framework preset **Other**. Root directory `.`. Leave Build Command and Output
   Directory empty (there is nothing to build — `api/index.js` is the function and
   `vercel.json` routes every path to it).
3. **Environment Variables** (all environments):

   | name | value |
   |---|---|
   | `DB_PASSWORD` | the Atlas password |
   | `MONGO_URI` | `mongodb+srv://<user>:<db_password>@<cluster>.mongodb.net/?appName=Cluster0` (placeholder kept literally). **The cluster must be `stockscluster.7njjp80` — the live one.** Vercel keeps its OWN copy of this value, so it can silently disagree with the repo-root `.env`; if they diverge the pipeline publishes where nobody reads. |
   | `MONGO_DB` | `Top150` |
   | `BUNDLE` | `top150` |
   | `CORS_ORIGIN` | `https://top150fe.onrender.com` (the Render site — add after step 3) |

4. Deploy, then open `https://top150-be.vercel.app/api/health` — expect
   `{"ok":true,"source":"mongo","bundle":"top150","bundle_present":true,...}`.
   Full check from `app/backend`: `node smoke.mjs https://top150-be.vercel.app`.
   (Deployed 2026-09-04; a cold start costs ~4 s on the first request, then ~200 ms.)

## 3. UI on Render

1. **New → Static Site**, connect `ddhruvui/Top150FE`, branch `main`.
2. Build command `npm ci && npm run build`; publish directory `dist`.
3. Environment variable **`VITE_API_BASE`** = `https://top150-be.vercel.app` (no trailing
   slash). Vite inlines it at build time, so changing it later needs a redeploy
   (*Manual Deploy → Clear build cache & deploy*).
4. No rewrite rules are needed — the app routes by URL hash.

`render.yaml` in the FE repo carries the same settings if you prefer *New → Blueprint*.

Then go back to Vercel, set `CORS_ORIGIN=https://top150fe.onrender.com`, redeploy — the
API now answers only that site's browser calls. (Both were live on 2026-09-04.)

## Day to day

- **New predictions:** `verify_source.py` → `market` → `predict`. The predict **pod
  publishes itself**: after `job=0` it runs `tools/pod_publish.sh` (G-02 against the
  source, bundle build, MongoDB publish) and the deployed UI shows the new book within
  ~30 s. Nothing is downloaded to a laptop. The launcher hands the pod the Mongo
  credentials from this repo's `.env`; look for `publish=0` in the pod log.
  `mirror_top150.sh` is optional now — it refreshes the local `reports/top150` git
  record and re-publishes the same content.
- **Quarterly research refresh:** `stage1` → `stage2` → `stage3`. The **stage3 pod
  publishes too**, in *research* mode: gates, members, equity curve, CPCV and the trade
  ledger go up; the `suggestions` section is left untouched, so the book on the UI stays
  the last G-02-verified one until the next daily predict. Look for `publish=0` in the
  stage3 log.
- **Code changes:** edit and commit **here**, then `scripts/push_repos.sh`. It pushes
  this branch to `Top150` and the two subtrees to `Top150BE` / `Top150FE`; Vercel and
  Render redeploy from `main` on their own.
- **Paper book:** lives in Mongo (`paper_books`), so the deployed UI and a local
  `npm start` (with `.env`) see the same positions.
- **History:** every publish also records the book under `predictions` keyed by its
  close date — the files alone never kept that.

## Local runs still work

```bash
cd app/backend && npm start                          # reads Mongo via ../../.env
REPORTS_DIR=../../reports/top150 npm start           # or the JSON files, no database
scripts/serve_top150_console.sh                      # files on :8790, as before
cd app/frontend && npm run dev                       # proxies /api to :8787
```

## If something is off

| symptom | cause |
|---|---|
| `/api/health` → 503 `MongoServerSelectionError` | Atlas network access, or a wrong password |
| `... not published yet` | run the publish (step 1) |
| UI: *Could not load* and a CORS error in the console | `CORS_ORIGIN` does not match the Render URL exactly, or `VITE_API_BASE` is unset (calls then hit Render itself and 404) |
| UI: unstyled page, console says *Refused to apply style … MIME type ('text/plain')* | the CSS request got a 404 — Render answers missing files with `text/plain` and `nosniff`, and Chrome reports that as a MIME error. It happens when the page is opened during the ~2 min a Render deploy takes (assets not yet in place). Nothing is wrong with the build: hard-reload (⌘⇧R) once the deploy shows *Live* |
| publish fails with `CERTIFICATE_VERIFY_FAILED` | macOS Python without the CA chain: `pip install certifi` (the script uses it when present) |
| pod log says `publish=0` but the UI still shows an older `as_of` | the book went to a cluster the deployment does not read. Happened 2026-09-11: repo `.env` still named the retired `cluster0.znyjnot` while Vercel read `stockscluster.7njjp80`, so three sessions' books published "successfully" into a cluster nobody served. `publish=0` only proves a write to whatever `MONGO_URI` names. `tools/publish_mongo.py` now refuses a cluster other than `EXPECT_HOST_DEFAULT` (override with `MONGO_HOST_EXPECT`, empty to disable). Confirm the deployment moved: `curl -s 'https://top150-be.vercel.app/api/health?cb=$(date +%s)'` and check `sections.suggestions.as_of` — the in-process cache TTL is only 30 s, so anything staler is a real mismatch, not caching |
