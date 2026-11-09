import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import { mockApi, fixtures, clone } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Paper from '../pages/Paper.jsx';

vi.mock('../api.js', () => ({ api: {} }));

/** The fixture book (ON open) plus one order waiting to fill and one closed trade. */
function busyBook() {
  const p = clone(fixtures.paper);
  p.positions.push(
    { ...p.positions[0], id: 'p2', ticker: 'BA', status: 'ordered', shares: 5, ref_close: 192.28,
      stop_pct: -22.88, profit_take_pct: 22.88, signal_date: '2026-10-01', fill_price: undefined },
    { ...p.positions[0], id: 'p3', ticker: 'XOM', status: 'closed', fill_date: '2026-10-02',
      exit_date: '2026-10-20', exit_price: 170, exit_reason: 'profit_take', holding_days: 12, ret_net: 0.0405 },
  );
  p.stats.counts = { ordered: 1, open: 1, closed: 1 };
  return p;
}

describe('Paper trading', () => {
  beforeEach(() => mockApi(api));

  it('shows the book at a glance and the three practice-stage instruments', async () => {
    renderPage(<Paper />);
    const glance = await screen.findByRole('region', { name: 'Practice book' });
    expect(within(glance).getByText('Open')).toBeInTheDocument();
    expect(within(glance).getByText(/the backtest scored 0\.60/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Do you get the price you expect?' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Fills recorded toward adoption' }))
      .toHaveAttribute('aria-valuemax', '60');
    expect(screen.getByText('Not tripped')).toBeInTheDocument();
    expect(screen.getByText('Not enough history yet')).toBeInTheDocument();
  });

  it('lists open trades and an empty finished list with guidance', async () => {
    renderPage(<Paper />);
    const open = await screen.findByRole('region', { name: "Trades you're in" });
    expect(within(open).getByText('ON')).toBeInTheDocument();
    expect(within(open).getByText('48.71')).toHaveClass('neg');
    const done = screen.getByRole('region', { name: 'Finished trades' });
    expect(within(done).getByText('No finished trades yet')).toBeInTheDocument();
    expect(within(done).getByRole('link', { name: 'Today page' })).toHaveAttribute('href', '#today');
  });

  it('records a fill, validating the price first', async () => {
    mockApi(api, { paper: busyBook() });
    const { user } = renderPage(<Paper />);
    const waiting = await screen.findByRole('region', { name: 'Waiting to fill' });
    const record = within(waiting).getByRole('button', { name: 'Record it' });
    expect(record).toBeDisabled();

    await user.type(within(waiting).getByLabelText('Price you paid for BA'), 'abc');
    await user.click(record);
    expect(await within(waiting).findByRole('alert')).toHaveTextContent('Enter the price you paid');
    expect(api.paperFill).not.toHaveBeenCalled();

    await user.clear(within(waiting).getByLabelText('Price you paid for BA'));
    await user.type(within(waiting).getByLabelText('Price you paid for BA'), '193.10');
    await user.type(within(waiting).getByLabelText('Official open for BA'), '192.90');
    await user.click(record);
    expect(api.paperFill).toHaveBeenCalledWith('p2', { fill_price: 193.1, official_open: 192.9 });
    expect(await screen.findByText('BA: fill recorded at 193.10.')).toBeInTheDocument();
  });

  it('sends no official open when it is left blank', async () => {
    mockApi(api, { paper: busyBook() });
    const { user } = renderPage(<Paper />);
    const waiting = await screen.findByRole('region', { name: 'Waiting to fill' });
    await user.type(within(waiting).getByLabelText('Price you paid for BA'), '193{Enter}');
    expect(api.paperFill).toHaveBeenCalledWith('p2', { fill_price: 193, official_open: null });
  });

  it('asks before cancelling an order', async () => {
    mockApi(api, { paper: busyBook() });
    const { user } = renderPage(<Paper />);
    const waiting = await screen.findByRole('region', { name: 'Waiting to fill' });
    await user.click(within(waiting).getByRole('button', { name: 'Cancel' }));
    expect(api.paperRemove).not.toHaveBeenCalled();
    await user.click(within(waiting).getByRole('button', { name: 'Cancel order?' }));
    expect(api.paperRemove).toHaveBeenCalledWith('p2');
    expect(await screen.findByText('BA: order cancelled.')).toBeInTheDocument();
  });

  it('closes a trade with a reason', async () => {
    const { user } = renderPage(<Paper />);
    const open = await screen.findByRole('region', { name: "Trades you're in" });
    await user.type(within(open).getByLabelText('Price you sold ON at'), '80.5');
    await user.selectOptions(within(open).getByLabelText('Why you sold ON'), 'profit_take');
    await user.click(within(open).getByRole('button', { name: 'Sold it' }));
    expect(api.paperClose).toHaveBeenCalledWith('p00001', { exit_price: 80.5, reason: 'profit_take' });
    expect(await screen.findByText('ON: closed at 80.50.')).toBeInTheDocument();
    await waitFor(() => expect(api.paper).toHaveBeenCalledTimes(2));
  });

  it('shows the server error when a close is rejected', async () => {
    mockApi(api, { paperClose: new Error('ON is not open') });
    const { user } = renderPage(<Paper />);
    const open = await screen.findByRole('region', { name: "Trades you're in" });
    await user.type(within(open).getByLabelText('Price you sold ON at'), '80');
    await user.click(within(open).getByRole('button', { name: 'Sold it' }));
    expect(await within(open).findByRole('alert')).toHaveTextContent('ON is not open');
  });

  it('lists finished trades with signed results', async () => {
    mockApi(api, { paper: busyBook() });
    renderPage(<Paper />);
    const done = await screen.findByRole('region', { name: 'Finished trades' });
    const xom = within(done).getAllByRole('row')[1];
    expect(xom).toHaveTextContent('XOM');
    expect(xom).toHaveTextContent('profit take');
    expect(xom).toHaveTextContent('▲ +4.05%');
  });

  it('saves settings explicitly and only when they changed', async () => {
    const { user } = renderPage(<Paper />);
    const settings = await screen.findByRole('region', { name: 'Settings' });
    const save = within(settings).getByRole('button', { name: 'Save settings' });
    expect(save).toBeDisabled();
    const pot = within(settings).getByLabelText('Practice pot ($)');
    expect(pot).toHaveValue('100000');
    await user.clear(pot);
    await user.type(pot, '25000');
    await user.type(within(settings).getByLabelText('Real account size ($)'), '30000');
    expect(save).toBeEnabled();
    await user.click(save);
    expect(api.paperSettings).toHaveBeenCalledWith({ nav: 25000, account_equity: 30000 });
    expect(await screen.findByText(/Settings saved/)).toBeInTheDocument();
  });

  it('will not save an invalid pot size', async () => {
    const { user } = renderPage(<Paper />);
    const settings = await screen.findByRole('region', { name: 'Settings' });
    await user.clear(within(settings).getByLabelText('Practice pot ($)'));
    await user.type(within(settings).getByLabelText('Practice pot ($)'), '-5');
    expect(within(settings).getByRole('button', { name: 'Save settings' })).toBeDisabled();
  });

  it('explains how to recover when the API is unreachable', async () => {
    mockApi(api, { paper: new Error('Failed to fetch') });
    renderPage(<Paper />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch');
    expect(screen.getByText(/Check VITE_API_BASE/)).toBeInTheDocument();
  });
});
