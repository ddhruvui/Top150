/* Shared building blocks for every page.
   Delta is the profit/loss primitive: hue is green/red per market convention,
   but the SIGN and the ▲/▼ glyph carry the meaning on their own — green vs red
   measures ΔE 4.1 under deuteranopia, so colour is never the only channel. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { arrow, signClass, fmtSignedPct, fmtNum } from './Chart.jsx';
import Icon from './Icon.jsx';

/* ------------------------------------------------------- sortable tables */

/** Client-side table sorting. Click cycle per column: desc → asc → original
 *  order. Nulls sort last in both directions so gaps never bury the data. */
export function useSort(rows) {
  const [sort, setSort] = useState({ key: null, dir: null });
  const sorted = useMemo(() => {
    if (!sort.key || !sort.dir) return rows;
    const { key, dir } = sort;
    return [...rows].sort((x, y) => {
      const a = x[key];
      const b = y[key];
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      const c = typeof a === 'number' && typeof b === 'number'
        ? a - b : String(a).localeCompare(String(b));
      return dir === 'asc' ? c : -c;
    });
  }, [rows, sort]);
  const onSort = (key) => setSort((s) => (s.key !== key
    ? { key, dir: 'desc' }
    : s.dir === 'desc' ? { key, dir: 'asc' } : { key: null, dir: null }));
  return { rows: sorted, sort, onSort };
}

/** Sortable header cell. `k` is the row field to sort by; omit it for
 *  non-sortable columns (action buttons, free text). The control is a real
 *  button, so keyboard users can sort too. */
