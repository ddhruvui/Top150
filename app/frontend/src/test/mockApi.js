/* Test double for src/api.js, fed by fixtures captured from a real API run
   (reports/top150 bundle + a one-position paper book). Every call returns a
   fresh deep copy so a test can't leak mutations into the next. */
import { vi } from 'vitest';
import health from './fixtures/health.json';
import today from './fixtures/today.json';
import summary from './fixtures/summary.json';
import equity from './fixtures/equity.json';
import suggestions from './fixtures/suggestions.json';
import potsHistory from './fixtures/pots_history.json';
import config from './fixtures/config.json';
import tradesSummary from './fixtures/trades_summary.json';
import trades from './fixtures/trades.json';
import paper from './fixtures/paper.json';

export const fixtures = {
  health, today, summary, equity, suggestions, potsHistory, config, tradesSummary, trades, paper,
};

export const clone = (x) => JSON.parse(JSON.stringify(x));

/** Point every api method at a fixture; `over` replaces any of them with a
 *  value (resolved), an Error (rejected) or a function (used as-is). */
export function mockApi(api, over = {}) {
  const ok = (v) => vi.fn(() => Promise.resolve(clone(v)));
  const base = {
    health: ok(health),
    today: ok(today),
    summary: ok(summary),
    equity: ok(equity),
    suggestions: ok(suggestions),
    potsHistory: ok(potsHistory),
    config: ok(config),
    tradesSummary: ok(tradesSummary),
    trades: ok(trades),
    paper: ok(paper),
    paperOpen: vi.fn(() => Promise.resolve({ ok: true })),
    paperFill: vi.fn(() => Promise.resolve({ ok: true })),
    paperClose: vi.fn(() => Promise.resolve({ ok: true })),
    paperRemove: vi.fn(() => Promise.resolve({ ok: true })),
    paperSettings: vi.fn(() => Promise.resolve({ ok: true })),
  };
  for (const [k, v] of Object.entries(over)) {
    if (typeof v === 'function') base[k] = vi.fn(v);
    else if (v instanceof Error) base[k] = vi.fn(() => Promise.reject(v));
    else base[k] = ok(v);
  }
  Object.assign(api, base);
  return api;
}
