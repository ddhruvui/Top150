import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import { mockApi } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Backtest from '../pages/Backtest.jsx';

vi.mock('../api.js', () => ({ api: {} }));

const ledger = () => screen.getByRole('region', { name: 'Every tested trade' });
const lastQuery = () => api.trades.mock.calls.at(-1)[0];

describe('Backtest', () => {
  beforeEach(() => mockApi(api));

  it('shows the totals and the evidence charts', async () => {
    renderPage(<Backtest />);
    const totals = await screen.findByRole('region', { name: 'Backtest totals' });
    expect(within(totals).getByText('10,475')).toBeInTheDocument();
    expect(within(totals).getByText(/40-day limit/)).toBeInTheDocument();
    for (const name of ['Average net return by conviction decile', 'Trades by exit type',
      'Average net return by holding length', 'Win rate by year', 'Average net return by year',
      'Distribution of trade returns']) {
      expect(screen.getByRole('img', { name })).toBeInTheDocument();
    }
  });

  it('pages through the ledger with a readable range', async () => {
    const { user } = renderPage(<Backtest />);
    await screen.findByRole('region', { name: 'Every tested trade' });
    expect(await within(ledger()).findByText('1–50 of 4,000 matching')).toBeInTheDocument();
    expect(within(ledger()).getAllByRole('row')).toHaveLength(13);
    expect(within(ledger()).getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(within(ledger()).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ offset: 50, limit: 50 }));
    expect(await within(ledger()).findByText('51–100 of 4,000 matching')).toBeInTheDocument();
  });

  it('re-queries from page one when a filter changes', async () => {
    const { user } = renderPage(<Backtest />);
    await screen.findByRole('region', { name: 'Every tested trade' });
    await user.click(within(ledger()).getByRole('button', { name: 'Next page' }));
    await user.selectOptions(screen.getByLabelText('How the trade ended'), 'upper');
    await waitFor(() => expect(lastQuery()).toMatchObject({ exit: 'upper', offset: 0 }));
    await user.selectOptions(screen.getByLabelText('Wins or losses'), 'loss');
    await waitFor(() => expect(lastQuery()).toMatchObject({ exit: 'upper', outcome: 'loss', offset: 0 }));
  });

  it('debounces the ticker filter and can clear everything', async () => {
    const { user } = renderPage(<Backtest />);
    await screen.findByRole('region', { name: 'Every tested trade' });
    const before = api.trades.mock.calls.length;
    await user.type(screen.getByRole('searchbox', { name: 'Filter by ticker' }), 'AAPL');
    await waitFor(() => expect(lastQuery()).toMatchObject({ ticker: 'AAPL', offset: 0 }));
    expect(api.trades.mock.calls.length - before).toBeLessThan(4);   // not one query per key
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ ticker: '', exit: '', outcome: '' }));
    expect(screen.getByRole('searchbox', { name: 'Filter by ticker' })).toHaveValue('');
  });

  it('sorts the ledger on the server', async () => {
    const { user } = renderPage(<Backtest />);
    await screen.findByRole('region', { name: 'Every tested trade' });
    const btn = within(ledger()).getByRole('button', { name: 'Profit / loss' });
    await user.click(btn);
    await waitFor(() => expect(lastQuery()).toMatchObject({ sortKey: 'exit_ret_net', sortDir: 'desc', offset: 0 }));
    expect(btn.closest('th')).toHaveAttribute('aria-sort', 'descending');
    await user.click(btn);
    await waitFor(() => expect(lastQuery()).toMatchObject({ sortKey: 'exit_ret_net', sortDir: 'asc' }));
    await user.click(btn);
    await waitFor(() => expect(lastQuery()).toMatchObject({ sortKey: '', sortDir: '' }));
  });

  it('shows worded outcomes and signed returns', async () => {
    renderPage(<Backtest />);
    await screen.findByRole('region', { name: 'Every tested trade' });
    const first = (await within(ledger()).findAllByRole('row'))[1];
    expect(within(first).getByText('Trailing stop')).toBeInTheDocument();
    expect(first).toHaveTextContent(/▼ -\d+\.\d\d%|▲ \+\d+\.\d\d%/);
  });

  it('says when no trades match', async () => {
    mockApi(api, { trades: { rows: [], total: 0, note: 'none' } });
    renderPage(<Backtest />);
    expect(await screen.findByText('No trades match these filters')).toBeInTheDocument();
  });

  it('points at the pipeline when the ledger is missing', async () => {
    mockApi(api, { tradesSummary: new Error('trades not published yet') });
    renderPage(<Backtest />);
    expect(await screen.findByRole('alert')).toHaveTextContent('trades not published yet');
    expect(screen.getByText('scripts/launch_top150.sh stage3')).toBeInTheDocument();
  });
});
