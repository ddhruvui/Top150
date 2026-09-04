// Report + paper-trading API (the Express app, no listener).
//
// Read side is a thin slice over the report bundle that tools/build_reports.py
// built from RunPod artifacts and tools/publish_mongo.py published — no metric
// is recomputed here, so the API can never disagree with the pipeline. Write
// side is the paper book (M18/BP15).
//
// src/server.js listens on a port for local use; api/index.js exports this
// app as the single Vercel function.
import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import * as reports from './reports.js';
import * as paper from './paper.js';
import { storeKind } from './store.js';
import { ticket } from './today.js';

export const app = express();

// The UI is a separate static site (Render), so the browser calls this origin
// cross-site. Any origin by default; CORS_ORIGIN=https://a.com,https://b.com
// pins it down.
const origins = (process.env.CORS_ORIGIN || '').split(',').map((s) => s.trim()).filter(Boolean);
app.use(cors(origins.length ? { origin: origins } : {}));
app.use(express.json({ limit: '1mb' }));

const wrap = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    if (!err.status) console.error(err);
    res.status(err.status || 500).json({ error: err.message });
  }
};

const NOT_PUBLISHED_HINT = reports.SOURCE === 'mongo'
  ? 'publish the bundle: python3 tools/publish_mongo.py --src reports/top150 --bundle top150'
  : 'build the bundle: python3 tools/build_reports.py --src derived --out reports/latest';

const send = (res, data, name) => (data
  ? res.json(data)
  : res.status(503).json({
      error: `${name} not published yet`,
      hint: NOT_PUBLISHED_HINT,
      ...reports.status(),
    }));

// ---------------------------------------------------------------- reports
app.get('/api/health', async (_req, res) => {
  const base = { ...reports.status(), paper_store: storeKind() };
  try {
    const [s, m, published] = await Promise.all([
      reports.summary(), reports.manifest(), reports.publishedUtc()]);
    res.json({
      ok: true,
      ...base,
      bundle_present: Boolean(s),
      generated_utc: s?.generated_utc ?? null,
      published_utc: published,
      sections: m?.sections ?? null,
    });
  } catch (err) {
    res.status(503).json({ ok: false, ...base, error: err.message });
  }
});

app.get('/api/today', wrap(async (_req, res) => res.json(await ticket())));
app.get('/api/summary', wrap(async (_req, res) => send(res, await reports.summary(), 'summary')));
app.get('/api/equity', wrap(async (_req, res) => send(res, await reports.equity(), 'equity')));
app.get('/api/suggestions', wrap(async (_req, res) =>
  send(res, await reports.suggestions(), 'suggestions')));
app.get('/api/config', wrap(async (_req, res) => res.json(await reports.config())));
app.get('/api/trades/summary', wrap(async (_req, res) =>
  send(res, await reports.tradesSummary(), 'trades')));
app.get('/api/trades', wrap(async (req, res) => res.json(await reports.queryTrades(req.query))));

// ----------------------------------------------------------- paper book
app.get('/api/paper', wrap(async (_req, res) => res.json(await paper.state())));
app.post('/api/paper/open', wrap(async (req, res) => res.json(await paper.openPosition(req.body))));
app.post('/api/paper/:id/fill', wrap(async (req, res) =>
  res.json(await paper.recordFill(req.params.id, req.body))));
app.post('/api/paper/:id/close', wrap(async (req, res) =>
  res.json(await paper.closePosition(req.params.id, req.body))));
app.delete('/api/paper/:id', wrap(async (req, res) =>
  res.json(await paper.removePosition(req.params.id))));
app.post('/api/paper/settings', wrap(async (req, res) => res.json(await paper.settings(req.body))));
app.post('/api/paper/reset', wrap(async (_req, res) => res.json(await paper.reset())));

// ------------------------------------------- static frontend (monorepo, local)
// Only when a built UI sits next to this package; on Vercel it never does.
const dist = path.resolve(process.cwd(), '../frontend/dist');
export const servesFrontend = process.env.SERVE_FRONTEND !== '0' && fs.existsSync(dist);
if (servesFrontend) {
  app.use(express.static(dist));
  app.get('*', (_req, res) => res.sendFile(path.join(dist, 'index.html')));
}

app.use('/api', (_req, res) => res.status(404).json({ error: 'no such endpoint' }));
