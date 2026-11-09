/* The current target book: what the model proposes for the next open, with the
   M5.2 barrier levels each entry would carry, and a one-click push into the
   paper book (BP15). Signals are from the last close; fills happen at the NEXT
   open — the one-day lag is structural (G-02). */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { BarChart, fmtNum, fmtPct, fmtInt } from '../components/Chart.jsx';
import {
  Card, StatTile, Stats, Loading, ErrorBox, Badge, useSort, Th, PageHeader, Callout,
  SearchInput, EmptyState,
} from '../components/Bits.jsx';
import { useToast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';

const EMPTY = [];

/* A barrier is only a barrier if price can plausibly reach it inside the hold.
   thr = m·σ·√h with m=1.5, h=20 is ±6.7σ, so a name at ~13% daily vol prices a
   ±90% barrier — unreachable, i.e. the trade can only ever end at the vertical
   exit. That is a faithful consequence of the spec, not a bug, but it must not
   be presented as a working stop. */
export const WIDE_BARRIER_PCT = 40;

export default function Suggestions() {
  const [d, setD] = useState({ loading: true });
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(null);
  const [paperTickers, setPaperTickers] = useState(new Set());
  const toast = useToast();

  const refreshPaper = () => api.paper()
    .then((p) => setPaperTickers(new Set(
      p.positions.filter((x) => x.status !== 'closed').map((x) => x.ticker))))
    .catch(() => {});

  const load = () => api.suggestions().then((s) => setD({ s })).catch((error) => setD({ error }));
  useEffect(() => {
    load();
    refreshPaper();
  }, []);

  // long picks first, then the short sleeve (side -1) — every row states its side
  const rows = useMemo(() => {
    const all = [...(d.s?.buys_or_increases || []).map((r) => ({ side: 1, ...r })),
                 ...(d.s?.shorts_or_increases || []).map((r) => ({ side: -1, ...r }))];
    const t = q.trim().toUpperCase();
    return t ? all.filter((r) => r.ticker.toUpperCase().includes(t)) : all;
  }, [d.s, q]);
  const pickSort = useSort(rows);
  const exits = useMemo(() => [
    ...(d.s?.sells_or_exits || []).map((r) => ({ side: 1, ...r })),
    ...(d.s?.covers_or_exits || []).map((r) => ({ side: -1, ...r })),
  ], [d.s]);
  const exitSort = useSort(exits);

  if (d.loading) return <Loading what="suggestions" />;
  if (d.error) {
    return <ErrorBox error={d.error} onRetry={() => { setD({ loading: true }); load(); }}
                     hint={d.error.body?.hint || 'Run the predict job on a pod, then mirror + publish the bundle.'} />;
  }

  const s = d.s;
  const book = s.portfolio || {};
  const wideRows = (s.buys_or_increases || [])
    .filter((r) => Math.abs(r.stop_pct || 0) > WIDE_BARRIER_PCT);
  const wideCount = wideRows.length;
  const widest = wideRows.reduce((a, r) => Math.max(a, Math.abs(r.stop_pct || 0)), 0);
  const topWeights = (s.buys_or_increases || []).slice(0, 18).map((r) => ({
    label: r.ticker, value: r.target_weight, tipLabel: 'target weight',
    tip: <div className="t-row"><span>Conviction</span><span>{fmtNum(r.ensemble_rank, 3)}</span></div>,
  }));

  const addToPaper = async (r) => {
    setBusy(r.ticker);
    try {
      await api.paperOpen({
        ticker: r.ticker, side: r.side ?? 1, target_weight: r.target_weight,
        signal_date: s.as_of_close, ref_close: r.last_close,
        stop_pct: r.stop_pct, profit_take_pct: r.profit_take_pct,
        trail_pct: r.trail_pct ?? null,
        max_hold_sessions: r.max_hold_sessions, ensemble_rank: r.ensemble_rank,
      });
      toast({ ok: true, text: `${r.ticker} is now tracked in your practice book — it "${r.side < 0 ? 'sells short' : 'fills'}" at the next open.` });
      refreshPaper();
    } catch (err) {
      toast({ ok: false, text: `${r.ticker}: ${err.message}`, ttl: 8000 });
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Research · the raw picks" icon="list"
                  title="The model's full pick list"
                  lede={<>This is the raw output — every stock the model wants and how it splits the
                    money. For exact share counts and what to actually do at the open, use the{' '}
                    <a href="#today">Today page</a>; this page is for digging into the picks themselves.</>} />

      <Stats label="The book">
        <StatTile label="Picked after" value={s.as_of_close} sub="that day's market close" />
        <StatTile label="Stocks picked" value={fmtInt(book.n_names)}
                  sub="long — the model's top-decile names" />
        <StatTile label="Money invested" value={fmtPct(book.gross_long, 0)}
                  sub="of the pot, long (rest stays cash)" />
        <StatTile label="Stocks shorted" value={fmtInt(book.n_short_names ?? 0)}
                  sub="bottom-of-ranking names sold short" />
        <StatTile label="Money short" value={fmtPct(book.gross_short ?? 0, 0)}
                  sub="of the pot, in borrowed shares" />
      </Stats>

      <div className="callouts">
        <Callout tone="warning" quiet icon="shield" title="Practice money only">
          {s.disclaimer} Timing rule: {s.execute_at}
        </Callout>
        {wideCount > 0 && (
          <Callout tone="warning" title={`${wideCount} of ${(s.buys_or_increases || []).length} picks have sell triggers wider than ±${WIDE_BARRIER_PCT}% (widest ±${fmtNum(widest, 0)}%)`}>
            Trigger width scales with how jumpy a stock is, and for the jumpiest names it
            lands further than the price could plausibly move before the time limit — so
            their stop and profit-take will never fire, and those positions simply get
            sold at the time limit. Don't count on those triggers as protection.
          </Callout>
        )}
      </div>

      <Card title="Biggest slices of the pot"
            subtitle="How the money is split. Steadier stocks get bigger slices; jumpier ones get smaller slices, and no single stock may exceed the cap.">
        <BarChart data={topWeights} horizontal height={Math.max(200, topWeights.length * 26 + 40)}
                  label="Target weight by stock" valueFormat={(v) => fmtPct(v, 2)} />
      </Card>

      <Card flush title="Every pick" count={rows.length}
            subtitle={`Stop and profit-take are % moves from the price you actually pay at the open; the time limit is ${s.exit_rules?.h_sessions} trading days. Conviction is the model's score — higher means it likes the stock more.`}
            right={<SearchInput value={q} onChange={setQ} />}>
        <div className="table-wrap scroll">
          <table className="sticky-first">
            <thead>
              <tr>
                <Th k="ticker" sort={pickSort.sort} onSort={pickSort.onSort}>Stock</Th>
                <Th>Action</Th>
                <Th k="target_weight" num sort={pickSort.sort} onSort={pickSort.onSort}>Slice of pot</Th>
                <Th k="ensemble_rank" num sort={pickSort.sort} onSort={pickSort.onSort}>Conviction</Th>
                <Th k="last_close" num sort={pickSort.sort} onSort={pickSort.onSort}>Latest close</Th>
                <Th k="stop_pct" num sort={pickSort.sort} onSort={pickSort.onSort}>Stop</Th>
                <Th k="profit_take_pct" num sort={pickSort.sort} onSort={pickSort.onSort}>Profit-take</Th>
                <Th k="max_hold_sessions" num sort={pickSort.sort} onSort={pickSort.onSort}>Time limit</Th>
                <Th><span className="sr-only">Actions</span></Th>
              </tr>
            </thead>
            <tbody>
              {pickSort.rows.map((r) => {
                const inPaper = paperTickers.has(r.ticker);
                return (
                  <tr key={`${r.side}-${r.ticker}`}>
                    <td><span className="ticker">{r.ticker}</span></td>
                    <td>{r.side < 0 ? <Badge kind="fail" glyph="▼">Sell short</Badge>
                      : <Badge kind="pass">Buy / add</Badge>}</td>
                    <td className="n">{fmtPct(r.target_weight, 2)}</td>
                    <td className="n">{fmtNum(r.ensemble_rank, 3)}</td>
                    <td className="n">{fmtNum(r.last_close, 2)}</td>
                    <td className="n neg">{r.stop_pct > 0 ? '+' : ''}{fmtNum(r.stop_pct, 2)}%</td>
                    <td className="n pos">{r.profit_take_pct >= 0 ? '+' : ''}{fmtNum(r.profit_take_pct, 2)}%</td>
                    <td className="n">
                      {Math.abs(r.stop_pct) > WIDE_BARRIER_PCT
                        ? <span title={`The ±${fmtNum(Math.abs(r.stop_pct), 0)}% triggers are `
                            + 'further than this stock could plausibly move in time, so the '
                            + 'only realistic exit is selling when the time limit is reached.'}>
                            <Badge kind="warn">⏱ {r.max_hold_sessions} days — only exit</Badge>
                          </span>
                        : `${r.max_hold_sessions} days`}
                    </td>
                    <td className="n">
                      {inPaper ? (
                        <span className="btn sm done" aria-disabled="true">
                          <Icon name="check" size={14} />Already tracked
                        </span>
                      ) : (
                        <button type="button" className="btn sm" disabled={busy === r.ticker}
                                onClick={() => addToPaper(r)}
                                aria-label={`Track ${r.ticker} in the practice book`}>
                          {busy === r.ticker ? 'Adding…' : <><Icon name="plus" size={14} />Track this trade</>}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!rows.length && (
                <tr><td colSpan="9" className="empty-cell">
                  <EmptyState icon="search" title="No matches">
                    No pick matches “{q}”.
                  </EmptyState>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {exits.length > 0 && (
        <Card flush title="Get out of these" count={exits.length}
              subtitle="Positions the model held before and no longer wants — sell the longs, buy back the shorts.">
          <div className="table-wrap">
            <table>
              <thead><tr>
                <Th k="ticker" sort={exitSort.sort} onSort={exitSort.onSort}>Stock</Th>
                <Th>Action</Th>
                <Th k="last_close" num sort={exitSort.sort} onSort={exitSort.onSort}>Latest close</Th>
                <Th k="current_weight" num sort={exitSort.sort} onSort={exitSort.onSort}>Slice held</Th>
              </tr></thead>
              <tbody>
                {exitSort.rows.map((r) => (
                  <tr key={`${r.side}-${r.ticker}`}>
                    <td><span className="ticker">{r.ticker}</span></td>
                    <td>{r.side < 0 ? <Badge kind="pass" glyph="▲">Buy back</Badge>
                      : <Badge kind="fail">Sell</Badge>}</td>
                    <td className="n">{r.last_close != null ? fmtNum(r.last_close, 2) : '—'}</td>
                    <td className="n">{fmtPct(r.current_weight, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
