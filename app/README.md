# Research console — backend + frontend

A read-only view of the pipeline's final reports, plus the paper-trading book the
blueprint requires before real capital (BP15).

```
app/
  backend/    Node + Express — serves the published bundle from MongoDB, owns the paper book
              (deployed on Vercel from github.com/ddhruvui/Top150BE — a subtree of this dir)
  frontend/   React + Vite — today's ticket, dashboard, suggestions, backtest, paper trading
              (deployed on Render from github.com/ddhruvui/Top150FE — a subtree of this dir)
```

**Deployment, end to end: [DEPLOY.md](../DEPLOY.md).** The deployed UI reads only what
`tools/publish_mongo.py` has published to the `Top150` database; the mirror step
publishes automatically.

## Run it locally

```bash
# API — reads MongoDB via ../../.env (or the JSON files with REPORTS_DIR / no MONGO_URI)
cd app/backend && npm install && npm start        # http://localhost:8787

# UI in dev mode (hot reload, proxies /api to 8787)
cd app/frontend && npm install && npm run dev     # http://localhost:5173
# …or build once and let the API serve it:
cd app/frontend && npm run build
```

`npm test` in `app/backend` runs the paper-book regression suite (no database needed);
`node smoke.mjs <url>` checks every read endpoint of a running API, local or deployed.

## Where the numbers come from

Nothing is recomputed in the app. `tools/build_reports.py` reads the artifacts the
RunPod jobs wrote (`derived/`) and emits `reports/<bundle>/*.json`;
`tools/publish_mongo.py` writes that bundle to MongoDB, and the API slices it. So a
number on screen always equals the number the pipeline produced — the API cannot
drift from it.

To refresh after a pipeline run (pull, rebuild, G-02 check, publish — one command):

```bash
.claude/skills/top150-pipeline/scripts/mirror_top150.sh
# or, just the publish of an already-built bundle:
python3 tools/publish_mongo.py --src reports/top150 --bundle top150
```

## Pages

| Page | What it answers |
|---|---|
| **Today** (landing) | What do I do at the next open? Dates itself to the next NYSE session — Friday evening and all weekend both point at Monday — and diffs the target book against what you actually hold, so a name reads BUY only if it is not already held, SELL if held but dropped from the target, HOLD otherwise. Also lists time-barrier exits that come due, and warns if the signals predate the last close. |
| **Dashboard** | Does this ship? G-11 verdict, the gate table, equity curve, member Rank ICs against the 0.02 admission floor, CPCV path spread, cost sensitivity, and the two free baselines it must beat. |
| **Suggestions** | What would I trade at the next open? The target book with each entry's triple-barrier levels, flagged where the barrier is too wide to ever trigger. One click pushes a name into the paper book. |
| **Backtest** | What was suggested, and what happened? 376k barrier trades: exit mix, win rate, return by conviction decile and holding length, and a filterable ledger. |
| **Paper trading** | The BP15 stage. Record fills against the official open to measure slippage (M18 → M15-03), watch the PDT budget and kill switch, and track the G-11 decay monitor. |

## Colour

Profit/loss uses market convention — green up, red down — which is the sanctioned
use of the status palette (the colour genuinely means good/bad). Green vs red
measures ΔE 4.1 under deuteranopia, far below the ≥8 separation target, so **hue is
never the only channel**: every profit/loss value also carries a sign, a ▲/▼ glyph,
or an explicit word ("Profit-take" / "Stop"), and diverging bars sit above or below
a zero baseline. Series identity (book vs SPY vs momentum) uses the validated
blue/orange/aqua categorical order, which clears all-pairs CVD separation in both
light and dark mode.
