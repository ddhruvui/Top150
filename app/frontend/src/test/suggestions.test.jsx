import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { mockApi, fixtures, clone } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Suggestions from '../pages/Suggestions.jsx';

vi.mock('../api.js', () => ({ api: {} }));

const picks = () => screen.getByRole('region', { name: 'Every pick' });

describe('Suggestions', () => {
  beforeEach(() => mockApi(api));

  it('summarises the book and links to Today for the actual orders', async () => {
    renderPage(<Suggestions />);
    expect(await screen.findByRole('heading', { level: 1, name: "The model's full pick list" })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Today page' })).toHaveAttribute('href', '#today');
    const book = screen.getByRole('region', { name: 'The book' });
    expect(within(book).getByText('2026-10-01')).toBeInTheDocument();
    expect(within(book).getByText('9')).toBeInTheDocument();
  });

  it('flags picks whose triggers are too wide to ever fire', async () => {
    renderPage(<Suggestions />);
    expect(await screen.findByText(/1 of 9 picks have sell triggers wider than ±40% \(widest ±107%\)/)).toBeInTheDocument();
    const mrna = within(picks()).getAllByRole('row').find((r) => r.textContent.includes('MRNA'));
    expect(within(mrna).getByText(/40 days — only exit/)).toBeInTheDocument();
  });

  it('filters by ticker and says when nothing matches', async () => {
    const { user } = renderPage(<Suggestions />);
    await screen.findByRole('region', { name: 'Every pick' });
    expect(within(picks()).getAllByRole('row')).toHaveLength(10);
    await user.type(screen.getByRole('searchbox', { name: 'Filter by ticker' }), 'dd');
    expect(within(picks()).getAllByRole('row')).toHaveLength(2);
    expect(within(picks()).getByText('DDOG')).toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox', { name: 'Filter by ticker' }));
    await user.type(screen.getByRole('searchbox', { name: 'Filter by ticker' }), 'qqq');
    expect(within(picks()).getByText('No matches')).toBeInTheDocument();
  });

  it('marks names already in the paper book and tracks new ones', async () => {
    const paper = clone(fixtures.paper);
    paper.positions.push({ ...paper.positions[0], id: 'p2', ticker: 'HD', status: 'ordered' });
    mockApi(api, { paper });
    const { user } = renderPage(<Suggestions />);
    await screen.findByRole('region', { name: 'Every pick' });
    const hd = within(picks()).getAllByRole('row').find((r) => r.textContent.includes('HD'));
    expect(await within(hd).findByText('Already tracked')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Track PEP in the practice book' }));
    expect(api.paperOpen).toHaveBeenCalledWith(expect.objectContaining({
      ticker: 'PEP', side: 1, signal_date: '2026-10-01', ref_close: 125.6,
    }));
    expect(await screen.findByText(/PEP is now tracked in your practice book/)).toBeInTheDocument();
    expect(api.paper).toHaveBeenCalledTimes(2);
  });

  it('lists shorts with their own badge when the book has them', async () => {
    const s = clone(fixtures.suggestions);
    s.shorts_or_increases = [{ ...s.buys_or_increases[0], ticker: 'SHRT', side: -1, stop_pct: 10, profit_take_pct: -10 }];
    s.covers_or_exits = [{ ticker: 'CVR', last_close: 10, current_weight: 0.01 }];
    mockApi(api, { suggestions: s });
    renderPage(<Suggestions />);
    await screen.findByRole('region', { name: 'Every pick' });
    const row = within(picks()).getAllByRole('row').find((r) => r.textContent.includes('SHRT'));
    expect(within(row).getByText('Sell short')).toBeInTheDocument();
    const exits = screen.getByRole('region', { name: 'Get out of these' });
    expect(within(exits).getByText('Buy back')).toBeInTheDocument();
  });
});
