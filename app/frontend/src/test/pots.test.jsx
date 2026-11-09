import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { mockApi, fixtures, clone } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Pots from '../pages/Pots.jsx';

vi.mock('../api.js', () => ({ api: {} }));

const table = () => screen.getByRole('region', { name: 'Every stock' });

describe('Pots — backtest', () => {
  beforeEach(() => mockApi(api));

  it('opens on the backtest with the book totals', async () => {
    renderPage(<Pots />);
    expect(screen.getByRole('button', { name: 'Backtest: 2007–today' })).toHaveAttribute('aria-pressed', 'true');
    const totals = await screen.findByRole('region', { name: 'Backtest pots' });
    expect(within(totals).getByText('+525%')).toBeInTheDocument();
    expect(within(totals).getByText('$6,375,780')).toBeInTheDocument();
    expect(within(totals).getByText('88 / 14')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Total pot value and money put in' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Whole book return by year' })).toBeInTheDocument();
  });

  it('filters stocks by name and by outcome', async () => {
    const { user } = renderPage(<Pots />);
    await screen.findByRole('region', { name: 'Every stock' });
    expect(within(table()).getAllByRole('row')).toHaveLength(7);
    await user.selectOptions(within(table()).getByLabelText('Show'), 'down');
    const rows = within(table()).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('DDOG');
    await user.selectOptions(within(table()).getByLabelText('Show'), 'all');
    await user.type(within(table()).getByRole('searchbox'), 'nv');
    expect(within(table()).getAllByRole('row').slice(1).map((r) => r.cells[0].textContent)).toEqual(['NVDA']);
    await user.clear(within(table()).getByRole('searchbox'));
    await user.type(within(table()).getByRole('searchbox'), 'zzzz');
    expect(within(table()).getByText('No stocks match')).toBeInTheDocument();
  });

  it('opens a stock in a side panel without losing the table', async () => {
    const { user } = renderPage(<Pots />);
    await screen.findByRole('region', { name: 'Every stock' });
    await user.click(screen.getByRole('button', { name: 'Show AMD pot history' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAccessibleName(/^AMD: \$10,000 → \$1,848,762/);
    expect(within(dialog).getByRole('img', { name: 'AMD pot value' })).toBeInTheDocument();
    expect(within(dialog).getByRole('img', { name: 'AMD return by year' })).toBeInTheDocument();
    const amdRow = within(table()).getAllByRole('row').find((r) => r.textContent.startsWith('AMD'));
    expect(amdRow).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('also opens the panel from a row click', async () => {
    const { user } = renderPage(<Pots />);
    await screen.findByRole('region', { name: 'Every stock' });
    const row = within(table()).getAllByRole('row').find((r) => r.textContent.startsWith('DELL'));
    await user.click(row.cells[3]);
    expect(screen.getByRole('dialog')).toHaveAccessibleName(/^DELL:/);
  });
});

describe('Pots — live', () => {
  beforeEach(() => mockApi(api));

  it('switches to the live pots', async () => {
    const { user } = renderPage(<Pots />);
    await screen.findByRole('region', { name: 'Every stock' });
    await user.click(screen.getByRole('button', { name: 'Live: since the pots started' }));
    const pots = await screen.findByRole('region', { name: 'Every pot' });
    expect(within(pots).getAllByRole('row').length).toBeGreaterThan(100);
    expect(within(pots).getAllByText('Waiting in cash').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Live pots' })).toBeInTheDocument();
  });

  it('shows status badges and P/L for a book with positions', async () => {
    const s = clone(fixtures.suggestions);
    s.buckets = [
      { ticker: 'AAA', status: 'holding', pot_value: 11000, pnl: 1000, pnl_pct: 0.1, open_ret_pct: 0.05,
        open_fill_price: 10, last_close: 10.5, trades_closed: 2, wins: 1 },
      { ticker: 'BBB', status: 'due_exit', pot_value: 9000, pnl: -1000, pnl_pct: -0.1, last_close: 5,
        trades_closed: 1, wins: 0 },
      { ticker: 'CCC', status: 'entering', entering: 'fallback', pot_value: 10000, pnl: 0, pnl_pct: 0,
        last_close: 7, trades_closed: 0, wins: 0 },
    ];
    s.bucket_performance = { pnl_pct: 0, pnl: 0, start_value: 30000, value: 30000, winners: 1, losers: 1,
      invested: 20000, trades_closed: 3, realized_pnl: 0,
      curve: [{ date: '2026-10-01', value: 30000 }, { date: '2026-10-02', value: 30100 }] };
    mockApi(api, { suggestions: s });
    const { user } = renderPage(<Pots />);
    await user.click(screen.getByRole('button', { name: 'Live: since the pots started' }));
    const pots = await screen.findByRole('region', { name: 'Every pot' });
    expect(within(pots).getByText('Holding')).toBeInTheDocument();
    expect(within(pots).getByText('Sells at next open')).toBeInTheDocument();
    expect(within(pots).getByText('Buys at next open')).toBeInTheDocument();
    expect(within(pots).getByText('(cycle catch-up)')).toBeInTheDocument();
    const bbb = within(pots).getAllByRole('row').find((r) => r.cells[0].textContent === 'BBB');
    expect(bbb).toHaveTextContent('▼ −$1,000');
    for (const g of within(bbb).getAllByText('▼')) expect(g.parentElement).toHaveClass('neg');
    expect(screen.getByRole('img', { name: 'Whole book profit or loss' })).toBeInTheDocument();
    await user.selectOptions(within(pots).getByLabelText('Show'), 'invested');
    expect(within(pots).getAllByRole('row').slice(1).map((r) => r.cells[0].textContent)).toEqual(['AAA', 'BBB']);
  });

  it('explains when the book has no pots', async () => {
    const s = clone(fixtures.suggestions);
    delete s.buckets;
    mockApi(api, { suggestions: s });
    const { user } = renderPage(<Pots />);
    await user.click(screen.getByRole('button', { name: 'Live: since the pots started' }));
    expect(await screen.findByText('No live pots')).toBeInTheDocument();
  });
});
