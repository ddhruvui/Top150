/* Paper-trading console — the BP15 stage the blueprint requires before real
   capital ("paper-trade 3–6 months measuring open-print slippage"), with the
   M18 ops instruments: slippage measurement, PDT budget, kill switch, and the
   G-11 decay monitor. */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { LineChart, fmtNum, fmtPct, fmtInt, fmtSignedPct } from '../components/Chart.jsx';
import {
  Card, StatTile, Stats, Badge, Delta, Loading, ErrorBox, useSort, Th, PageHeader,
  ConfirmButton, EmptyState,
} from '../components/Bits.jsx';
import { useToast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';

const EMPTY = [];
const isPrice = (v) => v !== '' && Number.isFinite(Number(v)) && Number(v) > 0;

export function FillForm({ pos, onDone }) {
  const [fill, setFill] = useState('');
  const [open, setOpen] = useState('');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    if (!isPrice(fill)) { setErr('Enter the price you paid'); return; }
    setBusy(true);
    try {
      await api.paperFill(pos.id, {
        fill_price: Number(fill),
        official_open: open === '' ? null : Number(open),
      });
      toast({ ok: true, text: `${pos.ticker}: fill recorded at ${Number(fill).toFixed(2)}.` });
      onDone();
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };
  return (
    <form className="inline-form" onSubmit={submit} noValidate>
      <label className="sr-only" htmlFor={`fill-${pos.id}`}>Price you paid for {pos.ticker}</label>
      <input id={`fill-${pos.id}`} className="input-sm" inputMode="decimal" placeholder="price you paid"
             value={fill} onChange={(e) => { setFill(e.target.value); setErr(null); }}
             aria-invalid={Boolean(err)} />
      <label className="sr-only" htmlFor={`open-${pos.id}`}>Official open for {pos.ticker}</label>
      <input id={`open-${pos.id}`} className="input-sm" inputMode="decimal" placeholder="official open"
             value={open} onChange={(e) => setOpen(e.target.value)} />
      <button type="submit" className="btn sm primary" disabled={!fill || busy}>
        {busy ? 'Saving…' : 'Record it'}
      </button>
      {err && <span className="neg inline-msg" role="alert">✕ {err}</span>}
    </form>
  );
}

export function CloseForm({ pos, onDone }) {
  const [px, setPx] = useState('');
  const [reason, setReason] = useState('manual');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    if (!isPrice(px)) { setErr('Enter the price you sold at'); return; }
    setBusy(true);
    try {
      await api.paperClose(pos.id, { exit_price: Number(px), reason });
      toast({ ok: true, text: `${pos.ticker}: closed at ${Number(px).toFixed(2)}.` });
      onDone();
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };
  return (
    <form className="inline-form" onSubmit={submit} noValidate>
      <label className="sr-only" htmlFor={`exit-${pos.id}`}>Price you sold {pos.ticker} at</label>
      <input id={`exit-${pos.id}`} className="input-sm" inputMode="decimal" placeholder="price you sold at"
             value={px} onChange={(e) => { setPx(e.target.value); setErr(null); }}
             aria-invalid={Boolean(err)} />
      <label className="sr-only" htmlFor={`why-${pos.id}`}>Why you sold {pos.ticker}</label>
      <select id={`why-${pos.id}`} className="input-sm" value={reason} onChange={(e) => setReason(e.target.value)}>
        <option value="profit_take">Hit profit target</option>
        <option value="stop">Hit stop-loss</option>
        <option value="vertical">Time limit reached</option>
        <option value="trail">Trailing stop hit</option>
        <option value="manual">My own call</option>
      </select>
      <button type="submit" className="btn sm" disabled={!px || busy}>{busy ? 'Saving…' : 'Sold it'}</button>
      {err && <span className="neg inline-msg" role="alert">✕ {err}</span>}
    </form>
  );
}

function Settings({ nav, equity, cfg, onSaved }) {
  const [navIn, setNavIn] = useState(String(nav ?? ''));
  const [eqIn, setEqIn] = useState(equity == null ? '' : String(equity));
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const dirty = navIn !== String(nav ?? '') || eqIn !== (equity == null ? '' : String(equity));
  const valid = isPrice(navIn) && (eqIn === '' || isPrice(eqIn));
  const save = async (e) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      await api.paperSettings({
        nav: Number(navIn),
        account_equity: eqIn === '' ? null : Number(eqIn),
      });
      toast({ ok: true, text: 'Settings saved — share counts on the Today page now use the new pot size.' });
      onSaved();
    } catch (ex) {
      toast({ ok: false, text: `Could not save settings: ${ex.message}`, ttl: 8000 });
    } finally { setBusy(false); }
  };
  return (
    <Card title="Settings" right={<Icon name="sliders" size={16} className="muted" />}
          subtitle="The practice pot sizes the share counts on the Today page. Set your real account size too if you want the day-trading limit enforced realistically.">
      <form onSubmit={save} noValidate>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field" style={{ width: 180 }}>Practice pot ($)
            <input inputMode="decimal" value={navIn} onChange={(e) => setNavIn(e.target.value)}
                   aria-invalid={!isPrice(navIn)} />
          </label>
          <label className="field" style={{ width: 180 }}>Real account size ($)
            <input inputMode="decimal" value={eqIn} placeholder="unset"
                   onChange={(e) => setEqIn(e.target.value)}
                   aria-invalid={eqIn !== '' && !isPrice(eqIn)} />
          </label>
          <button type="submit" className="btn primary" disabled={!dirty || !valid || busy}>
            {busy ? 'Saving…' : 'Save settings'}
          </button>
        </div>
        <p className="muted small" style={{ marginTop: 10 }}>
          US brokers limit accounts under ${fmtInt(cfg.pdt.equity_floor)} to{' '}
          {cfg.pdt.limit} same-day buy-and-sells per {cfg.pdt.window_business_days}{' '}
          business days — the book enforces that when your real account is below the line.
        </p>
      </form>
    </Card>
  );
}

