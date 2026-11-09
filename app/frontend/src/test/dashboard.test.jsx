import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { mockApi, fixtures, clone } from './mockApi.js';
import { renderPage } from './render.jsx';
import { api } from '../api.js';
import Dashboard from '../pages/Dashboard.jsx';

vi.mock('../api.js', () => ({ api: {} }));

describe('Dashboard', () => {
  beforeEach(() => mockApi(api));

  it('leads with the verdict in plain words', async () => {
    renderPage(<Dashboard />);
    const verdict = await screen.findByRole('region', { name: 'Verdict' });
    expect(verdict).toHaveTextContent('ITERATE');
    expect(verdict).toHaveTextContent('Not ready to trade — keep improving');
    expect(within(verdict).getByText('3 of 6 checks pass')).toBeInTheDocument();
    expect(within(verdict).getByText('3 fail')).toBeInTheDocument();
  });

  it('draws the headline numbers against their bars', async () => {
    renderPage(<Dashboard />);
    const bar = await screen.findByRole('region', { name: 'Against the bar' });
    expect(within(bar).getByText('0.604')).toHaveClass('pos');
    expect(within(bar).getByText('-43.5%')).toHaveClass('neg');
    expect(within(bar).getByText('0.0374')).toBeInTheDocument();
    expect(within(bar).getByText('0.999')).toBeInTheDocument();
    expect(bar.querySelectorAll('.meter')).toHaveLength(4);
    const ret = screen.getByRole('region', { name: 'Returns' });
    expect(within(ret).getByText('8.2%')).toBeInTheDocument();
    expect(within(ret).getByText('10,475')).toBeInTheDocument();
  });

  it('lists every gate with a worded result', async () => {
    renderPage(<Dashboard />);
    const gates = await screen.findByRole('region', { name: 'Quality checks (the G-11 gates)' });
    const rows = within(gates).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(6);
    const advance = rows.find((r) => r.textContent.includes('G-11 advance: net Sharpe'));
    expect(within(advance).getByText('Fail')).toBeInTheDocument();
    expect(advance).toHaveTextContent('>= 0.8000');
    expect(within(gates).getByText('3 / 6 pass')).toBeInTheDocument();
  });

  it('compares against the free baselines', async () => {
    renderPage(<Dashboard />);
    const bl = await screen.findByRole('region', { name: 'Does it beat doing the simple thing?' });
    expect(within(bl).getByText('This strategy')).toBeInTheDocument();
    expect(within(bl).getByText('SPY buy & hold')).toBeInTheDocument();
    expect(within(bl).getByText('Basic momentum recipe')).toBeInTheDocument();
    expect(within(bl).getByText(/Extra return beyond what the market itself gave/)).toBeInTheDocument();
  });

  it('renders the evidence charts and provenance', async () => {
    renderPage(<Dashboard />);
    expect(await screen.findByRole('img', { name: 'Cumulative return of the strategy after costs' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Rank IC by model' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Sharpe by CPCV path' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Sharpe by per-trade cost' })).toBeInTheDocument();
    const prov = screen.getByRole('region', { name: 'Provenance' });
    expect(within(prov).getByText('64e992f62175')).toBeInTheDocument();
  });

  it('still renders without the equity curve', async () => {
    mockApi(api, { equity: new Error('equity not published yet') });
    renderPage(<Dashboard />);
    await screen.findByRole('region', { name: 'Verdict' });
    expect(screen.queryByRole('img', { name: /cumulative return/i })).toBeNull();
  });

  it.each([
    ['KILL', 'Do not trade — no real edge'],
    ['ADVANCE', 'Ready for practice trading'],
    ['LEAKAGE-AUDIT', 'Too good to be true — check for errors'],
  ])('words the %s verdict', async (verdict, title) => {
    const s = clone(fixtures.summary);
    s.gates.verdict = verdict;
    mockApi(api, { summary: s });
    renderPage(<Dashboard />);
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument();
  });

  it('explains how to publish when nothing is there yet', async () => {
    mockApi(api, { summary: new Error('summary not published yet') });
    renderPage(<Dashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('summary not published yet');
    expect(screen.getByText(/run the pipeline mirror step/)).toBeInTheDocument();
  });
});
