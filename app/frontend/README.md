# Top150 research console (UI)

React + Vite front end for the Top150 EOD trading system. Pages are grouped by job:

- **Trade** — **Today** (the trade ticket for the next open, as numbered steps) and
  **Paper trading** (BP15: fills, slippage, safety rules, decay monitor).
- **Research** — **Dashboard** (G-11 verdict, metrics against their bars, gates,
  equity curve), **Pots** (one pot per stock, backtest and live), **Suggestions**
  (the target book with barrier levels), **Backtest** (what was suggested vs what
  happened).

It renders whatever the API serves; nothing is computed in the browser.

This directory is a git subtree of [ddhruvui/Top150](https://github.com/ddhruvui/Top150)
(`app/frontend`); edit there and push with `scripts/push_repos.sh`.

## Run

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend on :8787
npm run build      # dist/
npm test           # vitest + Testing Library, ~100 tests, no API needed
```

`API_PROXY=http://localhost:8791 npm run dev` points the dev server at another API.
The repo's `.claude/launch.json` has a sandbox pair (`top150-api-sandbox` on :8791,
reading `reports/top150` and writing paper trades to `app/backend/data/sandbox/`, and
`top150-ui-dev` on :5191) for trying the UI without touching MongoDB.

## Tests

`src/test/*.test.jsx` render each page against fixtures captured from a real API run
(`src/test/fixtures/`, trimmed), with `src/api.js` mocked. They cover the shell
(routing, focus, theme, menu), every page's content and actions (track, fill, close,
cancel, settings, filters, paging, server-side sort, drawer), error/empty states and
the shared components and formatters.

## Design notes

- `src/theme.css` holds the tokens (surfaces, text, accent, status washes) for light
  and dark. Profit/loss colour is never the only channel: every value also carries a
  sign, a ▲/▼ glyph or a word.
- Charts (`components/Chart.jsx`) measure their container, so axis text stays 11px in
  narrow cards; log axes tick on the 1-2-5 ladder.
- Wide analytic tables keep the ticker column sticky; the Today tables turn into
  stacked cards under 860px.

## Deploy (Render static site)

- Build command `npm ci && npm run build`, publish directory `dist`.
- Environment variable `VITE_API_BASE=https://<api-host>` (the Vercel URL, no trailing
  slash). It is inlined at build time — change it and redeploy with a cleared cache.
- No rewrites needed: pages are addressed by URL hash (`#today`, `#dashboard`, …).

`render.yaml` carries the same settings for a Blueprint deploy.