export function Th({ k, sort, onSort, num, children, className = '' }) {
  const cls = `${num ? 'n' : ''} ${className}`.trim() || undefined;
  if (!k) return <th className={cls} scope="col">{children}</th>;
  const active = sort?.key === k && sort?.dir;
  return (
    <th className={cls} scope="col"
        aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className="sort-btn" onClick={() => onSort(k)}>
        {children}
        <span className="ind" aria-hidden="true">
          {active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  );
}

/* ------------------------------------------------------------ primitives */

export function Delta({ value, pct = true, digits = 2, suffix = '', title }) {
  if (value == null || Number.isNaN(value)) return <span className="muted">—</span>;
  const text = pct ? fmtSignedPct(value, digits)
    : `${value >= 0 ? '+' : ''}${fmtNum(value, digits)}${suffix}`;
  return (
    <span className={`${signClass(value)} num`} title={title}>
      <span aria-hidden="true" style={{ fontSize: '0.8em' }}>{arrow(value)}</span> {text}
    </span>
  );
}

/** Where a metric sits against its gates — a bullet bar with labelled marks. */
export function Meter({ value, min = 0, max = 1, marks = [], tone }) {
  if (value == null || Number.isNaN(value)) return null;
  const pct = (v) => `${Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100))}%`;
  return (
    <div className="meter" aria-hidden="true">
      <div className={`fill ${tone || ''}`} style={{ width: pct(value) }} />
      {marks.map((m) => (
        <div key={m.label} className="mark" style={{ left: pct(m.at) }}>
          <span>{m.label}</span>
        </div>
      ))}
    </div>
  );
}

export function StatTile({ label, value, sub, tone, meter, size, icon }) {
  return (
    <div className={`tile ${size || ''}`}>
      <div className="label">{icon && <Icon name={icon} size={14} />}{label}</div>
      <div className={`value num ${tone || ''}`}>{value}</div>
      {meter && <Meter {...meter} />}
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/** A row of stat tiles sharing one surface (hairline dividers, no box soup). */
export function Stats({ children, label }) {
  return <section className="stats" aria-label={label}>{children}</section>;
}

export function Badge({ kind = 'neutral', glyph, children, title }) {
  const g = glyph ?? (kind === 'pass' ? '✓' : kind === 'fail' ? '✕' : null);
  return (
    <span className={`badge ${kind}`} title={title}>
      {g && <span className="g" aria-hidden="true">{g}</span>}{children}
    </span>
  );
}

/** Barrier outcome — word + glyph, so the class is never colour-only. */
export function OutcomeBadge({ hit }) {
  const map = {
    upper: ['pass', '▲', 'Hit profit target'],
    lower: ['fail', '▼', 'Hit stop-loss'],
    vertical: ['neutral', '⏱', 'Time limit'],
    trail: ['info', '⤴', 'Trailing stop'],
    flat: ['neutral', '≈', 'Flat exit'],
    censored: ['neutral', '⋯', 'Still open at end'],
  };
  const [kind, glyph, label] = map[hit] || ['neutral', '•', hit || '—'];
  return <Badge kind={kind} glyph={glyph}>{label}</Badge>;
}

/* ---------------------------------------------------------------- layout */

/** Page title block. With `meta`, the actions share a toolbar row with it
 *  under the lede (so the lede gets the full width); without, they sit to the
 *  right of the title. */
export function PageHeader({ eyebrow, icon, title, lede, meta, actions }) {
  return (
    <header className="page-head">
      <div style={{ minWidth: 0, flex: '1 1 480px' }}>
        {eyebrow && (
          <div className="eyebrow">{icon && <Icon name={icon} size={14} />}{eyebrow}</div>
        )}
        <h1 id="page-title">{title}</h1>
        {lede && <p className="lede">{lede}</p>}
        {meta && (
          <div className="head-bar">
            <div className="meta">{meta}</div>
            {actions && <div className="page-actions">{actions}</div>}
          </div>
        )}
      </div>
      {actions && !meta && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, subtitle, right, count, step, flush, children, footer, id, className = '' }) {
  return (
    <section className={`card ${flush ? 'flush' : ''} ${className}`.trim()} id={id}
             aria-label={typeof title === 'string' ? title : undefined}>
      {(title || right) && (
        <header className="card-head">
          <div className="titles">
            {title && (
              <h2>
                {step != null && <span className="step" aria-hidden="true">{step}</span>}
                {title}
                {count != null && <span className="count" aria-label={`${count} items`}>{count}</span>}
              </h2>
            )}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {right && <div className="right">{right}</div>}
        </header>
      )}
      {children}
      {footer && <div className="card-foot">{footer}</div>}
    </section>
  );
}

/** A numbered step heading — the order of operations on the Today page. */
export function SectionTitle({ step, children }) {
  return (
    <h2 className="section-title">
      {step != null && <span className="step" aria-hidden="true">{step}</span>}
      {children}
    </h2>
  );
}

const CALLOUT_ICON = { danger: 'xCircle', warning: 'alert', info: 'info', success: 'checkCircle' };

/** Status message. `detail` is optional extra copy behind a "More" toggle so
 *  a stack of callouts stays scannable without dropping any of the text. */
export function Callout({ tone = 'info', title, children, detail, icon, role, quiet }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`callout ${tone} ${quiet ? 'quiet' : ''}`} role={role}>
      <Icon name={icon || CALLOUT_ICON[tone]} size={18} className="ic" />
      <div style={{ minWidth: 0 }}>
        {title && <h2>{title}</h2>}
        <div className="body">
          {children}
          {detail && !open && (
            <button type="button" className="more" onClick={() => setOpen(true)}
                    aria-expanded="false">More</button>
          )}
        </div>
        {detail && open && <div className="body">{detail}</div>}
      </div>
    </div>
  );
}

/** Segmented control. `options` = [[value, label, icon?], …]. */
export function Segmented({ value, onChange, options, label, size, full }) {
  return (
    <div className={`segmented ${full ? 'full' : ''}`} role="group" aria-label={label}>
      {options.map(([v, text, icon, aria]) => (
        <button key={v} type="button" aria-pressed={value === v}
                aria-label={aria} title={aria}
                onClick={() => onChange(v)} className={size}>
          {icon && <Icon name={icon} size={14} />}{text}
        </button>
      ))}
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder = 'Filter ticker…', label = 'Filter by ticker' }) {
  return (
    <label className="search">
      <Icon name="search" size={14} />
      <span className="sr-only">{label}</span>
      <input type="search" value={value} placeholder={placeholder}
             onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function EmptyState({ icon = 'inbox', title, children }) {
  return (
    <div className="empty-state">
      <div className="ic"><Icon name={icon} size={18} /></div>
      {title && <strong>{title}</strong>}
      {children && <div className="small" style={{ maxWidth: 520 }}>{children}</div>}
    </div>
  );
}

/** Two-step destructive button: first click arms it, second click acts. */
export function ConfirmButton({ onConfirm, children, confirmText = 'Confirm?', className = 'btn sm' }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return undefined;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);
  return (
    <button type="button" className={`${className} danger ${armed ? 'confirm' : ''}`}
            onClick={() => (armed ? (setArmed(false), onConfirm()) : setArmed(true))}
            onBlur={() => setArmed(false)}>
      {armed ? confirmText : children}
    </button>
  );
}

/* -------------------------------------------------------------- feedback */

export function Skeleton({ h = 16, w = '100%', style }) {
  return <div className="skel" style={{ height: h, width: w, ...style }} />;
}

/** Page-shaped placeholder, so the layout doesn't jump when data lands. */
export function Loading({ what = 'data' }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Loading {what}…</span>
      <div aria-hidden="true">
        <Skeleton h={12} w={120} style={{ marginBottom: 12 }} />
        <Skeleton h={28} w="min(520px, 80%)" style={{ marginBottom: 10 }} />
        <Skeleton h={14} w="min(680px, 95%)" style={{ marginBottom: 24 }} />
        <Skeleton h={92} style={{ marginBottom: 16, borderRadius: 12 }} />
        <Skeleton h={280} style={{ borderRadius: 12 }} />
      </div>
    </div>
  );
}

export function ErrorBox({ error, hint, onRetry }) {
  return (
    <div className="card" role="alert">
      <div className="err-box">
        <Icon name="xCircle" size={20} className="ic" />
        <div style={{ minWidth: 0, flex: 1 }}>
          <h2>Could not load this page</h2>
          <div className="msg">{String(error?.message || error)}</div>
          {hint && <div className="note">{hint}</div>}
          {onRetry && (
            <button type="button" className="btn sm" style={{ marginTop: 12 }} onClick={onRetry}>
              <Icon name="refresh" size={14} /> Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- drawer */

/** Right-hand detail panel. Esc or the scrim closes it; focus moves into the
 *  panel on open and back to whatever opened it on close. */
export function Drawer({ open, onClose, title, subtitle, children }) {
  const panel = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.activeElement;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      if (prev && typeof prev.focus === 'function') prev.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"
           tabIndex={-1} ref={panel}>
        <div className="drawer-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 id="drawer-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="btn ghost icon" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </>
  );
}
