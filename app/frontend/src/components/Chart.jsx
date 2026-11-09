/* Chart primitives — inline SVG so the mark specs hold exactly:
   2px lines, 4px rounded data-ends anchored to the baseline, a 2px surface gap
   between adjacent bars, solid hairline grid one shade off the surface, and a
   hover layer on every plot. One y-axis, always: no dual-scale charts.

   Responsive: every chart measures its container and draws at that width, so
   axis text stays 11px whether the card is full-width or a third of a phone
   (the old fixed 900-unit viewBox shrank labels to ~6px in narrow cards). */
import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react';

export const fmtPct = (v, d = 1) =>
  v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`;
export const fmtSignedPct = (v, d = 1) =>
  v == null || Number.isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
export const fmtNum = (v, d = 2) =>
  v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d);
export const fmtInt = (v) =>
  v == null || Number.isNaN(v) ? '—' : Number(v).toLocaleString('en-US');

/** Sign glyph — the redundant channel that carries profit/loss without hue. */
export const arrow = (v) => (v == null ? '' : v >= 0 ? '▲' : '▼');
export const signClass = (v) => (v == null ? '' : v >= 0 ? 'pos' : 'neg');

/** Container width, live. Falls back to `fallback` where layout is unknown
 *  (tests, first paint). */
export function useWidth(fallback = 900) {
  const ref = useRef(null);
  const [w, setW] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const set = () => { const cw = el.clientWidth; if (cw > 0) setW(Math.round(cw)); };
    set();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const tipPos = (x, y, w = 270) => ({
  left: Math.max(8, Math.min(x + 14, window.innerWidth - w)),
  top: Math.max(8, y - 12),
});

export function useTooltip() {
  const [tip, setTip] = useState(null);
  const show = useCallback((e, content) => {
    setTip({ x: e.clientX, y: e.clientY, content });
  }, []);
  const hide = useCallback(() => setTip(null), []);
  const node = tip ? <div className="tooltip" style={tipPos(tip.x, tip.y)}>{tip.content}</div> : null;
  return { show, hide, node };
}

/** Rounded data-end only: the baseline end stays square. */
function barPath(x, y, w, h, r, dir) {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  if (h <= 0.01) return '';
  if (dir === 'up') {
    return `M${x},${y + h} L${x},${y + rr} Q${x},${y} ${x + rr},${y} `
      + `L${x + w - rr},${y} Q${x + w},${y} ${x + w},${y + rr} L${x + w},${y + h} Z`;
  }
  if (dir === 'down') {
    return `M${x},${y} L${x},${y + h - rr} Q${x},${y + h} ${x + rr},${y + h} `
      + `L${x + w - rr},${y + h} Q${x + w},${y + h} ${x + w},${y + h - rr} L${x + w},${y} Z`;
  }
  // 'right' — horizontal bar, rounded right end
  const rh = Math.max(0, Math.min(r, h / 2, w));
  return `M${x},${y} L${x + w - rh},${y} Q${x + w},${y} ${x + w},${y + rh} `
    + `L${x + w},${y + h - rh} Q${x + w},${y + h} ${x + w - rh},${y + h} L${x},${y + h} Z`;
}

function niceTicks(min, max, count = 5) {
  if (min === max) return [min];
  const span = max - min;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
  const out = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) {
    out.push(Number(t.toFixed(10)));
  }
  return out;
}

/** Log-axis ticks on the 1-2-5 ladder (…, 200k, 500k, 1M, 2M, …), thinned to
 *  about `count`, so a log axis reads in round numbers. */
function logTicks(lo, hi, count = 5) {
  const a = 10 ** lo;
  const b = 10 ** hi;
  const out = [];
  for (let k = Math.floor(lo) - 1; k <= Math.ceil(hi) + 1; k += 1) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** k;
      if (v >= a && v <= b) out.push(v);
    }
  }
  if (out.length <= count + 1) return out;
  const decades = out.filter((v) => Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-9);
  return decades.length >= 2 ? decades : out.filter((_, i) => i % Math.ceil(out.length / count) === 0);
}

/** "$1.2M", "$500K" — for axis ticks where full precision is noise. */
export const fmtMoneyShort = (v) => {
  if (v == null || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  const s = v < 0 ? '−' : '';
  if (a >= 1e9) return `${s}$${+(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}$${+(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${+(a / 1e3).toFixed(0)}K`;
  return `${s}$${a.toFixed(0)}`;
};

const TXT = { fontSize: 11, fill: 'var(--text-muted)', style: { fontVariantNumeric: 'tabular-nums' } };
const approxTextW = (s, px = 6.6) => String(s ?? '').length * px;

/* ------------------------------------------------------------- LineChart */
export function LineChart({
  series, height = 260, yFormat = (v) => fmtNum(v, 2),
  xLabels = 6, yTicks = 5, logY = false, zeroLine = false, area, label, tickFormat,
}) {
  const tickFmt = tickFormat || yFormat;
  const [box, W] = useWidth();
  const [hover, setHover] = useState(null);
  const gid = useId().replace(/:/g, '');
  const H = height;

  const flat = series.flatMap((s) => s.points);
  if (!flat.length) return <div ref={box} className="empty">No data</div>;

  const tx = (v) => (logY ? Math.log10(Math.max(v, 1e-9)) : v);
  const ys = flat.map((p) => tx(p.y)).filter((v) => Number.isFinite(v));
  let yMin = Math.min(...ys);
  let yMax = Math.max(...ys);
  if (zeroLine && !logY) { yMin = Math.min(yMin, 0); yMax = Math.max(yMax, 0); }
  const padY = (yMax - yMin) * 0.08 || 0.1;
  yMin -= padY; yMax += padY;
  const n = Math.max(...series.map((s) => s.points.length));

  const ticks = logY ? logTicks(yMin, yMax, yTicks) : niceTicks(yMin, yMax, yTicks);
  const ends = series.length <= 4 ? series.map((s) => s.points[s.points.length - 1]).filter(Boolean) : [];
  const yLabelW = Math.max(...ticks.map((t) => approxTextW(tickFmt(t))));
  const endW = ends.length ? Math.max(...ends.map((p) => approxTextW(yFormat(p.y), 7))) : 0;
  const pad = { t: 12, r: endW ? endW + 14 : 12, b: 26, l: Math.max(36, yLabelW + 14) };
  const plotW = Math.max(40, W - pad.l - pad.r);

  const px = (i) => pad.l + (i / Math.max(1, n - 1)) * plotW;
  const py = (v) => pad.t + (1 - (tx(v) - yMin) / (yMax - yMin)) * (H - pad.t - pad.b);

  const labels = series[0].points;
  const nX = Math.max(2, Math.min(xLabels, n, Math.floor(plotW / 84)));
  const xIdx = Array.from({ length: nX }, (_, k) =>
    Math.round((k / Math.max(1, nX - 1)) * (n - 1)));

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const rel = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((rel - pad.l) / plotW) * (n - 1));
    if (i >= 0 && i < n) setHover({ i, cx: e.clientX, cy: e.clientY });
    else setHover(null);
  };
  const showArea = area ?? series.length === 1;
  const baseY = zeroLine && !logY && yMin < 0 && yMax > 0 ? py(0) : H - pad.b;

  return (
    <div className="chart" ref={box}>
      {(series.length > 1 || series[0].name) && (
        <div className="legend">
          {series.map((s) => (
            <span className="key" key={s.name}>
              <span className="swatch" style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}
           onPointerMove={onMove} onPointerLeave={() => setHover(null)}
           role="img" aria-label={label || series.map((s) => s.name).join(', ')}>
        <defs>
          {series.map((s, si) => (
            <linearGradient key={s.name} id={`${gid}-g${si}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="0.16" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={py(t)} y2={py(t)}
                  stroke="var(--gridline)" strokeWidth="1" />
            <text x={pad.l - 8} y={py(t) + 4} textAnchor="end" {...TXT}>{tickFmt(t)}</text>
          </g>
        ))}
        {zeroLine && !logY && yMin < 0 && yMax > 0 && (
          <line x1={pad.l} x2={W - pad.r} y1={py(0)} y2={py(0)}
                stroke="var(--axis)" strokeWidth="1" />
        )}
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b}
              stroke="var(--axis)" strokeWidth="1" />
        {xIdx.map((i, k) => (
          <text key={i} x={px(i)} y={H - pad.b + 16}
                textAnchor={k === 0 ? 'start' : k === xIdx.length - 1 ? 'end' : 'middle'} {...TXT}>
            {labels[i]?.x ?? ''}
          </text>
        ))}

        {series.map((s, si) => {
          const d = s.points.map((p, i) =>
            `${i === 0 ? 'M' : 'L'}${px(i).toFixed(1)},${py(p.y).toFixed(1)}`).join(' ');
          return (
            <g key={s.name}>
              {showArea && s.points.length > 1 && (
                <path d={`${d} L${px(s.points.length - 1)},${baseY} L${px(0)},${baseY} Z`}
                      fill={`url(#${gid}-g${si})`} stroke="none" />
              )}
              <path d={d} fill="none" stroke={s.color}
                    strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}

        {/* direct endpoint labels — identity without relying on the legend */}
        {ends.length > 0 && series.map((s) => {
          const last = s.points[s.points.length - 1];
          if (!last) return null;
          return (
            <text key={`${s.name}-lbl`} x={W - pad.r + 7} y={py(last.y) + 4}
                  fontSize="11.5" fill="var(--text-secondary)" fontWeight="600"
                  style={{ fontVariantNumeric: 'tabular-nums' }}>
              {yFormat(last.y)}
            </text>
          );
        })}

        {hover && (
          <g>
            <line x1={px(hover.i)} x2={px(hover.i)} y1={pad.t} y2={H - pad.b}
                  stroke="var(--axis)" strokeWidth="1" strokeDasharray="3 3" />
            {series.map((s) => {
              const p = s.points[hover.i];
              return p ? (
                <circle key={s.name} cx={px(hover.i)} cy={py(p.y)} r="4.5"
                        fill={s.color} stroke="var(--surface-1)" strokeWidth="2" />
              ) : null;
            })}
          </g>
        )}
      </svg>
      {hover && (
        <div className="tooltip" style={tipPos(hover.cx, hover.cy, 250)}>
          <div className="t-title">{labels[hover.i]?.x}</div>
          {series.map((s) => (
            <div className="t-row" key={s.name}>
              <span><span className="swatch sq" style={{ background: s.color, width: 8, height: 8 }} />{s.name}</span>
              <span>{s.points[hover.i] ? yFormat(s.points[hover.i].y) : '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- BarChart */
export function BarChart({
  data, height = 240, horizontal = false, bySign = false,
  color = 'var(--series-1)', valueFormat = (v) => fmtNum(v, 3),
  refLine = null, refLabel = '', labelEvery = 1, label,
}) {
  const [box, W] = useWidth();
  const { show, hide, node } = useTooltip();
  const [hi, setHi] = useState(null);
  if (!data.length) return <div ref={box} className="empty">No data</div>;

  const H = horizontal ? Math.max(height, data.length * 26 + 32) : height;
  const vals = data.map((d) => d.value).filter((v) => Number.isFinite(v));
  let vMin = Math.min(0, ...vals);
  let vMax = Math.max(0, ...vals);
  if (refLine != null) { vMin = Math.min(vMin, refLine); vMax = Math.max(vMax, refLine); }
  if (vMin === vMax) vMax = vMin + 1;
  const span = vMax - vMin;
  vMax += span * 0.06;
  if (vMin < 0) vMin -= span * 0.06;

  const fillFor = (v) => (bySign ? (v >= 0 ? 'var(--profit)' : 'var(--loss)') : color);
  const dim = (i) => (hi != null && hi !== i ? 0.45 : 1);
  const tipFor = (d) => (
    <>
      <div className="t-title">{d.label}</div>
      <div className="t-row">
        <span>{d.tipLabel || 'value'}</span>
        <span>{valueFormat(d.value)}</span>
      </div>
      {d.tip}
    </>
  );
  const enter = (i, d) => (e) => { setHi(i); show(e, tipFor(d)); };
  const leave = () => { setHi(null); hide(); };

  if (horizontal) {
    const maxValW = Math.max(...data.map((d) => approxTextW(valueFormat(d.value))));
    const pad = {
      t: 6, b: 24,
      l: Math.min(170, Math.max(56, Math.max(...data.map((d) => approxTextW(d.label, 6.9))) + 16)),
      r: maxValW + 14,
    };
    const plotW = Math.max(40, W - pad.l - pad.r);
    const rowH = (H - pad.t - pad.b) / data.length;
    const barH = Math.max(6, Math.min(20, rowH - 6));   // ≥2px surface gap
    const sx = (v) => pad.l + ((v - vMin) / (vMax - vMin)) * plotW;
    const x0 = sx(0);
    const nT = Math.max(2, Math.min(6, Math.floor(plotW / 70)));
    return (
      <div className="chart" ref={box}>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
          {niceTicks(vMin, vMax, nT).map((t) => (
            <g key={t}>
              <line x1={sx(t)} x2={sx(t)} y1={pad.t} y2={H - pad.b}
                    stroke="var(--gridline)" strokeWidth="1" />
              <text x={sx(t)} y={H - pad.b + 15} textAnchor="middle" {...TXT}>{valueFormat(t)}</text>
            </g>
          ))}
          <line x1={x0} x2={x0} y1={pad.t} y2={H - pad.b} stroke="var(--axis)" strokeWidth="1" />
          {data.map((d, i) => {
            const y = pad.t + i * rowH + (rowH - barH) / 2;
            const xv = sx(d.value);
            const x = Math.min(x0, xv);
            const w = Math.abs(xv - x0);
            return (
              <g key={d.label} onPointerMove={enter(i, d)} onPointerLeave={leave}>
                <rect x={0} y={pad.t + i * rowH} width={W} height={rowH} fill="transparent" />
                <path d={barPath(x, y, Math.max(w, 1.5), barH, 4, 'right')}
                      fill={fillFor(d.value)} opacity={dim(i)} />
                <text x={pad.l - 10} y={y + barH / 2 + 4} textAnchor="end" fontSize="12"
                      fill="var(--text-secondary)">{d.label}</text>
                <text x={x + w + 7} y={y + barH / 2 + 4} fontSize="11.5"
                      fill="var(--text-secondary)" fontWeight="550"
                      style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {valueFormat(d.value)}
                </text>
              </g>
            );
          })}
          {refLine != null && (
            <g>
              <line x1={sx(refLine)} x2={sx(refLine)} y1={pad.t - 2} y2={H - pad.b}
                    stroke="var(--warning)" strokeWidth="2" strokeDasharray="4 3" />
              <text x={sx(refLine) + 5} y={H - pad.b - 5} fontSize="10.5" fill="var(--text-secondary)"
                    fontWeight="600">{refLabel}</text>
            </g>
          )}
        </svg>
        {node}
      </div>
    );
  }

  const yW = Math.max(...niceTicks(vMin, vMax, 5).map((t) => approxTextW(valueFormat(t))));
  const pad = { t: 14, r: 8, b: 30, l: Math.max(34, yW + 12) };
  const plotW = Math.max(40, W - pad.l - pad.r);
  const colW = plotW / data.length;
  const barW = Math.max(2, Math.min(44, colW - 2));      // 2px surface gap
  const sy = (v) => pad.t + (1 - (v - vMin) / (vMax - vMin)) * (H - pad.t - pad.b);
  const y0 = sy(0);
  const maxLblW = Math.max(...data.map((d) => approxTextW(d.label)));
  const every = Math.max(labelEvery, Math.ceil(data.length / Math.max(1, Math.floor(plotW / (maxLblW + 10)))));
  return (
    <div className="chart" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
        {niceTicks(vMin, vMax, 5).map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={sy(t)} y2={sy(t)}
                  stroke="var(--gridline)" strokeWidth="1" />
            <text x={pad.l - 8} y={sy(t) + 4} textAnchor="end" {...TXT}>{valueFormat(t)}</text>
          </g>
        ))}
        <line x1={pad.l} x2={W - pad.r} y1={y0} y2={y0} stroke="var(--axis)" strokeWidth="1" />
        {data.map((d, i) => {
          const x = pad.l + i * colW + (colW - barW) / 2;
          const yv = sy(d.value);
          const up = d.value >= 0;
          const y = up ? yv : y0;
          const h = Math.abs(yv - y0);
          return (
            <g key={d.label} onPointerMove={enter(i, d)} onPointerLeave={leave}>
              <rect x={pad.l + i * colW} y={pad.t} width={colW} height={H - pad.t - pad.b}
                    fill="transparent" />
              <path d={barPath(x, y, barW, Math.max(h, 1.5), Math.min(4, barW / 2), up ? 'up' : 'down')}
                    fill={fillFor(d.value)} opacity={dim(i)} />
              {i % every === 0 && (
                <text x={x + barW / 2} y={H - pad.b + 16} textAnchor="middle" {...TXT}>{d.label}</text>
              )}
            </g>
          );
        })}
      </svg>
      {node}
    </div>
  );
}
