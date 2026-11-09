import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import { mockApi, fixtures, clone } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Today from '../pages/Today.jsx';

vi.mock('../api.js', () => ({ api: {} }));

const section = (name) => screen.getByRole('region', { name });
const rowFor = (region, ticker) => within(region).getAllByRole('row')
  .find((r) => within(r).queryByText(ticker, { selector: '.ticker' }));

/** A fresh, pre-open ticket with a short sleeve, a hold, and a tracked add-on. */
function richTicket() {
  const t = clone(fixtures.today);
  t.signals = { ...t.signals, fresh: true };
  t.session = { ...t.session, market_state: 'pre_open', open_already_passed: false };
  t.buys[1] = { ...t.buys[1], position_id: 'p00002', status: 'ordered' };
  t.shorts = [{ ...t.buys[0], ticker: 'ZZZ', side: -1, stop_pct: 12, profit_take_pct: -12,
    stop_price: 215.35, profit_take_price: 169.21, position_id: undefined }];
  t.holds = [{ ...t.buys[2], ticker: 'HOLDME', status: 'open', fill_price: 100, stop_price: 80,
    profit_take_price: 120, sell_by_date: '2026-12-01' }];
  t.counts = { ...t.counts, short: 1, hold: 1 };
  t.plan = { ...t.plan, short_total: 961 };
  return t;
}

