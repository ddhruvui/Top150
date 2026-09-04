# Top150 research console (UI)

React + Vite front end for the Top-150 EOD trading system: **Today** (the trade
ticket for the next open), **Dashboard** (G-11 verdict, gates, equity curve),
**Suggestions** (the target book with barrier levels), **Backtest** (what was
suggested vs what happened), **Paper trading** (BP15). It renders whatever the API
serves; nothing is computed in the browser.

This directory is a git subtree of [ddhruvui/Top150](https://github.com/ddhruvui/Top150)
(`app/frontend`); edit there and push with `scripts/push_repos.sh`.

## Run

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend on :8787
npm run build      # dist/
```

## Deploy (Render static site)

- Build command `npm ci && npm run build`, publish directory `dist`.
- Environment variable `VITE_API_BASE=https://<api-host>` (the Vercel URL, no trailing
  slash). It is inlined at build time — change it and redeploy with a cleared cache.
- No rewrites needed: pages are addressed by URL hash (`#today`, `#dashboard`, …).

`render.yaml` carries the same settings for a Blueprint deploy.
