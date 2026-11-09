/* "What was suggested, and what happened to it."
   Every row here is one barrier trade the book actually proposed in the
   walk-forward: entry at the next open after the signal, exit by the M5.2
   triple barrier (profit-take / stop / 20-session time exit). */
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api.js';
import { BarChart, LineChart, fmtNum, fmtPct, fmtInt, fmtSignedPct } from '../components/Chart.jsx';
import {
  Card, StatTile, Stats, Loading, ErrorBox, OutcomeBadge, Delta, Th, PageHeader, SearchInput,
  EmptyState,
} from '../components/Bits.jsx';
import Icon from '../components/Icon.jsx';

const EXIT_LABEL = { upper: 'Hit profit target', lower: 'Hit stop-loss', vertical: 'Time limit', trail: 'Trailing stop', flat: 'Flat exit', censored: 'Still open at end' };
const START = { exit: '', ticker: '', outcome: '', sortKey: '', sortDir: '', limit: 50, offset: 0 };

export default function Backtest() {
  const [d, setD] = useState({ loading: true });
  const [filters, setFilters] = useState(START);
  const [tickerInput, setTickerInput] = useState('');
  const [table, setTable] = useState(null);
  const [fetching, setFetching] = useState(false);
  const reqId = useRef(0);

  const load = () => Promise.all([api.tradesSummary(), api.config().catch(() => null)])
    .then(([s, cfg]) => setD({ s, cfg })).catch((error) => setD({ error }));
  useEffect(() => { load(); }, []);

  // Typing in the ticker box re-queries once the user pauses, not per key.
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.ticker === tickerInput
      ? f : { ...f, ticker: tickerInput, offset: 0 })), 250);
    return () => clearTimeout(t);
  }, [tickerInput]);

  // Only the newest response may land, so a slow early page can't overwrite a later one.
  useEffect(() => {
    reqId.current += 1;
    const id = reqId.current;
    setFetching(true);
    api.trades(filters)
      .then((r) => { if (id === reqId.current) setTable(r); })
      .catch(() => { if (id === reqId.current) setTable(null); })
      .finally(() => { if (id === reqId.current) setFetching(false); });
  }, [filters]);

  const conviction = useMemo(() => (d.s?.by_conviction_decile || []).map((r) => ({
    label: `D${r.decile}`, value: r.avg_ret, tipLabel: 'avg net return',
    tip: (<>
      <div className="t-row"><span>Win rate</span><span>{fmtPct(r.win_rate)}</span></div>
      <div className="t-row"><span>Trades</span><span>{fmtInt(r.n)}</span></div>
    </>),
  })), [d.s]);

  if (d.loading) return <Loading what="backtest trades" />;
  if (d.error) {
    return <ErrorBox error={d.error} onRetry={() => { setD({ loading: true }); load(); }}
                     hint={d.error.body?.hint || (
      <>The trade ledger comes from Stage 3. Run it on a pod, then publish:{' '}
        <code>scripts/launch_top150.sh stage3</code> →{' '}
        <code>FULL_MIRROR=1 mirror_top150.sh</code></>)} />;
  }

  const s = d.s;
  const hDays = d.cfg?.barrier?.h_days ?? 20;

  // The ledger is paginated on the server, so sorting is too — a header click
  // re-queries with sortKey/sortDir and jumps back to the first page.
  const ledgerSort = { key: filters.sortKey || null, dir: filters.sortDir || null };
  const onLedgerSort = (key) => setFilters((f) => (f.sortKey !== key
    ? { ...f, sortKey: key, sortDir: 'desc', offset: 0 }
    : f.sortDir === 'desc'
      ? { ...f, sortDir: 'asc', offset: 0 }
      : { ...f, sortKey: '', sortDir: '', offset: 0 }));
  const exitMix = (s.by_exit || []).map((r) => ({
    label: EXIT_LABEL[r.exit] || r.exit,
    value: r.n,
    tipLabel: 'trades',
    tip: (<>
      <div className="t-row"><span>Avg net return</span><span>{fmtSignedPct(r.avg_ret, 2)}</span></div>
      <div className="t-row"><span>Avg hold</span><span>{fmtNum(r.avg_hold, 1)} sessions</span></div>
    </>),
  }));

  const byYearWin = [{
    name: 'Win rate',
    color: 'var(--series-1)',
    points: (s.by_year || []).map((r) => ({ x: String(r.year), y: r.win_rate })),
  }];
  const byYearRet = (s.by_year || []).map((r) => ({
    label: String(r.year), value: r.avg_ret, tipLabel: 'avg net return',
    tip: <div className="t-row"><span>Trades</span><span>{fmtInt(r.n)}</span></div>,
  }));
  const dist = (s.return_distribution || []).map((b) => ({
    label: `${(b.lo * 100).toFixed(0)}%`,
    value: b.n,
    signedBy: b.lo + (b.hi - b.lo) / 2,
    tipLabel: 'trades',
  }));
  const holds = (s.by_holding_bucket || []).map((r) => ({
    label: r.bucket, value: r.avg_ret, tipLabel: 'avg net return',
    tip: (<>
      <div className="t-row"><span>Trades</span><span>{fmtInt(r.n)}</span></div>
      <div className="t-row"><span>Win rate</span><span>{fmtPct(r.win_rate)}</span></div>
    </>),
  }));

  const total = table?.total ?? 0;
  const from = total ? filters.offset + 1 : 0;
  const to = Math.min(filters.offset + filters.limit, total);
  const filtered = Boolean(filters.exit || filters.outcome || filters.ticker);

  return (
    <>
      <PageHeader eyebrow="Research · what happened" icon="history"
                  title="How the strategy did in testing"
                  lede="Every trade the strategy would have made, replayed through history with costs included. This is the evidence behind the daily suggestions." />

      <Stats label="Backtest totals">
        <StatTile label="Trades tested" value={fmtInt(s.n_trades)}
                  sub={`${s.date_range[0]} → ${s.date_range[1]}`} />
        <StatTile label="Made money" value={fmtPct(s.win_rate)}
                  sub="share of trades, after costs"
                  tone={s.win_rate == null ? '' : s.win_rate > 0.5 ? 'pos' : 'neg'} />
        <StatTile label="Avg profit per trade" value={fmtSignedPct(s.avg_ret, 2)}
                  sub={`typical trade ${fmtSignedPct(s.median_ret, 2)}`}
                  tone={s.avg_ret == null ? '' : s.avg_ret >= 0 ? 'pos' : 'neg'} />
        <StatTile label="Avg time held" value={`${fmtNum(s.avg_hold, 1)}`}
                  sub={`trading days (${hDays}-day limit)`} />
        <StatTile label="Sold at a profit target" value={fmtInt(s.total_pt)}
                  sub={`${fmtPct(s.total_pt / s.n_trades)} of trades`} tone="pos" />
        <StatTile label="Stopped out at a loss" value={fmtInt(s.total_stop)}
                  sub={`${fmtPct(s.total_stop / s.n_trades)} of trades`} tone="neg" />
      </Stats>

      <Card title="Did the model's favourites do better?"
            subtitle="Trades grouped by how strongly the model liked them (D1 = least, D10 = most) — among trades actually taken, which were already the model's top picks. A flat, noisy picture is normal here: the model earns its keep by choosing which stocks to buy at all, not by fine-ranking within its own shortlist."
            footer={(
              <div className="note" style={{ marginTop: 0 }}>
                Bars above the zero line are profitable on average (green, ▲ in the tooltip);
                below it, loss-making (red, ▼). Sign and position carry the meaning — the
                colour is only reinforcement.
              </div>
            )}>
        <BarChart data={conviction} height={250} bySign label="Average net return by conviction decile"
                  valueFormat={(v) => fmtSignedPct(v, 2)} />
      </Card>

      <div className="grid cols-2">
        <Card title="How trades ended"
              subtitle={`Every trade ends one of three ways: it hit its profit target, hit its stop-loss, or ran out of time (${hDays} trading days).`}>
          <BarChart data={exitMix} horizontal height={170} label="Trades by exit type"
                    valueFormat={(v) => fmtInt(v)} />
        </Card>
        <Card title="Profit by how long the trade lasted"
              subtitle="Very short trades struggle: you pay the trading costs twice either way, and a quick exit means the price barely moved.">
          <BarChart data={holds} height={210} bySign label="Average net return by holding length"
                    valueFormat={(v) => fmtSignedPct(v, 2)} />
        </Card>
      </div>

      <div className="grid cols-2">
        <Card title="Share of winning trades, year by year"
              subtitle="A healthy strategy of this kind wins about 52–55% of its trades — not 70%. It profits from a small edge repeated many times.">
          <LineChart series={byYearWin} height={220} zeroLine area={false}
                     label="Win rate by year" yFormat={(v) => fmtPct(v, 0)} xLabels={8} />
        </Card>
        <Card title="Average profit per trade, year by year">
          <BarChart data={byYearRet} height={220} bySign label="Average net return by year"
                    valueFormat={(v) => fmtSignedPct(v, 1)} labelEvery={2} />
        </Card>
      </div>

      <Card title="What a typical trade looks like"
            subtitle="How often trades ended with each size of profit or loss (capped at ±50%). Most land near break-even — many small outcomes, tilted slightly to the good side, is the whole game.">
        <BarChart data={dist} height={210} labelEvery={5} label="Distribution of trade returns"
                  color="var(--series-1)" valueFormat={(v) => fmtInt(v)} />
      </Card>

      <Card flush title="Every tested trade"
            subtitle={table?.note || 'Each row is one trade the strategy would have made, and how it turned out.'}>
        <div className="toolbar" role="search" aria-label="Filter trades">
          <label className="sr-only" htmlFor="bt-exit">How the trade ended</label>
          <select id="bt-exit" value={filters.exit}
                  onChange={(e) => setFilters({ ...filters, exit: e.target.value, offset: 0 })}>
            <option value="">However they ended</option>
            <option value="upper">Hit profit target</option>
            <option value="lower">Hit stop-loss</option>
            <option value="vertical">Time limit</option>
            <option value="trail">Trailing stop</option>
          </select>
          <label className="sr-only" htmlFor="bt-outcome">Wins or losses</label>
          <select id="bt-outcome" value={filters.outcome}
                  onChange={(e) => setFilters({ ...filters, outcome: e.target.value, offset: 0 })}>
            <option value="">Wins and losses</option>
            <option value="win">Winners only</option>
            <option value="loss">Losers only</option>
          </select>
          <SearchInput value={tickerInput} onChange={setTickerInput} />
          {filtered && (
            <button type="button" className="btn ghost sm"
                    onClick={() => { setTickerInput(''); setFilters({ ...START, sortKey: filters.sortKey, sortDir: filters.sortDir }); }}>
              <Icon name="x" size={14} />Clear
            </button>
          )}
          <div className="grow" />
          <div className="pager" aria-live="polite">
            <span>{table ? `${fmtInt(from)}–${fmtInt(to)} of ${fmtInt(total)} matching` : fetching ? 'Loading…' : ''}</span>
            <button type="button" className="btn sm icon" disabled={!filters.offset}
                    aria-label="Previous page"
                    onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - filters.limit) })}>
              <Icon name="chevronLeft" size={16} />
            </button>
            <button type="button" className="btn sm icon"
                    aria-label="Next page"
                    disabled={!table || filters.offset + filters.limit >= table.total}
                    onClick={() => setFilters({ ...filters, offset: filters.offset + filters.limit })}>
              <Icon name="chevronRight" size={16} />
            </button>
          </div>
        </div>
        <div className="table-wrap scroll" style={{ opacity: fetching ? 0.6 : 1, transition: 'opacity 0.15s' }}>
          <table className="sticky-first">
            <thead>
              <tr>
                <Th k="ticker" sort={ledgerSort} onSort={onLedgerSort}>Stock</Th>
                <Th k="entry_date" sort={ledgerSort} onSort={onLedgerSort}>Picked on</Th>
                <Th k="entry_price" num sort={ledgerSort} onSort={onLedgerSort}>Bought at</Th>
                <Th k="exit_date" sort={ledgerSort} onSort={onLedgerSort}>Sold on</Th>
                <Th k="exit_price" num sort={ledgerSort} onSort={onLedgerSort}>Sold at</Th>
                <Th k="barrier_hit" sort={ledgerSort} onSort={onLedgerSort}>How it ended</Th>
                <Th k="holding_days" num sort={ledgerSort} onSort={onLedgerSort}>Days held</Th>
                <Th k="ensemble_rank" num sort={ledgerSort} onSort={onLedgerSort}>Conviction</Th>
                <Th k="exit_ret_net" num sort={ledgerSort} onSort={onLedgerSort}>Profit / loss</Th>
              </tr>
            </thead>
            <tbody>
              {(table?.rows || []).map((r, i) => (
                <tr key={`${r.ticker}-${r.entry_date}-${i}`}>
                  <td><span className="ticker">{r.ticker}</span></td>
                  <td className="muted">{r.entry_date}</td>
                  <td className="n">{fmtNum(r.entry_price, 2)}</td>
                  <td className="muted">{r.exit_date}</td>
                  <td className="n">{fmtNum(r.exit_price, 2)}</td>
                  <td><OutcomeBadge hit={r.barrier_hit} /></td>
                  <td className="n">{r.holding_days}</td>
                  <td className="n">{fmtNum(r.ensemble_rank, 3)}</td>
                  <td className="n"><Delta value={r.exit_ret_net} /></td>
                </tr>
              ))}
              {!table?.rows?.length && !fetching && (
                <tr><td colSpan="9" className="empty-cell">
                  <EmptyState icon="search" title="No trades match these filters">
                    Try a different exit type or ticker, or clear the filters.
                  </EmptyState>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
