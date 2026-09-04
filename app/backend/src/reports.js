// Report bundle access — MongoDB in production, JSON files for local and
// monorepo use. Either way this layer only reads and slices what
// tools/build_reports.py produced (and tools/publish_mongo.py published): no
// metric is recomputed here, so the API can never disagree with the pipeline.
//
// Mongo layout (database MONGO_DB, default Top150):
//   reports      { _id: "<bundle>/<section>", bundle, section, data, built_utc, published_utc }
//   trades       one document per backtest trade: { bundle, version, seq, ...row }
//                (the `trades_sample` report document carries the live `version`)
//   predictions  { _id: "<bundle>/<as_of_close>", ... } — every published book, by date
//   paper_books  { _id: "<bundle>", ...paper book state }   (see store.js)
import fs from 'node:fs';
import path from 'node:path';
import { BUNDLE, DB_NAME, hasMongo, col } from './db.js';

const TTL_MS = Number(process.env.REPORTS_CACHE_MS ?? 30_000);

// ---------------------------------------------------------------- source
// An explicit REPORTS_DIR always means files (scripts/serve_top150_console.sh
// relies on that). Otherwise Mongo when configured, else the monorepo's
// reports/ tree: reports/<bundle> if it exists, reports/latest if not.
function defaultReportsDir() {
  const base = path.resolve(process.cwd(), '../../reports');
  for (const d of [path.join(base, BUNDLE), path.join(base, 'latest')]) {
    if (fs.existsSync(path.join(d, 'suggestions.json'))) return d;
  }
  return path.join(base, 'latest');
}

const REPORTS_DIR = process.env.REPORTS_DIR || (hasMongo() ? null : defaultReportsDir());
export const SOURCE = REPORTS_DIR ? 'file' : 'mongo';

export const status = () => ({
  source: SOURCE,
  bundle: BUNDLE,
  ...(SOURCE === 'file' ? { reports_dir: REPORTS_DIR } : { db: DB_NAME }),
});

// ------------------------------------------------------------ file source
const fileCache = new Map();

function readJsonFile(name) {
  const file = path.join(REPORTS_DIR, `${name}.json`);
  let stat;
  try {
    stat = fs.statSync(file);
  } catch {
    return null;
  }
  const hit = fileCache.get(name);
  if (hit && hit.mtimeMs === stat.mtimeMs) return hit.data;
  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    fileCache.set(name, { mtimeMs: stat.mtimeMs, data });
    return data;
  } catch (err) {
    console.error(`reports: cannot parse ${name}.json:`, err.message);
    return null;
  }
}

// ----------------------------------------------------------- mongo source
// Sections are small (the equity curve is the largest at ~140 KB); a short
// TTL cache keeps a warm serverless instance from re-reading them per request
// while still picking up a fresh publish within seconds.
const mongoCache = new Map();

async function readMongoSection(name) {
  const hit = mongoCache.get(name);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.doc;
  const doc = await col('reports').findOne({ _id: `${BUNDLE}/${name}` });
  mongoCache.set(name, { at: Date.now(), doc });
  return doc;
}

async function section(name) {
  if (SOURCE === 'file') return readJsonFile(name);
  return (await readMongoSection(name))?.data ?? null;
}

/** When a section was last published to Mongo — null for the file source. */
export async function publishedUtc(name = 'summary') {
  if (SOURCE === 'file') return null;
  return (await readMongoSection(name))?.published_utc ?? null;
}

export const summary = () => section('summary');
export const equity = () => section('equity');
export const suggestions = () => section('suggestions');
export const tradesSummary = () => section('trades_summary');
export const manifest = () => section('manifest');
export const readCalendar = () => section('calendar');

const DEFAULT_CONFIG = {
  cost: { per_trade_bps: 15, borrow_gc_bps_yr: 50, slippage_bps: 0 },
  barrier: { m: 1.5, h_days: 20 },
  pdt: { limit: 3, window_business_days: 5, equity_floor: 25000 },
  ops: { max_daily_loss_pct: 0.02 },
  slippage_adoption_min_fills: 60,
  decay: { window_sessions: 63, breach_sessions: 126, ratio_of_backtest: 0.5 },
};

export async function config() {
  return (await section('config')) || DEFAULT_CONFIG;
}

