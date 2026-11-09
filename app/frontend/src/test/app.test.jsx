import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockApi } from './mockApi.js';
import { api } from '../api.js';
import App, { PAGES } from '../App.jsx';

vi.mock('../api.js', () => ({ api: {} }));   // hoisted above the imports by vitest

const go = async (hash) => {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
};

describe('app shell', () => {
  beforeEach(() => mockApi(api));

  it('groups the six pages into Trade and Research', async () => {
    render(<App />);
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    const links = within(nav).getAllByRole('link').map((a) => a.textContent);
    expect(links).toEqual(['Today', 'Paper trading', 'Dashboard', 'Pots', 'Suggestions', 'Backtest']);
    expect(within(nav).getByText('Trade')).toBeInTheDocument();
    expect(within(nav).getByText('Research')).toBeInTheDocument();
    expect(PAGES.map((p) => p.id)).toEqual(['today', 'paper', 'dashboard', 'pots', 'suggestions', 'backtest']);
    await screen.findByRole('heading', { level: 1, name: /your plan for the/i });
  });

  it('lands on Today, marks it current and names the tab', async () => {
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: /your plan for the/i });
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    expect(within(nav).getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page');
    expect(document.title).toBe('Today · Top150');
  });

  it('routes by hash, scrolls to the top and focuses the new page', async () => {
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: /your plan for the/i });
    window.scrollTo.mockClear();
    await go('#dashboard');
    expect(await screen.findByRole('heading', { level: 1, name: 'Strategy dashboard' })).toBeInTheDocument();
    expect(document.title).toBe('Dashboard · Top150');
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
    expect(screen.getByRole('main')).toHaveFocus();
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    expect(within(nav).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Today' })).not.toHaveAttribute('aria-current');
  });

  it.each([
    ['#paper', 'Your practice book'],
    ['#pots', 'Pots'],
    ['#suggestions', "The model's full pick list"],
    ['#backtest', 'How the strategy did in testing'],
  ])('renders %s', async (hash, title) => {
    window.location.hash = hash;
    render(<App />);
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument();
  });

  it('falls back to Today for an unknown hash', async () => {
    window.location.hash = '#nope';
    render(<App />);
    expect(await screen.findByRole('heading', { level: 1, name: /your plan for the/i })).toBeInTheDocument();
  });

  it('shows when the report was built', async () => {
    render(<App />);
    expect(await screen.findByText('Report built')).toBeInTheDocument();
    expect(screen.getByText('2 Oct 2026, 14:10 UTC')).toBeInTheDocument();
    expect(screen.getByText(/days ago|today|yesterday/)).toBeInTheDocument();
  });

  it('says so when the API is unreachable', async () => {
    mockApi(api, { health: new Error('fetch failed') });
    render(<App />);
    expect(await screen.findByText('API unreachable')).toBeInTheDocument();
  });

  it('switches and remembers the colour theme', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Dark theme' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Light theme' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    await user.click(screen.getByRole('button', { name: 'Match system theme' }));
    expect(document.documentElement).not.toHaveAttribute('data-theme');
    expect(localStorage.getItem('theme')).toBe('auto');
  });

  it('restores a saved theme on load', () => {
    localStorage.setItem('theme', 'dark');
    render(<App />);
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('opens and closes the narrow-screen menu', async () => {
    const user = userEvent.setup();
    render(<App />);
    const toggle = screen.getByRole('button', { name: 'Open menu' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('sidebar')).toHaveAttribute('data-open', 'true');
    await user.keyboard('{Escape}');
    expect(document.getElementById('sidebar')).toHaveAttribute('data-open', 'false');
  });

  it('offers a skip link to the content', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('link', { name: 'Skip to content' }));
    expect(screen.getByRole('main')).toHaveFocus();
  });
});