describe('Today', () => {
  beforeEach(() => mockApi(api));

  it('dates the plan to the next session and sums it up in one sentence', async () => {
    renderPage(<Today />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Your plan for the Monday 9 Nov open' })).toBeInTheDocument();
    expect(screen.getByText(/sell 1 whose time is up, then sell 1 the model dropped, then buy 9 stocks for about \$7,972\./))
      .toBeInTheDocument();
    expect(screen.getByText(/Based on the Thursday 1 Oct close and your \$100,000 practice account/)).toBeInTheDocument();
  });

  it('warns loudly when the list is stale and when the open has passed', async () => {
    renderPage(<Today />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("This list is out of date — don't trade from it");
    expect(alert).toHaveTextContent('Signals are from the 2026-10-01 close');
    expect(screen.getByText("Today's opening price has already happened")).toBeInTheDocument();
    expect(screen.getByText('List is out of date')).toBeInTheDocument();
  });

  it('keeps the practice-only and one-pot notes, with their detail one click away', async () => {
    const { user } = renderPage(<Today />);
    await screen.findByText('Practice money only');
    expect(screen.getByText('One pot per stock')).toBeInTheDocument();
    expect(screen.queryByText(/only knows about stocks recorded in/)).toBeNull();
    await user.click(screen.getAllByRole('button', { name: 'More' })[0]);
    expect(screen.getByText(/only knows about stocks recorded in/)).toBeInTheDocument();
  });

  it('numbers the order sections in the order to place them', async () => {
    renderPage(<Today />);
    await screen.findByRole('region', { name: 'Buy' });
    const steps = [...document.querySelectorAll('.card-head h2')]
      .filter((h) => h.querySelector('.step'))
      .map((h) => `${h.querySelector('.step').textContent} ${h.childNodes[1].textContent}`);
    expect(steps).toEqual(['1 Close first — time is up', '2 Sell', '3 Buy']);
  });

  it('summarises the counts', async () => {
    renderPage(<Today />);
    const stats = await screen.findByRole('region', { name: 'Orders at a glance' });
    for (const label of ['Buy', 'Sell', 'Close — time is up', 'Do nothing', 'You own']) {
      expect(within(stats).getByText(label)).toBeInTheDocument();
    }
  });

  it('lists each buy as a broker ticket', async () => {
    renderPage(<Today />);
    const buys = await screen.findByRole('region', { name: 'Buy' });
    const ba = rowFor(buys, 'BA');
    expect(ba).toHaveTextContent('Buy 5 shares');
    expect(ba).toHaveTextContent('$192.28');
    expect(ba).toHaveTextContent('$961');
    expect(ba).toHaveTextContent('$148.29');
    expect(ba).toHaveTextContent('$236.27');
    expect(rowFor(buys, 'MRNA')).toHaveTextContent('no price triggers — just sell by the date');
    expect(within(buys).getByText(/All 9 buys together come to about/)).toBeInTheDocument();
  });

  it('tracks a trade in the paper book and confirms with a toast', async () => {
    const { user } = renderPage(<Today />);
    await screen.findByRole('region', { name: 'Buy' });
    await user.click(screen.getByRole('button', { name: 'Track BA in the practice book' }));
    expect(api.paperOpen).toHaveBeenCalledWith({
      ticker: 'BA', side: 1, target_weight: 0.0098, signal_date: '2026-10-01', ref_close: 192.28,
      stop_pct: -22.88, profit_take_pct: 22.88, trail_pct: 15.25, max_hold_sessions: 40,
      ensemble_rank: 0.1225,
    });
    expect(await screen.findByText(/BA is now tracked in your practice book/)).toBeInTheDocument();
    await waitFor(() => expect(api.today).toHaveBeenCalledTimes(2));
  });

  it('reports a rejected track request', async () => {
    mockApi(api, { paperOpen: new Error('kill switch tripped') });
    const { user } = renderPage(<Today />);
    await screen.findByRole('region', { name: 'Buy' });
    await user.click(screen.getByRole('button', { name: 'Track HD in the practice book' }));
    expect(await screen.findByText('HD: kill switch tripped')).toBeInTheDocument();
  });

  it('switches to the quant columns and back', async () => {
    const { user } = renderPage(<Today />);
    const buys = await screen.findByRole('region', { name: 'Buy' });
    expect(within(buys).queryByRole('columnheader', { name: /conviction/i })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Detailed view' }));
    expect(within(buys).getByRole('columnheader', { name: /conviction/i })).toBeInTheDocument();
    expect(within(buys).getByText(/Quant view/)).toBeInTheDocument();
    expect(rowFor(buys, 'BA')).toHaveTextContent('-15.25%');
    await user.click(screen.getByRole('button', { name: 'Simple view' }));
    expect(within(buys).getByRole('columnheader', { name: /sell if it drops to/i })).toBeInTheDocument();
  });

  it('shows the how-to on demand', async () => {
    const { user } = renderPage(<Today />);
    const btn = await screen.findByRole('button', { name: 'How do I use this?' });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    await user.click(btn);
    expect(screen.getByRole('region', { name: 'How to use this page' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Hide help' }));
    expect(screen.queryByRole('region', { name: 'How to use this page' })).toBeNull();
  });

  it('sorts the buy list', async () => {
    const { user } = renderPage(<Today />);
    const buys = await screen.findByRole('region', { name: 'Buy' });
    await user.click(within(buys).getByRole('button', { name: /latest close/i }));
    const first = within(buys).getAllByRole('row')[1];
    expect(first).toHaveTextContent('LIN');   // $469.45 is the highest close
  });

  it('handles a fresh ticket with shorts, holds and an already-tracked add-on', async () => {
    mockApi(api, { today: richTicket() });
    const { user } = renderPage(<Today />);
    await screen.findByRole('region', { name: 'Buy' });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('List is current')).toBeInTheDocument();

    const ddog = rowFor(section('Buy'), 'DDOG');
    expect(within(ddog).getByText('Already tracked')).toBeInTheDocument();
    expect(within(ddog).queryByRole('button', { name: /track/i })).toBeNull();
    expect(ddog).toHaveTextContent('adds a lot to the DDOG order you track');

    const shorts = section('Sell short');
    expect(rowFor(shorts, 'ZZZ')).toHaveTextContent('Sell short 5 shares');
    expect(within(shorts).getByRole('columnheader', { name: /buy back if it climbs to/i })).toBeInTheDocument();

    const holds = section('Do nothing');
    expect(within(holds).queryByRole('table')).toBeNull();
    await user.click(within(holds).getByRole('button', { name: 'Show' }));
    expect(rowFor(holds, 'HOLDME')).toHaveTextContent('keep holding it');
  });

  it('shows a retryable error when the API fails', async () => {
    mockApi(api, { today: new Error('Failed to fetch') });
    const { user } = renderPage(<Today />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch');
    mockApi(api);
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByRole('heading', { level: 1, name: /your plan for the/i })).toBeInTheDocument();
  });

  it('explains a ticket that the bundle could not build', async () => {
    mockApi(api, { today: { session: fixtures.today.session, error: 'no suggestions in the report bundle' } });
    renderPage(<Today />);
    expect(await screen.findByRole('alert')).toHaveTextContent('no suggestions in the report bundle');
    expect(screen.getByText('Run the predict job, then rebuild the bundle.')).toBeInTheDocument();
  });
});
