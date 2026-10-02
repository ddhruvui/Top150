/* One pot per stock (port.book: buckets). Every stock started with the same
   pot and keeps its own profit or loss; this page shows how each pot is
   doing and what the whole book has made since the pots were funded.
   Numbers are the model's own book at the configured pot size, priced at the
   last close — not the paper account, which is scaled to its own NAV. */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { LineChart, fmtNum, fmtInt, fmtSignedPct, arrow, signClass } from '../components/Chart.jsx';
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

export default function Pots() {
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
      <Card title="Pots">
        <div className="empty">The published book is not the per-stock pot book
          (port.book: buckets), so there are no pots to show.</div>
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
