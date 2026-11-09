/* The trade ticket: what to do at the NEXT open, in plain terms.
   Answers the two questions the raw suggestion file cannot — which session these
   orders belong to (Friday evening and all weekend both point at Monday), and
   which names are genuinely new versus already held.
   Default view speaks broker-ticket language (shares, dollars, trigger prices);
   the quant columns (weight, conviction, barrier %s) live behind a toggle.

   Layout: the plan in one sentence → anything that should stop you (stale
   list, open already passed) → the order counts → the orders themselves as
   numbered steps, in the order they should be placed (exits free the cash
   the buys spend). */
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtPct, fmtInt } from '../components/Chart.jsx';
import {
  Card, StatTile, Stats, Badge, Loading, ErrorBox, useSort, Th, PageHeader, Callout,
  Segmented,
} from '../components/Bits.jsx';
import { useToast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';

const EMPTY = [];

const DOW = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export const pretty = (iso) => {
  if (!iso) return '—';
  const d = new Date(`${iso}T12:00:00Z`);
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${
    d.toLocaleString('en', { month: 'short', timeZone: 'UTC' })}`;
};

const fmtMoney = (v) => (v == null || Number.isNaN(v)
  ? '—' : `$${Math.round(v).toLocaleString('en-US')}`);
const fmtPrice = (v) => (v == null || Number.isNaN(v)
  ? '—' : `$${Number(v).toFixed(2)}`);

const STATE_TEXT = {
  closed: 'Market closed',
  pre_open: 'Pre-open',
  open: 'Market open',
  post_close: 'After the close',
};

/* ------------------------------------------------- simple (default) rows */

/* A short row (side -1) reads "Sell short": the stop column is the price it
   must be bought back at if it climbs, the profit-take the price to buy it
   back at if it drops. Same cells, mirrored meaning; the card headers say so. */
function BuyRowSimple({ r, onAct, busy }) {
  const noTriggers = r.barrier_unreachable;
  const skipped = r.skipped;                 // whole shares only: under one share
  const short = r.side < 0;
  const verb = short ? 'Sell short' : 'Buy';
  const exitVerb = short ? 'Buy back' : 'Sell';
  // Already in the practice book: the engine is adding a lot to it. The paper
  // book holds one position per name, so "track" would only bounce (409).
  const tracked = r.position_id != null;
  return (
    <tr>
      <td className="cell-primary">
        <span className="ticker">{r.ticker}</span>
        {tracked && <Badge kind="info" glyph="●">tracked</Badge>}
      </td>
      <td data-label="What to do">
        <strong>{skipped ? 'Skip'
          : r.shares != null ? `${verb} ${fmtInt(r.shares)} shares` : verb}</strong>
        <span className="sub">
          {skipped
            ? 'under one whole share at this price — whole shares only'
            : tracked ? `at the open — adds a lot to the ${r.ticker} ${r.status === 'ordered' ? 'order' : 'position'} you track`
              : short ? 'at the open — borrowed shares (margin account)' : 'at the open'}
        </span>
      </td>
      <td className="n" data-label="Latest close">{fmtPrice(r.last_close)}</td>
      <td className="n" data-label={short ? 'Worth about' : 'Costs about'}>
        {skipped ? <span className="muted">—</span> : fmtMoney(r.est_cost)}
        <span className="sub">{fmtPct(r.target_weight, 1)} of your money</span>
      </td>
      {noTriggers ? (
        <td colSpan="2" className="small muted cell-full wrap" data-label="Price triggers">
          no price triggers — just {short ? 'buy back' : 'sell'} by the date →
        </td>
      ) : (
        <>
          <td className="n neg" data-label={`${exitVerb} if it ${short ? 'climbs' : 'drops'} to`}>
            {fmtPrice(r.stop_price)}
          </td>
          <td className="n pos" data-label={`${exitVerb} if it ${short ? 'drops' : 'climbs'} to`}>
            {fmtPrice(r.profit_take_price)}
          </td>
        </>
      )}
      <td data-label={`${exitVerb} by (latest)`}>
        {r.sell_by_date ? pretty(r.sell_by_date) : `${r.max_hold_sessions} trading days`}
        {r.sell_by_date && <span className="sub">{r.max_hold_sessions} trading days</span>}
      </td>
      <td className="n cell-action">
        {onAct && !skipped && tracked && (
          <span className="btn sm done" aria-disabled="true">
            <Icon name="check" size={14} />Already tracked
          </span>
        )}
        {onAct && !skipped && !tracked && (
          <button type="button" className="btn sm" disabled={busy === r.ticker}
                  onClick={() => onAct(r)} aria-label={`Track ${r.ticker} in the practice book`}>
            {busy === r.ticker ? 'Adding…' : <><Icon name="plus" size={14} />Track this trade</>}
          </button>
        )}
      </td>
    </tr>
  );
}

/* Hold rows are keyed by price direction ("if it drops to" / "if it climbs
   to"), so a short's cells swap: dropping reaches its profit-take, climbing
   its stop. */
function HoldRowSimple({ r, exitWord }) {
  const short = r.side < 0;
  const dropTo = short ? r.profit_take_price : r.stop_price;
  const climbTo = short ? r.stop_price : r.profit_take_price;
  return (
    <tr>
      <td className="cell-primary">
        <span className="ticker">{r.ticker}</span>
        {short && <Badge kind="neutral">short</Badge>}
      </td>
      <td data-label="What to do">
        <strong>Do nothing</strong>
        <span className="sub">
          {r.status === 'ordered' ? 'order already placed, waiting to fill'
            : short ? 'keep the short open' : 'keep holding it'}
        </span>
      </td>
      <td className="n" data-label="You paid">{r.fill_price != null ? fmtPrice(r.fill_price) : '—'}</td>
      {r.barrier_unreachable ? (
        <td colSpan="2" className="small muted cell-full wrap" data-label="Price triggers">
          no price triggers — just {short ? 'buy back' : 'sell'} by the date →
        </td>
      ) : (
        <>
          <td className={`n ${short ? 'pos' : 'neg'}`} data-label={`${exitWord} if it drops to`}>{fmtPrice(dropTo)}</td>
          <td className={`n ${short ? 'neg' : 'pos'}`} data-label={`${exitWord} if it climbs to`}>{fmtPrice(climbTo)}</td>
        </>
      )}
      <td data-label={`${exitWord} by (latest)`}>{r.sell_by_date ? pretty(r.sell_by_date) : '—'}</td>
    </tr>
  );
}

/* --------------------------------------------------- detailed-view row */

const KIND = {
  BUY: ['pass', '▲', 'Buy'],
  SKIP: ['neutral', '·', 'Skip'],
  SHORT: ['fail', '▼', 'Sell short'],
  SELL: ['fail', '▼', 'Sell'],
  COVER: ['pass', '▲', 'Buy back'],
  HOLD: ['neutral', '=', 'Hold'],
};
const signed = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${fmtNum(v, 2)}%`);

function ActionRow({ r, kind }) {
  const wide = r.barrier_unreachable;
  const short = r.side < 0;
  const k = r.skipped ? 'SKIP' : kind === 'HOLD' && short ? 'HOLD' : kind;
  const [tone, glyph, label] = KIND[k] ?? KIND.HOLD;
  return (
    <tr>
      <td><span className="ticker">{r.ticker}</span>{short && kind === 'HOLD' && <span className="small muted"> short</span>}</td>
      <td><Badge kind={tone} glyph={glyph}>{label}</Badge></td>
      <td className="n">{r.target_weight ? fmtPct(r.target_weight, 2) : '—'}</td>
      <td className="n">{r.ensemble_rank != null ? fmtNum(r.ensemble_rank, 3) : '—'}</td>
      <td className="n">{r.last_close != null ? fmtNum(r.last_close, 2)
        : r.fill_price != null ? fmtNum(r.fill_price, 2) : '—'}</td>
      <td className="n neg">{signed(r.stop_pct)}</td>
      <td className="n pos">{signed(r.profit_take_pct)}</td>
      <td className="n" title={short
        ? 'Trailing stop: each night lower the buy-stop to the low since fill plus this, never above the fixed stop'
        : 'Trailing stop: each night raise the stop to the high since fill minus this, never below the fixed stop'}>
        {r.trail_pct != null ? `${short ? '+' : '-'}${fmtNum(r.trail_pct, 2)}%` : '—'}</td>
      <td className="small muted wrap" style={{ maxWidth: 280 }}>
        {wide ? <Badge kind="neutral">⏱ time-exit only</Badge> : r.reason}
      </td>
    </tr>
  );
}

function DetailHead({ sort, onSort }) {
  const p = { sort, onSort };
  return (
    <tr>
      <Th k="ticker" {...p}>Ticker</Th><Th>Action</Th>
      <Th k="target_weight" num {...p}>Target weight</Th>
      <Th k="ensemble_rank" num {...p}>Conviction</Th>
      <Th k="last_close" num {...p}>Price</Th>
      <Th k="stop_pct" num {...p}>Stop</Th>
      <Th k="profit_take_pct" num {...p}>Profit-take</Th>
      <Th k="trail_pct" num {...p}>Trail</Th><Th>Why</Th>
    </tr>
  );
}

/* ---------------------------------------------------------------- page */

const SELL_REASON = {
  'dropped out of the target book': 'the model no longer ranks it worth holding',
  'model flagged an exit': 'the model says it is time to get out',
};

function Help({ nav }) {
  return (
    <Card title="How to use this page" right={<Icon name="help" size={18} className="muted" />}>
      <p className="secondary" style={{ maxWidth: '80ch' }}>
        After every market close, the model re-scores the market and picks the
        stocks it likes best. This page turns that into a shopping list for the
        next time the market opens.
      </p>
      <p style={{ margin: '14px 0 10px' }}>
        <strong>Every buy comes with its exit plan already decided.</strong> You
        sell when the <em>first</em> of three things happens:
      </p>
      <div className="help">
        <div className="h-item">
          <strong className="neg"><span aria-hidden="true">▼ </span>The price falls to the "sell if it drops to" level</strong>
          — cut the loss.
        </div>
        <div className="h-item">
          <strong className="pos"><span aria-hidden="true">▲ </span>The price climbs to the "sell if it climbs to" level</strong>
          — take the profit.
        </div>
        <div className="h-item">
          <strong><span aria-hidden="true">⏱ </span>The "sell by" date arrives</strong>
          — sell at that morning's open no matter what.
        </div>
      </div>
      <p className="secondary" style={{ marginTop: 14, maxWidth: '80ch' }}>
        Share counts and dollar amounts are sized to your practice account
        ({fmtMoney(nav)} — change it on the Paper page), in <strong>whole shares
        only</strong>: a slot that would be less than one share at the current
        price is marked "Skip" and left out. The trigger prices are estimates
        from the last close; the exact levels come from the price you actually
        pay. "Track this trade" records the buy in your practice book so
        the page can tell you when to sell it — no real money moves anywhere.
      </p>
    </Card>
  );
}

export default function Today() {
  const [d, setD] = useState({ loading: true });
  const [busy, setBusy] = useState(null);
  const [showHolds, setShowHolds] = useState(false);
  const [detail, setDetail] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const toast = useToast();

  const load = () => api.today().then((t) => setD({ t })).catch((error) => setD({ error }));
  useEffect(() => { load(); }, []);

  const t = d.t ?? {};
  const buySort = useSort(t.buys ?? EMPTY);
  const sellSort = useSort(t.sells ?? EMPTY);
  const holdSort = useSort(t.holds ?? EMPTY);
  const dueSort = useSort(t.due_exits ?? EMPTY);
  const shortSort = useSort(t.shorts ?? EMPTY);
  const coverSort = useSort(t.covers ?? EMPTY);

  if (d.loading) return <Loading what="today's plan" />;
  if (d.error) {
    return <ErrorBox error={d.error} onRetry={() => { setD({ loading: true }); load(); }}
                     hint={d.error.body?.hint || 'Is the API reachable, and has a report been published?'} />;
  }
  if (t.error) return <ErrorBox error={t.error} hint="Run the predict job, then rebuild the bundle." />;
  const s = t.session;
  const nav = t.plan?.nav;

  const buy = async (r) => {
    setBusy(r.ticker);
    try {
      await api.paperOpen({
        ticker: r.ticker, side: r.side ?? 1, target_weight: r.target_weight,
        signal_date: t.signals.as_of_close, ref_close: r.last_close,
        stop_pct: r.stop_pct, profit_take_pct: r.profit_take_pct,
        trail_pct: r.trail_pct ?? null,
        max_hold_sessions: r.max_hold_sessions, ensemble_rank: r.ensemble_rank,
      });
      toast({ ok: true, text: `${r.ticker} is now tracked in your practice book — it "${r.side < 0 ? 'sells short' : 'fills'}" at the ${pretty(s.next_open)} open.` });
      load();
    } catch (e) { toast({ ok: false, text: `${r.ticker}: ${e.message}`, ttl: 8000 }); }
    finally { setBusy(null); }
  };

  // The one-sentence version of the whole page.
  const planBits = [];
  const anyShort = Boolean(t.counts.short || t.counts.cover
    || (t.holds ?? EMPTY).some((r) => r.side < 0) || (t.due_exits ?? EMPTY).some((r) => r.side < 0));
  if (t.counts.due_exit) planBits.push(`${anyShort ? 'close' : 'sell'} ${t.counts.due_exit} whose time is up`);
  if (t.counts.sell) planBits.push(`sell ${t.counts.sell} the model dropped`);
  if (t.counts.cover) planBits.push(`buy back ${t.counts.cover} short${t.counts.cover === 1 ? '' : 's'} the model dropped`);
  if (t.counts.buy) {
    planBits.push(`buy ${t.counts.buy} stock${t.counts.buy === 1 ? '' : 's'} for about ${
      fmtMoney(t.plan?.invest_total)}`);
  }
  if (t.counts.short) {
    planBits.push(`sell short ${t.counts.short} stock${t.counts.short === 1 ? '' : 's'} worth about ${
      fmtMoney(t.plan?.short_total)}`);
  }
  if (t.counts.hold) planBits.push(`leave ${t.counts.hold} alone`);
  if (t.counts.skipped) planBits.push(`skip ${t.counts.skipped} that would be under one whole share`);
  const anyShortHold = (t.holds ?? EMPTY).some((r) => r.side < 0);
  const exitWord = anyShortHold ? 'Get out' : 'Sell';
  const planText = planBits.length
    ? `${planBits.join(', then ')}.` : 'nothing — there are no orders for this open.';

  const sessionNote = s.is_weekend
    ? 'It is the weekend — the next trading day is Monday.'
    : s.market_state === 'post_close'
      ? 'Today has closed; do these when the market next opens.'
      : s.market_state === 'pre_open'
        ? 'Before the bell — do these at today\'s open.'
        : s.market_state === 'open'
          ? 'The market is already open; the opening price has passed.'
          : 'Market closed today.';

  // Steps are numbered in the order they should be placed.
  let n = 0;
  const step = () => { n += 1; return n; };
  const tableCls = (extra = '') => `stackable ${extra}`.trim();

  return (
    <>
      <PageHeader
        eyebrow="Trade · next open" icon="today"
        title={`Your plan for the ${pretty(s.next_open)} open`}
        lede={<>In short: <strong>{planText}</strong></>}
        meta={(
          <>
            <Badge kind={s.market_state === 'open' || s.market_state === 'pre_open' ? 'info' : 'neutral'}
                   glyph="●">{STATE_TEXT[s.market_state]}</Badge>
            <Badge kind={t.signals.fresh ? 'pass' : 'fail'}>
              {t.signals.fresh ? 'List is current' : 'List is out of date'}
            </Badge>
            <span className="small muted">
              Based on the {pretty(t.signals.as_of_close)} close and your{' '}
              {fmtMoney(nav)} practice account. {sessionNote}
            </span>
          </>
        )}
        actions={(
          <>
            <Segmented label="Table detail" value={detail ? 'detail' : 'simple'}
                       onChange={(v) => setDetail(v === 'detail')}
                       options={[['simple', 'Simple view'], ['detail', 'Detailed view']]} />
            <button type="button" className="btn sm" aria-expanded={showHelp}
                    onClick={() => setShowHelp(!showHelp)}>
              <Icon name="help" size={14} />{showHelp ? 'Hide help' : 'How do I use this?'}
            </button>
          </>
        )}
      />

      {showHelp && <Help nav={nav} />}

      <div className="callouts">
        {!t.signals.fresh && (
          <Callout tone="danger" role="alert" title="This list is out of date — don't trade from it">
            {t.signals.stale_reason}
          </Callout>
        )}
        {s.open_already_passed && (
          <Callout tone="warning" title="Today's opening price has already happened">
            These orders are meant for the moment the market opens. Buying later in
            the day means paying a different price than the plan assumes, so the
            numbers on this page no longer quite apply. Waiting for the next open
            is the safe choice.
          </Callout>
        )}
        <div className="callout-row">
        <Callout tone="warning" quiet icon="shield" title="Practice money only"
                 detail={<>Use it with the practice (paper) book, not your broker. Also: this
                   page only knows about stocks recorded in {t.holdings_source}</>}>
          The system's own quality checks say this strategy is not ready for real
          money yet ({t.gate_warning})
        </Callout>
        {t.bucket_book && (
          <Callout tone="info" quiet icon="coins" title="One pot per stock"
                   detail={t.bucket_book.cycle && (
                     <>This is session {t.bucket_book.cycle.session_in_cycle} of{' '}
                       {t.bucket_book.cycle.cycle_sessions} in the current cycle;{' '}
                       {(t.bucket_book.cycle.untraded_this_cycle ?? EMPTY).length} stock
                       {(t.bucket_book.cycle.untraded_this_cycle ?? EMPTY).length === 1 ? ' has' : 's have'}{' '}
                       not traded yet this cycle and will be bought by its last session.</>
                   )}>
            Every stock has its own pot (started at {fmtMoney(t.bucket_book.unit)} on{' '}
            {pretty(t.bucket_book.start)}) and keeps its own profit or loss. A buy spends
            that stock's whole pot; between trades the pot waits in cash.
          </Callout>
        )}
        </div>
      </div>

      <Stats label="Orders at a glance">
        <StatTile label="Buy" value={fmtInt(t.counts.buy)}
                  sub="new stocks to purchase, whole shares" tone={t.counts.buy ? 'pos' : ''} />
        {t.counts.skipped > 0 && (
          <StatTile label="Skip" value={fmtInt(t.counts.skipped)}
                    sub="under one whole share at your account size" />
        )}
        <StatTile label="Sell" value={fmtInt(t.counts.sell)}
                  sub="you own, model dropped them" tone={t.counts.sell ? 'neg' : ''} />
        {(t.counts.short > 0 || anyShort) && (
          <StatTile label="Sell short" value={fmtInt(t.counts.short)}
                    sub="new stocks to bet against" tone={t.counts.short ? 'neg' : ''} />
        )}
        {t.counts.cover > 0 && (
          <StatTile label="Buy back" value={fmtInt(t.counts.cover)}
                    sub="shorts the model dropped" tone="pos" />
        )}
        <StatTile label="Close — time is up" value={fmtInt(t.counts.due_exit)}
                  sub="reached their exit date" tone={t.counts.due_exit ? 'neg' : ''} />
        <StatTile label="Do nothing" value={fmtInt(t.counts.hold)}
                  sub="you own, still on the list" />
        <StatTile label="You own" value={fmtInt(t.counts.held_total)}
                  sub="stocks in the practice book" />
      </Stats>

      {t.due_exits.length > 0 && (
        <Card flush step={step()} title="Close first — time is up" count={t.due_exits.length}
              subtitle="These reached their exit date. Close them at the open no matter what the price is — the deadline is part of the strategy, even if the model still likes the position.">
          <div className="table-wrap">
            <table className={tableCls()}>
              <thead><tr>
                <Th k="ticker" sort={dueSort.sort} onSort={dueSort.onSort}>Stock</Th>
                <Th>What to do</Th>
                <Th k="fill_date" sort={dueSort.sort} onSort={dueSort.onSort}>Opened</Th>
                <Th k="vertical_date" sort={dueSort.sort} onSort={dueSort.onSort}>Exit-by date</Th>
              </tr></thead>
              <tbody>
                {dueSort.rows.map((r) => (
                  <tr key={r.position_id}>
                    <td className="cell-primary"><span className="ticker">{r.ticker}</span></td>
                    <td className="cell-full" data-label="What to do">
                      <strong>{r.side < 0 ? 'Buy back all the borrowed shares at the open'
                        : 'Sell all your shares at the open'}</strong>
                    </td>
                    <td className="muted" data-label="Opened">{pretty(r.fill_date)}</td>
                    <td className="muted" data-label="Exit-by date">{pretty(r.vertical_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {t.sells.length > 0 && (
        <Card flush step={step()} title="Sell" count={t.sells.length}
              subtitle="Stocks you own that the model no longer wants. Sell all your shares at the open.">
          <div className="table-wrap">
            <table className={tableCls()}>
              <thead><tr>
                <Th k="ticker" sort={sellSort.sort} onSort={sellSort.onSort}>Stock</Th>
                <Th>What to do</Th>
                <Th k="last_close" num sort={sellSort.sort} onSort={sellSort.onSort}>Latest close</Th>
                <Th k="fill_price" num sort={sellSort.sort} onSort={sellSort.onSort}>You paid</Th>
                <Th>Why</Th>
              </tr></thead>
              <tbody>
                {sellSort.rows.map((r) => (
                  <tr key={r.ticker}>
                    <td className="cell-primary"><span className="ticker">{r.ticker}</span></td>
                    <td className="cell-full" data-label="What to do"><strong>Sell all your shares at the open</strong></td>
                    <td className="n" data-label="Latest close">{fmtPrice(r.last_close)}</td>
                    <td className="n" data-label="You paid">{r.fill_price != null ? fmtPrice(r.fill_price) : '—'}</td>
                    <td className="small muted cell-full" data-label="Why">{SELL_REASON[r.reason] || r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {t.covers.length > 0 && (
        <Card flush step={step()} title="Buy back" count={t.covers.length}
              subtitle="Shorts you have open that the model no longer wants. Buy back all the borrowed shares at the open.">
          <div className="table-wrap">
            <table className={tableCls()}>
              <thead><tr>
                <Th k="ticker" sort={coverSort.sort} onSort={coverSort.onSort}>Stock</Th>
                <Th>What to do</Th>
                <Th k="last_close" num sort={coverSort.sort} onSort={coverSort.onSort}>Latest close</Th>
                <Th k="fill_price" num sort={coverSort.sort} onSort={coverSort.onSort}>You sold at</Th>
                <Th>Why</Th>
              </tr></thead>
              <tbody>
                {coverSort.rows.map((r) => (
                  <tr key={r.ticker}>
                    <td className="cell-primary"><span className="ticker">{r.ticker}</span></td>
                    <td className="cell-full" data-label="What to do"><strong>Buy back all the borrowed shares at the open</strong></td>
                    <td className="n" data-label="Latest close">{fmtPrice(r.last_close)}</td>
                    <td className="n" data-label="You sold at">{r.fill_price != null ? fmtPrice(r.fill_price) : '—'}</td>
                    <td className="small muted cell-full" data-label="Why">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card flush step={step()} title="Buy" count={t.buys.length}
            subtitle={detail
              ? `Quant view. Each fills market-on-open on ${pretty(s.next_open)} and carries its triple-barrier exits from the actual fill price.`
              : `Place each as a market order for when the market opens on ${pretty(s.next_open)}. The two sell prices and the sell-by date are your exit plan — whichever happens first wins.`}>
        <div className="table-wrap scroll">
          <table className={detail ? '' : tableCls()}>
            <thead>
              {detail ? <DetailHead sort={buySort.sort} onSort={buySort.onSort} /> : (
                <tr>
                  <Th k="ticker" sort={buySort.sort} onSort={buySort.onSort}>Stock</Th>
                  <Th k="shares" sort={buySort.sort} onSort={buySort.onSort}>What to do</Th>
                  <Th k="last_close" num sort={buySort.sort} onSort={buySort.onSort}>Latest close</Th>
                  <Th k="est_cost" num sort={buySort.sort} onSort={buySort.onSort}>Costs about</Th>
                  <Th k="stop_price" num sort={buySort.sort} onSort={buySort.onSort}>Sell if it drops to</Th>
                  <Th k="profit_take_price" num sort={buySort.sort} onSort={buySort.onSort}>Sell if it climbs to</Th>
                  <Th k="sell_by_date" sort={buySort.sort} onSort={buySort.onSort}>Sell by (latest)</Th>
                  <Th><span className="sr-only">Actions</span></Th>
                </tr>
              )}
            </thead>
            <tbody>
              {buySort.rows.map((r) => (detail
                ? <ActionRow key={r.ticker} r={r} kind="BUY" />
                : <BuyRowSimple key={r.ticker} r={r} onAct={buy} busy={busy} />))}
              {!t.buys.length && (
                <tr><td colSpan="9" className="empty">No buys for this open.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {!detail && t.counts.buy > 0 && (
          <div className="card-body" style={{ paddingTop: 0 }}>
            <div className="note">
              All {t.counts.buy} buys together come to about{' '}
              <strong>{fmtMoney(t.plan?.invest_total)}</strong> of your {fmtMoney(nav)}.
            </div>
          </div>
        )}
      </Card>

      {(t.shorts ?? EMPTY).length > 0 && (
        <Card flush step={step()} title="Sell short" count={t.shorts.length}
              subtitle={detail
                ? `Quant view of the short sleeve. Each is sold short market-on-open on ${pretty(s.next_open)}; its stop sits above the fill, its profit-take below.`
                : `Bet against these: sell borrowed shares at the ${pretty(s.next_open)} open (needs a margin account). Buy them back when the first of the two prices or the date is reached — whichever comes first.`}>
          <div className="table-wrap scroll">
            <table className={detail ? '' : tableCls()}>
              <thead>
                {detail ? <DetailHead sort={shortSort.sort} onSort={shortSort.onSort} /> : (
                  <tr>
                    <Th k="ticker" sort={shortSort.sort} onSort={shortSort.onSort}>Stock</Th>
                    <Th k="shares" sort={shortSort.sort} onSort={shortSort.onSort}>What to do</Th>
                    <Th k="last_close" num sort={shortSort.sort} onSort={shortSort.onSort}>Latest close</Th>
                    <Th k="est_cost" num sort={shortSort.sort} onSort={shortSort.onSort}>Worth about</Th>
                    <Th k="stop_price" num sort={shortSort.sort} onSort={shortSort.onSort}>Buy back if it climbs to</Th>
                    <Th k="profit_take_price" num sort={shortSort.sort} onSort={shortSort.onSort}>Buy back if it drops to</Th>
                    <Th k="sell_by_date" sort={shortSort.sort} onSort={shortSort.onSort}>Buy back by (latest)</Th>
                    <Th><span className="sr-only">Actions</span></Th>
                  </tr>
                )}
              </thead>
              <tbody>
                {shortSort.rows.map((r) => (detail
                  ? <ActionRow key={r.ticker} r={r} kind="SHORT" />
                  : <BuyRowSimple key={r.ticker} r={r} onAct={buy} busy={busy} />))}
              </tbody>
            </table>
          </div>
          {!detail && t.counts.short > 0 && (
            <div className="card-body" style={{ paddingTop: 0 }}>
              <div className="note">
                All {t.counts.short} shorts together come to about{' '}
                <strong>{fmtMoney(t.plan?.short_total)}</strong> of borrowed stock against your {fmtMoney(nav)}.
              </div>
            </div>
          )}
        </Card>
      )}

      {t.holds.length > 0 && (
        <Card flush title="Do nothing" count={t.holds.length}
              subtitle="You already own these and the model still likes them. No action — just keep an eye on their sell prices and dates."
              right={(
                <button type="button" className="btn sm" aria-expanded={showHolds}
                        onClick={() => setShowHolds(!showHolds)}>
                  <Icon name={showHolds ? 'chevronDown' : 'chevronRight'} size={14} />
                  {showHolds ? 'Hide' : 'Show'}
                </button>
              )}>
          {showHolds ? (
            <div className="table-wrap">
              <table className={detail ? '' : tableCls()}>
                <thead>
                  {detail ? <DetailHead sort={holdSort.sort} onSort={holdSort.onSort} /> : (
                    <tr>
                      <Th k="ticker" sort={holdSort.sort} onSort={holdSort.onSort}>Stock</Th>
                      <Th k="status" sort={holdSort.sort} onSort={holdSort.onSort}>What to do</Th>
                      <Th k="fill_price" num sort={holdSort.sort} onSort={holdSort.onSort}>You paid</Th>
                      <Th k="stop_price" num sort={holdSort.sort} onSort={holdSort.onSort}>{exitWord} if it drops to</Th>
                      <Th k="profit_take_price" num sort={holdSort.sort} onSort={holdSort.onSort}>{exitWord} if it climbs to</Th>
                      <Th k="sell_by_date" sort={holdSort.sort} onSort={holdSort.onSort}>{exitWord} by (latest)</Th>
                    </tr>
                  )}
                </thead>
                <tbody>
                  {holdSort.rows.map((r) => (detail
                    ? <ActionRow key={r.ticker} r={{ ...r, reason: r.status }} kind="HOLD" />
                    : <HoldRowSimple key={r.ticker} r={r} exitWord={exitWord} />))}
                </tbody>
              </table>
            </div>
          ) : <div style={{ height: 4 }} />}
        </Card>
      )}
    </>
  );
}
