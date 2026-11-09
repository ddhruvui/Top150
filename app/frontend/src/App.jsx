import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';
import Icon from './components/Icon.jsx';
import { Segmented } from './components/Bits.jsx';
import { ToastProvider } from './components/Toast.jsx';
import Today from './pages/Today.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Suggestions from './pages/Suggestions.jsx';
import Backtest from './pages/Backtest.jsx';
import Paper from './pages/Paper.jsx';
import Pots from './pages/Pots.jsx';

/* Pages grouped by the job they do: "Trade" is what you act on each morning,
   "Research" is the evidence behind it. Hash routing (#today, …) stays, so
   the static host needs no rewrites and old links keep working. */
export const PAGES = [
  { id: 'today', label: 'Today', group: 'Trade', icon: 'today', Comp: Today },
  { id: 'paper', label: 'Paper trading', group: 'Trade', icon: 'book', Comp: Paper },
  { id: 'dashboard', label: 'Dashboard', group: 'Research', icon: 'gauge', Comp: Dashboard },
  { id: 'pots', label: 'Pots', group: 'Research', icon: 'coins', Comp: Pots },
  { id: 'suggestions', label: 'Suggestions', group: 'Research', icon: 'list', Comp: Suggestions },
  { id: 'backtest', label: 'Backtest', group: 'Research', icon: 'history', Comp: Backtest },
];
const GROUPS = ['Trade', 'Research'];

const pageFromHash = () => {
  const id = window.location.hash.slice(1);
  return PAGES.some((p) => p.id === id) ? id : 'today';
};

function readTheme() {
  try { return localStorage.getItem('theme') || 'auto'; } catch { return 'auto'; }
}

/** "2 Oct 2026, 14:10 UTC" + a plain-language age. */
export function describeBuilt(iso, now = new Date()) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const when = `${d.getUTCDate()} ${d.toLocaleString('en', { month: 'short', timeZone: 'UTC' })} ${
    d.getUTCFullYear()}, ${String(d.getUTCHours()).padStart(2, '0')}:${
    String(d.getUTCMinutes()).padStart(2, '0')} UTC`;
  const days = Math.floor((now - d) / 86400e3);
  const age = days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
  return { when, age, days };
}

function Sidebar({ page, open, onClose, health, theme, setTheme }) {
  const built = describeBuilt(health?.generated_utc);
  const tone = !health ? 'bad' : !built ? 'warn' : built.days > 3 ? 'warn' : 'ok';
  return (
    <aside className="sidebar" data-open={open} aria-label="Main navigation" id="sidebar">
      <div style={{ display: 'flex', alignItems: 'flex-start' }}>
        <a className="brand" href="#today" onClick={onClose}>
          <span className="brand-mark" aria-hidden="true"><Icon name="trend" size={17} stroke={2.4} /></span>
          <span>
            <span className="brand-name">Top150</span>
            <span className="brand-sub" style={{ display: 'block' }}>EOD swing &amp; position · research console</span>
          </span>
        </a>
        <button type="button" className="btn ghost icon drawer-close" onClick={onClose}
                aria-label="Close menu" style={{ marginLeft: 'auto' }}>
          <Icon name="x" size={18} />
        </button>
      </div>
      <nav aria-label="Pages">
        {GROUPS.map((g) => (
          <div className="nav-group" key={g}>
            <div className="nav-group-label">{g}</div>
            {PAGES.filter((p) => p.group === g).map((p) => (
              <a key={p.id} href={`#${p.id}`} className="nav-link" onClick={onClose}
                 aria-current={page === p.id ? 'page' : undefined}>
                <Icon name={p.icon} size={16} />
                {p.label}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="freshness" title={health?.generated_utc || ''}>
          <div className="row">
            <span className={`dot ${tone}`} aria-hidden="true" />
            {health ? (built ? 'Report built' : 'No report published yet') : 'API unreachable'}
          </div>
          {built && <div className="sub">{built.when}</div>}
          {built && <div className="sub">{built.age}</div>}
        </div>
        <Segmented label="Colour theme" value={theme} onChange={setTheme} full
                   options={[['auto', '', 'monitor', 'Match system theme'],
                             ['light', '', 'sun', 'Light theme'],
                             ['dark', '', 'moon', 'Dark theme']]} />
      </div>
    </aside>
  );
}

export default function App() {
  const [page, setPage] = useState(pageFromHash);
  const [health, setHealth] = useState(null);
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const mainRef = useRef(null);
  const shown = useRef(null);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); }, []);

  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('theme', theme); } catch { /* private mode */ }
  }, [theme]);

  const active = PAGES.find((p) => p.id === page) || PAGES[0];

  // A new page starts at the top, with focus on its content (not the nav),
  // and the tab title names it.
  useEffect(() => {
    document.title = `${active.label} · Top150`;
    setMenu(false);
    const prev = shown.current;
    shown.current = active.id;
    if (prev == null || prev === active.id) return;   // first paint: leave focus alone
    window.scrollTo(0, 0);
    mainRef.current?.focus({ preventScroll: true });
  }, [active]);

  useEffect(() => {
    if (!menu) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setMenu(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menu]);

  const Active = active.Comp;

  return (
    <ToastProvider>
      <a className="skip-link" href="#main" onClick={(e) => {
        e.preventDefault(); mainRef.current?.focus();
      }}>Skip to content</a>
      <div className="shell">
        <Sidebar page={page} open={menu} onClose={() => setMenu(false)}
                 health={health} theme={theme} setTheme={setTheme} />
        {menu && <div className="scrim" onClick={() => setMenu(false)} aria-hidden="true" />}
        <div className="content">
          <header className="topbar">
            <button type="button" className="btn ghost icon" onClick={() => setMenu(true)}
                    aria-label="Open menu" aria-expanded={menu} aria-controls="sidebar">
              <Icon name="menu" size={20} />
            </button>
            <span className="brand-mark" aria-hidden="true"><Icon name="trend" size={15} stroke={2.4} /></span>
            <span className="topbar-title">{active.label}</span>
          </header>
          <main id="main" ref={mainRef} tabIndex={-1} aria-labelledby="page-title">
            <Active key={active.id} />
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