// ------------------------------------------------------------------ trades
const SORTABLE_TRADE_KEYS = new Set(['ticker', 'entry_date', 'exit_date',
  'entry_price', 'exit_price', 'barrier_hit', 'holding_days', 'ensemble_rank',
  'exit_ret_net']);

const escapeRe = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function parseQuery({ limit = 100, offset = 0, exit, ticker, year, minRank,
                      outcome, sortKey, sortDir } = {}) {
  return {
    limit: Math.min(Math.max(Number(limit) || 100, 1), 1000),
    offset: Math.max(Number(offset) || 0, 0),
    exit: exit || null,
    ticker: ticker ? String(ticker).toUpperCase() : null,
    year: year ? String(year) : null,
    minRank: minRank != null && minRank !== '' ? Number(minRank) : null,
    outcome: outcome === 'win' || outcome === 'loss' ? outcome : null,
    sortKey: sortKey && SORTABLE_TRADE_KEYS.has(sortKey) ? sortKey : null,
    sortDir: sortDir === 'asc' ? 1 : -1,
  };
}

/** File source: filter + sort + paginate the in-memory sample. */
function queryTradesFile(q) {
  const bundle = readJsonFile('trades_sample');
  if (!bundle) return { rows: [], total: 0, n_ledger: 0 };
  let rows = bundle.rows;
  if (q.exit) rows = rows.filter((r) => r.barrier_hit === q.exit);
  if (q.ticker) rows = rows.filter((r) => String(r.ticker).toUpperCase().includes(q.ticker));
  if (q.year) rows = rows.filter((r) => String(r.entry_date).startsWith(q.year));
  if (q.minRank != null) {
    rows = rows.filter((r) => r.ensemble_rank != null && r.ensemble_rank >= q.minRank);
  }
  if (q.outcome === 'win') rows = rows.filter((r) => r.exit_ret_net > 0);
  if (q.outcome === 'loss') rows = rows.filter((r) => r.exit_ret_net <= 0);
  if (q.sortKey) {
    rows = [...rows].sort((x, y) => {
      const a = x[q.sortKey];
      const b = y[q.sortKey];
      if (a == null && b == null) return 0;
      if (a == null) return 1;          // nulls last regardless of direction
      if (b == null) return -1;
      const c = typeof a === 'number' && typeof b === 'number'
        ? a - b : String(a).localeCompare(String(b));
      return q.sortDir * c;
    });
  }
  const total = rows.length;
  return { rows: rows.slice(q.offset, q.offset + q.limit), total,
           n_ledger: bundle.n_total, note: bundle.note };
}

/** Mongo source: the same query pushed down to the `trades` collection. Only
 *  rows of the version named by the live `trades_sample` document count, so a
 *  publish in progress (new rows in, old rows not yet deleted) is invisible. */
async function queryTradesMongo(q) {
  const meta = await section('trades_sample');
  if (!meta) return { rows: [], total: 0, n_ledger: 0 };
  const match = { bundle: BUNDLE, version: meta.version };
  if (q.exit) match.barrier_hit = q.exit;
  if (q.ticker) match.ticker = { $regex: escapeRe(q.ticker), $options: 'i' };
  if (q.year) match.entry_date = { $regex: `^${escapeRe(q.year)}` };
  if (q.minRank != null) match.ensemble_rank = { $gte: q.minRank };
  if (q.outcome === 'win') match.exit_ret_net = { $gt: 0 };
  if (q.outcome === 'loss') match.exit_ret_net = { $lte: 0 };

  const pipeline = [{ $match: match }];
  if (q.sortKey) {
    // nulls last regardless of direction — same contract as the file path
    pipeline.push(
      { $addFields: { _nul: { $eq: [{ $ifNull: [`$${q.sortKey}`, null] }, null] } } },
      { $sort: { _nul: 1, [q.sortKey]: q.sortDir, seq: 1 } });
  } else {
    pipeline.push({ $sort: { seq: 1 } });
  }
  pipeline.push({ $skip: q.offset }, { $limit: q.limit },
                { $project: { _id: 0, _nul: 0, bundle: 0, version: 0, seq: 0 } });
  const [rows, total] = await Promise.all([
    col('trades').aggregate(pipeline).toArray(),
    col('trades').countDocuments(match),
  ]);
  return { rows, total, n_ledger: meta.n_total, note: meta.note };
}

export async function queryTrades(query = {}) {
  const q = parseQuery(query);
  return SOURCE === 'file' ? queryTradesFile(q) : queryTradesMongo(q);
}