export default function Paper() {
  const [d, setD] = useState({ loading: true });
  const [backtestSharpe, setBacktestSharpe] = useState(null);
  const toast = useToast();

  const load = () => api.paper().then((p) => setD({ p })).catch((error) => setD({ error }));
  useEffect(() => {
    load();
    api.summary().then((s) => setBacktestSharpe(s.book?.sharpe_net)).catch(() => {});
  }, []);

  const positions = d.p?.positions ?? EMPTY;
  const ordered = useMemo(() => positions.filter((p) => p.status === 'ordered'), [positions]);
  const open = useMemo(() => positions.filter((p) => p.status === 'open'), [positions]);
  const closed = useMemo(() => positions.filter((p) => p.status === 'closed')
    .sort((a, b) => (b.exit_date || '').localeCompare(a.exit_date || '')), [positions]);
  const orderedSort = useSort(ordered);
  const openSort = useSort(open);
  const closedSort = useSort(closed);

  if (d.loading) return <Loading what="paper book" />;
  if (d.error) {
    return <ErrorBox error={d.error} onRetry={() => { setD({ loading: true }); load(); }}
                     hint="Is the API reachable? Check VITE_API_BASE and the backend's /api/health." />;
  }

  const { stats: st, cfg, nav, account_equity: equity } = d.p;

  const slipPct = Math.min(100,
    (st.slippage.n_fills / st.slippage.adoption_min_fills) * 100);
  const decayFloor = backtestSharpe != null ? backtestSharpe * cfg.decay.ratio_of_backtest : null;
  const decayBreached = st.decay.rolling_sharpe != null && decayFloor != null
    && st.decay.rolling_sharpe < decayFloor;

  const eqSeries = st.realized.equity.length > 1 ? [{
    name: 'Paper book (realized)',
    color: 'var(--series-1)',
    points: st.realized.equity.map((p) => ({ x: p.date, y: p.equity - 1 })),
  }] : null;

  const cancel = (p) => api.paperRemove(p.id)
    .then(() => { toast({ ok: true, text: `${p.ticker}: order cancelled.` }); load(); })
    .catch((e) => toast({ ok: false, text: `${p.ticker}: ${e.message}`, ttl: 8000 }));

  return (
    <>
      <PageHeader eyebrow="Trade · practice book" icon="book" title="Your practice book"
                  lede={<>Trades you chose to track, run with pretend money. When one "fills" at the
                    open, record the price here — comparing it with the official opening print
                    is the whole point of this practice stage.</>}
                  actions={(
                    <button type="button" className="btn sm" onClick={() => { load(); }}>
                      <Icon name="refresh" size={14} />Refresh
                    </button>
                  )} />

      <Stats label="Practice book">
        <StatTile label="Waiting to fill" value={fmtInt(st.counts.ordered)}
                  sub="orders for the next open" />
        <StatTile label="Open" value={fmtInt(st.counts.open)} sub="trades you're in right now" />
        <StatTile label="Finished" value={fmtInt(st.counts.closed)}
                  sub={st.realized.win_rate != null
                    ? `${fmtPct(st.realized.win_rate)} made money` : '—'} />
        <StatTile label="Avg profit per trade"
                  value={st.realized.avg_ret != null ? fmtSignedPct(st.realized.avg_ret, 2) : '—'}
                  sub="after trading costs"
                  tone={st.realized.avg_ret == null ? ''
                    : st.realized.avg_ret >= 0 ? 'pos' : 'neg'} />
        <StatTile label="Risk-adjusted score" value={fmtNum(st.realized.sharpe_all, 2)}
                  sub={backtestSharpe != null
                    ? `Sharpe · the backtest scored ${fmtNum(backtestSharpe, 2)}` : 'Sharpe'} />
      </Stats>

      <div className="grid cols-3">
        <Card title="Do you get the price you expect?"
              subtitle="The gap between the official opening price and the price you actually got (slippage) — the measurement this whole practice stage exists to collect. 100 bps = 1%.">
          <div className="big-num num">
            {st.slippage.median_bps == null ? '—' : `${fmtNum(st.slippage.median_bps, 1)} bps`}
          </div>
          <div className="small muted">
            median of {fmtInt(st.slippage.n_fills)} fills
            {st.slippage.mad_bps != null && ` · MAD ${fmtNum(st.slippage.mad_bps, 1)} bps`}
          </div>
          <div className="progress" style={{ marginTop: 12 }} role="progressbar"
               aria-label="Fills recorded toward adoption"
               aria-valuenow={st.slippage.n_fills} aria-valuemin={0}
               aria-valuemax={st.slippage.adoption_min_fills}>
            <div className={st.slippage.adopted ? 'done' : ''} style={{ width: `${slipPct}%` }} />
          </div>
          <div className="small muted" style={{ marginTop: 6 }}>
            {st.slippage.adopted
              ? <><span aria-hidden="true">✓ </span>Enough data — now baked into the cost model.</>
              : `${st.slippage.n_fills} of the ${st.slippage.adoption_min_fills} recorded fills needed before it counts`}
          </div>
        </Card>

        <Card title="Safety rules"
              subtitle="The day-trading limit and the daily loss cut-off, enforced automatically.">
          <div style={{ display: 'grid', gap: 14 }}>
            <div>
              <div className="small muted">Bought &amp; sold the same day (last {st.pdt.window_business_days} business days) — US rules allow max 3 under $25k</div>
              <div className="kv-big" style={{ marginTop: 2 }}>
                <span className="big-num num" style={{ fontSize: 24 }}>{st.pdt.used} / {st.pdt.limit}</span>
                <Badge kind={st.pdt.enforced ? (st.pdt.used >= st.pdt.limit ? 'fail' : 'neutral') : 'neutral'}>
                  {st.pdt.enforced ? 'enforced (< $25k)' : 'not enforced'}
                </Badge>
              </div>
            </div>
            <div>
              <div className="small muted">Bad-day brake: lose more than {fmtPct(st.kill_switch.threshold_pct, 0)} in one day and no new trades are allowed</div>
              <div style={{ marginTop: 6 }}>
                <Badge kind={st.kill_switch.tripped ? 'fail' : 'pass'}>
                  {st.kill_switch.tripped ? 'TRIPPED — no new trades today' : 'Not tripped'}
                </Badge>
              </div>
            </div>
          </div>
        </Card>

        <Card title="Is the strategy fading?"
              subtitle={`Your last ${st.decay.window_sessions} sessions of practice results, scored against what the backtest promised. If it stays below half the promise for too long, the strategy gets retrained or retired.`}>
          <div className="big-num num">
            {st.decay.rolling_sharpe == null ? '—' : fmtNum(st.decay.rolling_sharpe, 2)}
          </div>
          <div className="small muted">
            {st.decay.sessions_recorded} / {st.decay.window_sessions} sessions recorded
            {decayFloor != null && ` · retire floor ${fmtNum(decayFloor, 2)}`}
          </div>
          <div style={{ marginTop: 10 }}>
            {st.decay.rolling_sharpe == null
              ? <Badge kind="neutral">Not enough history yet</Badge>
              : <Badge kind={decayBreached ? 'fail' : 'pass'}>
                  {decayBreached ? 'Doing worse than promised — watch it' : 'Healthy'}
                </Badge>}
          </div>
        </Card>
      </div>

      {eqSeries && (
        <Card title="How your practice money has done"
              subtitle="% change since you started, counting finished trades only — open ones aren't counted until they close, so this is the honest number.">
          <LineChart series={eqSeries} height={230} zeroLine label="Practice book realized return"
                     yFormat={(v) => fmtSignedPct(v, 2)} />
        </Card>
      )}

      {ordered.length > 0 && (
        <Card flush title="Waiting to fill" count={ordered.length}
              subtitle="These sit here until the market next opens. Once you buy, enter the price you paid and the day's official opening price — the gap between them is the slippage measurement.">
          <div className="table-wrap">
            <table className="sticky-first">
              <thead><tr>
                <Th k="ticker" sort={orderedSort.sort} onSort={orderedSort.onSort}>Stock</Th>
                <Th k="signal_date" sort={orderedSort.sort} onSort={orderedSort.onSort}>Picked on</Th>
                <Th k="target_weight" num sort={orderedSort.sort} onSort={orderedSort.onSort}>Slice of pot</Th>
                <Th k="shares" num sort={orderedSort.sort} onSort={orderedSort.onSort}>Shares</Th>
                <Th k="ref_close" num sort={orderedSort.sort} onSort={orderedSort.onSort}>Close that day</Th>
                <Th k="stop_pct" num sort={orderedSort.sort} onSort={orderedSort.onSort}>Stop</Th>
                <Th k="profit_take_pct" num sort={orderedSort.sort} onSort={orderedSort.onSort}>Profit-take</Th>
                <Th>What did you pay?</Th><Th><span className="sr-only">Actions</span></Th>
              </tr></thead>
              <tbody>
                {orderedSort.rows.map((p) => (
                  <tr key={p.id}>
                    <td><span className="ticker">{p.ticker}</span>{p.side < 0 && <span className="small muted"> short</span>}</td>
                    <td className="muted">{p.signal_date}</td>
                    <td className="n">{fmtPct(p.target_weight, 2)}</td>
                    <td className="n">{p.shares != null ? fmtInt(p.shares) : '—'}</td>
                    <td className="n">{fmtNum(p.ref_close, 2)}</td>
                    <td className="n neg">{fmtNum(p.stop_pct, 2)}%</td>
                    <td className="n pos">+{fmtNum(p.profit_take_pct, 2)}%</td>
                    <td><FillForm pos={p} onDone={load} /></td>
                    <td>
                      <ConfirmButton onConfirm={() => cancel(p)} confirmText="Cancel order?">
                        Cancel
                      </ConfirmButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {open.length > 0 && (
        <Card flush title="Trades you're in" count={open.length}
              subtitle="The sell triggers below come from the price you actually paid, exactly as the backtest computes them.">
          <div className="table-wrap">
            <table className="sticky-first">
              <thead><tr>
                <Th k="ticker" sort={openSort.sort} onSort={openSort.onSort}>Stock</Th>
                <Th k="fill_date" sort={openSort.sort} onSort={openSort.onSort}>Bought</Th>
                <Th k="fill_price" num sort={openSort.sort} onSort={openSort.onSort}>You paid</Th>
                <Th k="slip_bps" num sort={openSort.sort} onSort={openSort.onSort}>Slippage</Th>
                <Th k="stop_price" num sort={openSort.sort} onSort={openSort.onSort}>Sell if it drops to</Th>
                <Th k="profit_take_price" num sort={openSort.sort} onSort={openSort.onSort}>Sell if it climbs to</Th>
                <Th k="target_weight" num sort={openSort.sort} onSort={openSort.onSort}>Slice of pot</Th>
                <Th k="shares" num sort={openSort.sort} onSort={openSort.onSort}>Shares</Th>
                <Th>Close it out</Th>
              </tr></thead>
              <tbody>
                {openSort.rows.map((p) => (
                  <tr key={p.id}>
                    <td><span className="ticker">{p.ticker}</span>{p.side < 0 && <span className="small muted"> short</span>}</td>
                    <td className="muted">{p.fill_date}</td>
                    <td className="n">{fmtNum(p.fill_price, 2)}</td>
                    <td className="n">
                      {p.slip_bps == null ? <span className="muted">—</span>
                        : <span className={p.slip_bps <= 0 ? 'pos' : 'neg'}>
                            <span aria-hidden="true">{p.slip_bps <= 0 ? '▲' : '▼'}</span>{' '}
                            {fmtNum(p.slip_bps, 1)} bps
                          </span>}
                    </td>
                    <td className="n neg">{fmtNum(p.stop_price, 2)}</td>
                    <td className="n pos">{fmtNum(p.profit_take_price, 2)}</td>
                    <td className="n">{fmtPct(p.target_weight, 2)}</td>
                    <td className="n">{p.shares != null ? fmtInt(p.shares) : '—'}</td>
                    <td><CloseForm pos={p} onDone={load} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-body">
            <div className="note">
              Slippage: negative means you got a better price than the official open
              (▲ good for you); positive means you paid up (▼ costly). 100 bps = 1%.
            </div>
          </div>
        </Card>
      )}

      <Card flush title="Finished trades" count={closed.length}
            subtitle="What each practice trade made or lost, with the same trading costs the backtest charges.">
        <div className="table-wrap">
          <table className="sticky-first">
            <thead><tr>
              <Th k="ticker" sort={closedSort.sort} onSort={closedSort.onSort}>Stock</Th>
              <Th k="fill_date" sort={closedSort.sort} onSort={closedSort.onSort}>Bought</Th>
              <Th k="exit_date" sort={closedSort.sort} onSort={closedSort.onSort}>Sold</Th>
              <Th k="exit_reason" sort={closedSort.sort} onSort={closedSort.onSort}>Why sold</Th>
              <Th k="fill_price" num sort={closedSort.sort} onSort={closedSort.onSort}>Paid</Th>
              <Th k="exit_price" num sort={closedSort.sort} onSort={closedSort.onSort}>Got</Th>
              <Th k="holding_days" num sort={closedSort.sort} onSort={closedSort.onSort}>Days held</Th>
              <Th k="ret_net" num sort={closedSort.sort} onSort={closedSort.onSort}>Profit / loss</Th>
            </tr></thead>
            <tbody>
              {closedSort.rows.map((p) => (
                <tr key={p.id}>
                  <td><span className="ticker">{p.ticker}</span></td>
                  <td className="muted">{p.fill_date}</td>
                  <td className="muted">{p.exit_date}</td>
                  <td>{p.exit_reason?.replace('_', ' ')}{p.day_trade && ' · day trade'}</td>
                  <td className="n">{fmtNum(p.fill_price, 2)}</td>
                  <td className="n">{fmtNum(p.exit_price, 2)}</td>
                  <td className="n">{p.holding_days}</td>
                  <td className="n"><Delta value={p.ret_net} /></td>
                </tr>
              ))}
              {!closed.length && (
                <tr><td colSpan="8" className="empty-cell">
                  <EmptyState icon="inbox" title="No finished trades yet">
                    Press "Track this trade" on the <a href="#today">Today page</a>, record what you
                    paid when it fills, then close it here when one of its sell triggers is hit.
                  </EmptyState>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Settings key={`${nav}-${equity}`} nav={nav} equity={equity} cfg={cfg} onSaved={load} />
    </>
  );
}
