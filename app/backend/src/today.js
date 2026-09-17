// "What do I do at the next open?" — the session-aware trade ticket.
//
// Two things the raw suggestion file cannot answer on its own:
//
//   1. WHICH SESSION do these orders belong to? An EOD system signals after a
//      close and fills at the NEXT open (G-02). On a Friday evening or all
//      weekend that next open is Monday; on a weekday morning it is today's.
//      Resolved against the D-11 NYSE calendar, so holidays are handled.
//   2. WHAT DO I ALREADY HOLD? The suggestion file is a TARGET book, not a
//      diff. Every name reads as a "buy" until it is compared with the current
//      book — so a name already held shows as HOLD, and a held name that has
//      dropped out of the target shows as SELL.
//
// Short sleeve (2026-09-17): the file also carries shorts_or_increases /
// short_holds / covers_or_exits. Those are matched against the paper book's
// side -1 positions the same way: SHORT (sell borrowed shares at the open) when
// not held, DO NOTHING when held, COVER (buy back) when held but dropped. Every
// row states its side.
import * as reports from './reports.js';
import { state as paperState } from './paper.js';
import { storeLocation } from './store.js';

const ET = 'America/New_York';

/** Wall-clock date + minutes-since-midnight in US market time. */
function nowInET(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: ET, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(now).reduce((a, p) => ({ ...a, [p.type]: p.value }), {});
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

const CLOSE_MIN = 16 * 60;      // 16:00 ET
const OPEN_MIN = 9 * 60 + 30;   // 09:30 ET

/** Pure: `sessions` is the sorted ISO list from the calendar section. */
export function sessionContext(now = new Date(), sessions = []) {
  const { date: todayET, minutes } = nowInET(now);
  const isSessionToday = sessions.includes(todayET);
  const todayClosed = isSessionToday && minutes >= CLOSE_MIN;

  // The most recent close whose data a signal could already reflect.
  const past = sessions.filter((s) => s < todayET || (s === todayET && todayClosed));
  const lastClose = past.length ? past[past.length - 1] : null;
  const nextOpen = sessions.find((s) => (lastClose ? s > lastClose : s >= todayET)) ?? null;

  const weekday = new Date(`${todayET}T12:00:00Z`).getUTCDay();
  return {
    now_et: todayET,
    minutes_et: minutes,
    is_trading_day: isSessionToday,
    is_weekend: weekday === 0 || weekday === 6,
    market_state: !isSessionToday ? 'closed'
      : minutes < OPEN_MIN ? 'pre_open'
        : minutes < CLOSE_MIN ? 'open' : 'post_close',
    last_completed_close: lastClose,
    next_open: nextOpen,
    open_already_passed: Boolean(nextOpen === todayET && minutes >= OPEN_MIN),
  };
}

export async function ticket(now = new Date()) {
  const [sug, cfg, calendar, book] = await Promise.all([
    reports.suggestions(), reports.config(), reports.readCalendar(), paperState(),
  ]);
  const cal = calendar?.sessions ?? [];
  const ctx = sessionContext(now, cal);
  if (!sug) return { session: ctx, error: 'no suggestions in the report bundle' };

  const nav = Number(book.nav) > 0 ? Number(book.nav) : 100000;
  // Paper positions by side: a short (side -1) lives in its own map, so a name
  // is matched against the long target and the short target independently.
  const heldL = new Map();
  const heldS = new Map();
  for (const p of book.positions) {
    if (p.status !== 'open' && p.status !== 'ordered') continue;
    (Number(p.side) < 0 ? heldS : heldL).set(p.ticker, p);
  }

  const iNextOpen = ctx.next_open ? cal.indexOf(ctx.next_open) : -1;
  // M5.2: vertical exit is a MOO at fill + h + 1 sessions. For a not-yet-held
  // name the fill session IS the next open; for a held one it is fill_date.
  const sellByFrom = (fillDate, h) => {
    const i = fillDate == null ? iNextOpen : cal.indexOf(fillDate);
    return i >= 0 ? cal[i + h + 1] ?? null : null;
  };

  // Plain-terms sizing: weight × NAV → whole shares at the last close, and the
  // barrier %s → the prices a broker ticket actually wants. Approximate until
  // the real fill (barriers hang off the fill, not this close). The %s are
  // signed per side, so px × (1 + pct/100) is the level for longs and shorts
  // alike: a short's stop sits above the price and its profit-take below.
  const rowFor = (ticker, r, side) => {
    const h = r.max_hold_sessions ?? cfg.barrier.h_days;
    const px = r.last_close > 0 ? r.last_close : null;
    const dollars = r.target_weight != null ? r.target_weight * nav : null;
    const shares = px && dollars != null ? Math.floor(dollars / px) : null;
    // A ±40%+ barrier is unreachable inside h sessions — the trade is
    // time-exit only, so trigger prices would be nonsense (even negative).
    const unreachable = Math.abs(r.stop_pct ?? 0) > 40;
    return {
      ticker,
      side,
      target_weight: r.target_weight,
      ensemble_rank: r.ensemble_rank,
      last_close: r.last_close,
      stop_pct: r.stop_pct,
      profit_take_pct: r.profit_take_pct,
      levels_basis: r.levels_basis ?? 'fill',
      new_lot_weight: r.new_lot_weight ?? null,
      sessions_left: r.sessions_left ?? null,
      lots: r.lots ?? null,
      // trailing stop (barrier.trail_m): each night a long's GTC stop is raised
      // to high_since_fill x (1 - trail_pct/100), a short's lowered to
      // low_since_fill x (1 + trail_pct/100), never past the fixed stop
      trail_pct: r.trail_pct ?? null,
      max_hold_sessions: h,
      shares,
      // 0 whole shares (price > slot) still costs the slot in fractional terms
      est_cost: shares ? shares * px : dollars,
      stop_price: !unreachable && px && r.stop_pct != null
        ? px * (1 + r.stop_pct / 100) : null,
      profit_take_price: !unreachable && px && r.profit_take_pct != null
        ? px * (1 + r.profit_take_pct / 100) : null,
      barrier_unreachable: unreachable,
    };
  };

  // The target book = today's new lots + the open lots the engine still holds
  // (event-engine ticket, 2026-09-08+). A held name shows DO NOTHING when the
  // paper book has it and BUY (open lot, to replicate the book) when it does
  // not. The short sleeve is the same story against the side -1 positions.
  const buildSleeve = (newRows, holdRows, heldMap, side) => {
    const target = new Map();
    for (const r of newRows || []) target.set(r.ticker, r);
    for (const r of holdRows || []) if (!target.has(r.ticker)) target.set(r.ticker, r);
    const verb = side < 0 ? 'SHORT' : 'BUY';
    const opens = [];
    const keeps = [];
    for (const [ticker, r] of target) {
      const pos = heldMap.get(ticker);
      const h = r.max_hold_sessions ?? cfg.barrier.h_days;
      const row = rowFor(ticker, r, side);
      const px = row.last_close > 0 ? row.last_close : null;
      // Event-engine book: a row may be an OPEN lot the backtest already holds —
      // sessions_left counts to its vertical from the next open, and its
      // stop/profit-take are priced off the last close (levels_basis).
      const sellBy = r.sessions_left != null && iNextOpen >= 0
        ? cal[iNextOpen + r.sessions_left] ?? null : sellByFrom(null, h);
      if (!pos) {
        opens.push({ ...row, action: verb,
                     reason: r.lots ? `open lot in the backtested book (${r.lots.length} lot${r.lots.length === 1 ? '' : 's'}) — not held here`
                                    : 'new — not held',
                     sell_by_date: sellBy });
      } else if (r.new_lot_weight > 0) {
        // held here AND the engine adds a lot today: trade the increment only
        const addDollars = r.new_lot_weight * nav;
        const addShares = px ? Math.floor(addDollars / px) : null;
        opens.push({
          ...row, action: verb, position_id: pos.id, status: pos.status,
          shares: addShares, est_cost: addShares ? addShares * px : addDollars,
          reason: `add a lot (${(r.new_lot_weight * 100).toFixed(2)}% of NAV) to an open ${side < 0 ? 'short ' : ''}position`,
          sell_by_date: sellByFrom(null, h) });
      } else {
        keeps.push({
          ...row, action: 'HOLD', position_id: pos.id, status: pos.status,
          fill_price: pos.fill_price ?? null,
          // A filled position's barriers are the real ones from the fill.
          stop_price: pos.stop_price ?? row.stop_price,
          profit_take_price: pos.profit_take_price ?? row.profit_take_price,
          sell_by_date: r.sessions_left != null && iNextOpen >= 0
            ? cal[iNextOpen + r.sessions_left] ?? null
            : sellByFrom(pos.fill_date ?? null, pos.max_hold_sessions ?? h),
        });
      }
    }
    return { target, opens, keeps };
  };
  const L = buildSleeve(sug.buys_or_increases, sug.holds, heldL, 1);
  const S = buildSleeve(sug.shorts_or_increases, sug.short_holds, heldS, -1);
  const buys = L.opens;
  const shorts = S.opens;
  const holds = [...L.keeps, ...S.keeps];

  // Held but no longer wanted, plus anything the source file explicitly exits.
  // A closed-out name is outside the target book, so its close must be scraped
  // from whichever suggestion section still prices it (sells carry their own
  // last_close in files written after 2026-09-02).
  const closeOf = new Map();
  for (const section of [sug.buys_or_increases, sug.holds, sug.sells_or_exits,
                         sug.shorts_or_increases, sug.short_holds, sug.covers_or_exits]) {
    for (const r of section || []) {
      if (r.last_close != null) closeOf.set(r.ticker, r.last_close);
    }
  }
  const sells = [];
  for (const [ticker, pos] of heldL) {
    if (!L.target.has(ticker)) {
      sells.push({
        ticker, side: 1, action: 'SELL', position_id: pos.id, status: pos.status,
        fill_price: pos.fill_price ?? null, target_weight: 0,
        last_close: closeOf.get(ticker) ?? null,
        reason: 'dropped out of the target book',
      });
    }
  }
  for (const r of sug.sells_or_exits || []) {
    if (!sells.some((x) => x.ticker === r.ticker)) {
      sells.push({ ticker: r.ticker, side: 1, action: 'SELL', target_weight: 0,
                   current_weight: r.current_weight,
                   last_close: closeOf.get(r.ticker) ?? null,
                   reason: 'model flagged an exit' });
    }
  }
  const covers = [];
  for (const [ticker, pos] of heldS) {
    if (!S.target.has(ticker)) {
      covers.push({
        ticker, side: -1, action: 'COVER', position_id: pos.id, status: pos.status,
        fill_price: pos.fill_price ?? null, target_weight: 0,
        last_close: closeOf.get(ticker) ?? null,
        reason: 'dropped out of the short book',
      });
    }
  }
  for (const r of sug.covers_or_exits || []) {
    if (!covers.some((x) => x.ticker === r.ticker)) {
      covers.push({ ticker: r.ticker, side: -1, action: 'COVER', target_weight: 0,
                    current_weight: r.current_weight,
                    last_close: closeOf.get(r.ticker) ?? null,
                    reason: 'model flagged a cover' });
    }
  }

  // Barrier obligations on open positions: the vertical exit is a scheduled MOO
  // at fill + h sessions (M5.2) — it is due regardless of what the model says.
  // A short's vertical is a buy-to-cover.
  const dueExits = [];
  for (const pos of [...heldL.values(), ...heldS.values()]) {
    if (pos.status !== 'open' || !pos.fill_date) continue;
    const h = pos.max_hold_sessions ?? cfg.barrier.h_days;
    const verticalDate = sellByFrom(pos.fill_date, h);
    if (verticalDate && ctx.next_open && verticalDate <= ctx.next_open) {
      const short = Number(pos.side) < 0;
      dueExits.push({
        ticker: pos.ticker, side: short ? -1 : 1, position_id: pos.id,
        action: short ? 'COVER (time barrier)' : 'EXIT (time barrier)',
        fill_date: pos.fill_date, vertical_date: verticalDate,
        reason: `${h}-session vertical barrier reached — market-on-open ${short ? 'cover' : 'exit'}`,
      });
    }
  }

  const stale = Boolean(ctx.last_completed_close
    && sug.as_of_close && sug.as_of_close < ctx.last_completed_close);

  return {
    session: ctx,
    signals: {
      as_of_close: sug.as_of_close,
      fresh: !stale,
      stale_reason: stale
        ? `Signals are from the ${sug.as_of_close} close, but ${ctx.last_completed_close} `
          + 'has since closed. Re-run the predict job before acting on these.'
        : null,
      execute_at: sug.execute_at,
    },
    counts: { buy: buys.length, sell: sells.length, hold: holds.length,
              short: shorts.length, cover: covers.length,
              due_exit: dueExits.length, held_total: heldL.size + heldS.size },
    // Sizing basis for the plain-English view: everything above is scaled to
    // the paper book's NAV, so the page can say "shares" and "dollars".
    plan: {
      nav,
      invest_total: buys.reduce((a, r) => a + (r.est_cost ?? 0), 0),
      short_total: shorts.reduce((a, r) => a + (r.est_cost ?? 0), 0),
    },
    buys, sells, holds, due_exits: dueExits, shorts, covers,
    gate_warning: 'The G-11 gates on this book return ITERATE — research output, '
      + 'not a recommendation to trade.',
    holdings_source: `the paper book (${storeLocation()}). Positions you hold `
      + 'elsewhere are invisible to this diff until they are recorded here.',
  };
}
