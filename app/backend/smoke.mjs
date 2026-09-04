// Post-deploy check — hits every read endpoint and reports status + latency.
//   node smoke.mjs                          # local API on :8787
//   node smoke.mjs https://<app>.vercel.app # the deployment
const base = (process.argv[2] || 'http://localhost:8787').replace(/\/$/, '');
const paths = ['/api/health', '/api/summary', '/api/equity', '/api/suggestions',
  '/api/config', '/api/trades/summary', '/api/trades?limit=2&sortKey=exit_ret_net',
  '/api/today', '/api/paper'];

let failed = 0;
for (const p of paths) {
  const t0 = Date.now();
  try {
    const r = await fetch(base + p);
    const body = await r.json().catch(() => ({}));
    const ms = Date.now() - t0;
    let detail = '';
    if (p === '/api/health') detail = `source=${body.source} bundle=${body.bundle} published=${body.published_utc ?? '-'}`;
    if (p === '/api/summary') detail = `verdict=${body.gates?.verdict}`;
    if (p === '/api/suggestions') detail = `as_of=${body.as_of_close} n=${body.buys_or_increases?.length}`;
    if (p.startsWith('/api/trades?')) detail = `total=${body.total} of ${body.n_ledger}`;
    if (p === '/api/today') detail = `next_open=${body.session?.next_open} buy=${body.counts?.buy}`;
    if (p === '/api/paper') detail = `positions=${body.positions?.length}`;
    if (!r.ok) { failed += 1; detail = `${body.error || ''} ${body.hint || ''}`.trim(); }
    console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.status} ${p.padEnd(44)} ${String(ms).padStart(5)}ms  ${detail}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL ---- ${p.padEnd(44)}        ${err.message}`);
  }
}
console.log(failed ? `${failed} endpoint(s) failed` : 'all endpoints ok');
process.exit(failed ? 1 : 0);
