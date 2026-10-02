/* One pot per stock (port.book: buckets). Every stock started with the same
   pot and keeps its own profit or loss; this page shows how each pot is
   doing and what the whole book has made since the pots were funded.
   Numbers are the model's own book at the configured pot size, priced at the
   last close — not the paper account, which is scaled to its own NAV. */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { LineChart, BarChart, fmtNum, fmtInt, fmtPct, fmtSignedPct, arrow, signClass } from '../components/Chart.jsx';
import { Card, StatTile, Loading, ErrorBox, Badge, Delta, useSort, Th } from '../components/Bits.jsx';

const EMPTY = [];
const money = (v) => (v == null || Number.isNaN(v) ? '—'
  : `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
const signedMoney = (v) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${money(Math.abs(v))}`);

const STATUS = {
  holding: ['pass', '●', 'Holding'],
  due_exit: ['neutral', '⏱', 'Sells at next open'],
  entering: ['pass', '▲', 'Buys at next open'],
  flat: ['neutral', '○', 'Waiting in cash'],
};

function Live() {
  const [d, setD] = useState({ loading: true });
  const [q, setQ] = useState('');
  const [show, setShow] = useState('all');

  useEffect(() => {
    api.suggestions().then((s) => setD({ s })).catch((error) => setD({ error }));
  }, []);

  const pots = d.s?.buckets ?? EMPTY;
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return pots.filter((r) => (!t || r.ticker.toUpperCase().includes(t))
      && (show === 'all' || (show === 'invested' ? ['holding', 'due_exit'].includes(r.status)
        : show === 'up' ? r.pnl > 0 : show === 'down' ? r.pnl < 0 : true)));
  }, [pots, q, show]);
  const sort = useSort(rows);

  if (d.loading) return <Loading what="pots" />;
  if (d.error) return <ErrorBox error={d.error} />;
  if (!pots.length) {
    return (
      <Card title="Live pots">
        <div className="empty">The published book is not the per-stock pot book
          (port.book: buckets), so there are no live pots to show.</div>
      </Card>
    );
  }

  const P = d.s.bucket_performance || {};
  const start = d.s.book_engine?.bucket_start;
  const unit = d.s.book_engine?.unit;
  const curve = (P.curve || []).length > 1 ? [{
    name: 'Whole book', color: 'var(--series-1)',
    points: P.curve.map((p) => ({ x: p.date, y: p.value / P.start_value - 1 })),
  }] : null;
  const holding = pots.filter((r) => ['holding', 'due_exit'].includes(r.status)).length;

  return (
    <>
      <Card title="How every pot is doing"
            subtitle={`Each stock started with ${money(unit)} on the ${start} close and keeps its own
              profit or loss. Values are at the ${d.s.as_of_close} close.`}>
        <div className="tiles">
          <StatTile label="Total profit / loss" value={fmtSignedPct(P.pnl_pct, 2)}
                    sub={`${signedMoney(P.pnl)} on ${money(P.start_value)}`}
                    tone={P.pnl > 0 ? 'pos' : P.pnl < 0 ? 'neg' : ''} />
          <StatTile label="Book value" value={money(P.value)}
                    sub={`${fmtInt(pots.length)} pots`} />
          <StatTile label="Pots up / down" value={`${fmtInt(P.winners)} / ${fmtInt(P.losers)}`}
                    sub="above / below their starting value" />
          <StatTile label="In a stock now" value={fmtInt(holding)}
                    sub={`${money(P.invested)} invested; the rest waits in cash`} />
          <StatTile label="Trades closed" value={fmtInt(P.trades_closed)}
                    sub={`${signedMoney(P.realized_pnl)} booked`} />
        </div>
      </Card>

      {curve && (
        <Card title="Whole book since the start" subtitle="Total profit or loss of all pots together, per close">
          <LineChart series={curve} height={220} zeroLine yFormat={(v) => fmtSignedPct(v, 1)} />
        </Card>
      )}

      <Card title="Every pot"
            right={(
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={show} onChange={(e) => setShow(e.target.value)}>
                  <option value="all">All pots</option>
                  <option value="invested">In a stock</option>
                  <option value="up">Up</option>
                  <option value="down">Down</option>
                </select>
                <input placeholder="Filter ticker…" value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
            )}>
        <div className="table-wrap" style={{ maxHeight: 720, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <Th k="ticker" sort={sort.sort} onSort={sort.onSort}>Stock</Th>
                <Th k="status" sort={sort.sort} onSort={sort.onSort}>Now</Th>
                <Th k="pot_value" num sort={sort.sort} onSort={sort.onSort}>Pot value</Th>
                <Th k="pnl" num sort={sort.sort} onSort={sort.onSort}>Profit / loss</Th>
                <Th k="pnl_pct" num sort={sort.sort} onSort={sort.onSort}>Since start</Th>
                <Th k="open_ret_pct" num sort={sort.sort} onSort={sort.onSort}>Open trade</Th>
                <Th k="open_fill_price" num sort={sort.sort} onSort={sort.onSort}>Bought at</Th>
                <Th k="last_close" num sort={sort.sort} onSort={sort.onSort}>Last close</Th>
                <Th k="trades_closed" num sort={sort.sort} onSort={sort.onSort}>Trades (won)</Th>
              </tr>
            </thead>
            <tbody>
              {sort.rows.map((r) => {
                const [kind, glyph, label] = STATUS[r.status] || ['neutral', '•', r.status];
                return (
                  <tr key={r.ticker}>
                    <td><strong>{r.ticker}</strong></td>
                    <td>
                      <Badge kind={kind} glyph={glyph}>{label}</Badge>
                      {r.status === 'entering' && r.entering === 'fallback' && (
                        <span className="muted small"> (cycle catch-up)</span>
                      )}
                    </td>
                    <td className="n">{money(r.pot_value)}</td>
                    <td className="n">
                      <span className={`${signClass(r.pnl)} num`}>
                        <span aria-hidden="true">{arrow(r.pnl)}</span> {signedMoney(r.pnl)}
                      </span>
                    </td>
                    <td className="n"><Delta value={r.pnl_pct} /></td>
                    <td className="n">{r.open_ret_pct == null
                      ? <span className="muted">—</span> : <Delta value={r.open_ret_pct} />}</td>
                    <td className="n">{r.open_fill_price == null ? '—' : fmtNum(r.open_fill_price, 2)}</td>
                    <td className="n">{fmtNum(r.last_close, 2)}</td>
                    <td className="n">{fmtInt(r.trades_closed)} ({fmtInt(r.wins)})</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small" style={{ marginTop: 8 }}>
          “Open trade” is the gain on the shares a pot holds now, from its fill to the last close.
          “Since start” counts everything the pot has made or lost, closed trades included,
          after costs.
        </p>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------ backtest */

const Money = ({ v }) => (
  <span className={`${signClass(v)} num`}>
    <span aria-hidden="true">{arrow(v)}</span> {signedMoney(v)}
  </span>
);

function Backtest() {
  const [d, setD] = useState({ loading: true });
  const [q, setQ] = useState('');
  const [show, setShow] = useState('all');
  const [pick, setPick] = useState(null);

  useEffect(() => {
    api.potsHistory().then((h) => setD({ h })).catch((error) => setD({ error }));
  }, []);
  useEffect(() => {
    if (pick) document.getElementById('pot-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [pick]);

  const stocks = d.h?.stocks ?? EMPTY;
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return stocks.filter((r) => (!t || r.ticker.toUpperCase().includes(t))
      && (show === 'all' || (show === 'up' ? r.pnl > 0 : r.pnl < 0)));
  }, [stocks, q, show]);
  const sort = useSort(rows);

  if (d.loading) return <Loading what="backtest pots" />;
  if (d.error) {
    return <ErrorBox error={d.error}
                     hint="The pot history is built from the stage 3 bucket backtest; publish a fresh report bundle." />;
  }
  const H = d.h;
  const T = H.total;
  const bookSeries = [
    { name: 'All pots together', color: 'var(--series-1)',
      points: H.book.map((p) => ({ x: p.date, y: p.value })) },
    { name: 'Money put in', color: 'var(--series-2, #999)',
      points: H.book.map((p) => ({ x: p.date, y: p.deposited })) },
  ];
  const years = Object.entries(T.by_year || {}).map(([y, v]) => ({
    label: y, value: v, tipLabel: 'whole book' }));
  const sel = pick ? stocks.find((x) => x.ticker === pick) : null;

  return (
    <>
      <Card title={`How every pot did, ${H.start.slice(0, 4)}–today (backtest)`}
            subtitle={`Each stock started with ${money(stocks[0]?.start_value)} at its first trade and
              kept its own profit or loss, after costs, through ${H.end}.`}>
        <div className="tiles">
          <StatTile label="Total profit / loss" value={fmtSignedPct(T.pnl_pct, 0)}
                    sub={`${signedMoney(T.pnl)} on ${money(T.start_value)}`}
                    tone={T.pnl >= 0 ? 'pos' : 'neg'} />
          <StatTile label="All pots now" value={money(T.end_value)}
                    sub={`${fmtInt(T.stocks)} pots`} />
          <StatTile label="Pots up / down" value={`${fmtInt(T.up)} / ${fmtInt(T.down)}`}
                    sub="ended above / below their start" />
          <StatTile label="Trades" value={fmtInt(T.trades)} sub="closed, all pots" />
        </div>
        <p className="muted small" style={{ marginTop: 8 }}>{H.note}</p>
      </Card>

      <Card title="All pots together" subtitle="Total value of every pot at each month end, and the money put in">
        <LineChart series={bookSeries} height={240} logY
                   yFormat={(v) => money(v)} />
      </Card>

      {years.length > 0 && (
        <Card title="Each year" subtitle="Profit or loss of the whole book per calendar year">
          <BarChart data={years} height={220} bySign valueFormat={(v) => fmtSignedPct(v, 1)} />
        </Card>
      )}

      {sel && (
        <div id="pot-detail" style={{ scrollMarginTop: 80 }}>
        <Card title={`${sel.ticker}: ${money(sel.start_value)} → ${money(sel.end_value)} (${fmtSignedPct(sel.pnl_pct, 0)})`}
              subtitle={`Pot value after every trade since ${sel.first_trade}; ${sel.trades} trades, `
                + `${fmtPct(sel.win_rate, 0)} won`}
              right={<button className="btn sm" onClick={() => setPick(null)}>Close</button>}>
          <LineChart series={[{ name: sel.ticker, color: 'var(--series-1)',
                                points: (H.paths[sel.ticker] || []).map(([x, y]) => ({ x, y })) }]}
                     height={220} yFormat={(v) => money(v)} />
          <BarChart data={Object.entries(sel.by_year).map(([y, v]) => ({
                      label: y, value: v, tipLabel: sel.ticker }))}
                    height={180} bySign valueFormat={(v) => fmtSignedPct(v, 1)} />
        </Card>
        </div>
      )}

      <Card title="Every stock"
            subtitle="Click a stock to see its pot over time"
            right={(
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={show} onChange={(e) => setShow(e.target.value)}>
                  <option value="all">All stocks</option>
                  <option value="up">Made money</option>
                  <option value="down">Lost money</option>
                </select>
                <input placeholder="Filter ticker…" value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
            )}>
        <div className="table-wrap" style={{ maxHeight: 720, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <Th k="ticker" sort={sort.sort} onSort={sort.onSort}>Stock</Th>
                <Th k="end_value" num sort={sort.sort} onSort={sort.onSort}>Pot now</Th>
                <Th k="pnl" num sort={sort.sort} onSort={sort.onSort}>Profit / loss</Th>
                <Th k="pnl_pct" num sort={sort.sort} onSort={sort.onSort}>Total</Th>
                <Th k="cagr" num sort={sort.sort} onSort={sort.onSort}>Per year</Th>
                <Th k="last_1y" num sort={sort.sort} onSort={sort.onSort}>Last 12 mo</Th>
                <Th k="last_3y" num sort={sort.sort} onSort={sort.onSort}>Last 3 yrs</Th>
                <Th k="trades" num sort={sort.sort} onSort={sort.onSort}>Trades</Th>
                <Th k="win_rate" num sort={sort.sort} onSort={sort.onSort}>Won</Th>
                <Th k="avg_trade" num sort={sort.sort} onSort={sort.onSort}>Avg trade</Th>
                <Th k="best_trade" num sort={sort.sort} onSort={sort.onSort}>Best</Th>
                <Th k="worst_trade" num sort={sort.sort} onSort={sort.onSort}>Worst</Th>
                <Th k="first_trade" sort={sort.sort} onSort={sort.onSort}>Since</Th>
              </tr>
            </thead>
            <tbody>
              {sort.rows.map((r) => (
                <tr key={r.ticker} onClick={() => setPick(r.ticker)}
                    style={{ cursor: 'pointer' }}
                    aria-selected={pick === r.ticker}>
                  <td><strong>{r.ticker}</strong></td>
                  <td className="n">{money(r.end_value)}</td>
                  <td className="n"><Money v={r.pnl} /></td>
                  <td className="n"><Delta value={r.pnl_pct} digits={0} /></td>
                  <td className="n"><Delta value={r.cagr} digits={1} /></td>
                  <td className="n"><Delta value={r.last_1y} digits={1} /></td>
                  <td className="n"><Delta value={r.last_3y} digits={1} /></td>
                  <td className="n">{fmtInt(r.trades)}</td>
                  <td className="n">{fmtPct(r.win_rate, 0)}</td>
                  <td className="n"><Delta value={r.avg_trade} digits={1} /></td>
                  <td className="n"><Delta value={r.best_trade} digits={0} /></td>
                  <td className="n"><Delta value={r.worst_trade} digits={0} /></td>
                  <td>{r.first_trade}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

export default function Pots() {
  const [view, setView] = useState('backtest');
  return (
    <>
      <div className="nav" role="tablist" style={{ marginBottom: 12 }}>
        {[['backtest', 'Backtest: 2007–today'], ['live', 'Live: since the pots started']]
          .map(([id, label]) => (
            <button key={id} role="tab" aria-selected={view === id}
                    aria-current={view === id ? 'page' : undefined}
                    onClick={() => setView(id)}>{label}</button>
          ))}
      </div>
      {view === 'backtest' ? <Backtest /> : <Live />}
    </>
  );
}
