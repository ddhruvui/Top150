/* A tiny inline icon set (24-unit grid, 2px round strokes) so the console
   needs no icon dependency. Decorative by default: aria-hidden unless a
   `title` is given. */
const P = {
  today: ['M8 2v4', 'M16 2v4', 'M3 10h18', 'm9 16 2 2 4-4',
    { rect: { x: 3, y: 4, width: 18, height: 18, rx: 2 } }],
  book: ['M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z', 'M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'],
  gauge: ['m12 14 4-4', 'M3.34 19a10 10 0 1 1 17.32 0'],
  coins: ['M18.09 10.37A6 6 0 1 1 10.34 18', 'M7 6h1v4', 'm16.71 13.88.7.71-2.82 2.82',
    { circle: { cx: 8, cy: 8, r: 6 } }],
  list: ['M3 12h.01', 'M3 18h.01', 'M3 6h.01', 'M8 12h13', 'M8 18h13', 'M8 6h13'],
  history: ['M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8', 'M3 3v5h5', 'M12 7v5l4 2'],
  sun: ['M12 2v2', 'M12 20v2', 'm4.93 4.93 1.41 1.41', 'm17.66 17.66 1.41 1.41', 'M2 12h2',
    'M20 12h2', 'm6.34 17.66-1.41 1.41', 'm19.07 4.93-1.41 1.41', { circle: { cx: 12, cy: 12, r: 4 } }],
  moon: ['M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z'],
  monitor: ['M8 21h8', 'M12 17v4', { rect: { x: 2, y: 3, width: 20, height: 14, rx: 2 } }],
  menu: ['M4 12h16', 'M4 6h16', 'M4 18h16'],
  x: ['M18 6 6 18', 'm6 6 12 12'],
  alert: ['m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3', 'M12 9v4', 'M12 17h.01'],
  xCircle: ['m15 9-6 6', 'm9 9 6 6', { circle: { cx: 12, cy: 12, r: 10 } }],
  info: ['M12 16v-4', 'M12 8h.01', { circle: { cx: 12, cy: 12, r: 10 } }],
  checkCircle: ['m9 12 2 2 4-4', { circle: { cx: 12, cy: 12, r: 10 } }],
  check: ['M20 6 9 17l-5-5'],
  plus: ['M5 12h14', 'M12 5v14'],
  refresh: ['M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8', 'M21 3v5h-5',
    'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16', 'M8 16H3v5'],
  search: ['m21 21-4.3-4.3', { circle: { cx: 11, cy: 11, r: 8 } }],
  chevronLeft: ['m15 18-6-6 6-6'],
  chevronRight: ['m9 18 6-6-6-6'],
  chevronDown: ['m6 9 6 6 6-6'],
  clock: ['M12 6v6l4 2', { circle: { cx: 12, cy: 12, r: 10 } }],
  help: ['M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3', 'M12 17h.01', { circle: { cx: 12, cy: 12, r: 10 } }],
  shield: ['M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z'],
  activity: ['M22 12h-4l-3 9L9 3l-3 9H2'],
  inbox: ['M22 12h-6l-2 3h-4l-2-3H2',
    'M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z'],
  target: [{ circle: { cx: 12, cy: 12, r: 10 } }, { circle: { cx: 12, cy: 12, r: 6 } },
    { circle: { cx: 12, cy: 12, r: 2 } }],
  sliders: ['M20 7h-9', 'M14 17H5', { circle: { cx: 17, cy: 17, r: 3 } }, { circle: { cx: 7, cy: 7, r: 3 } }],
  database: ['M3 5V19A9 3 0 0 0 21 19V5', 'M3 12A9 3 0 0 0 21 12',
    { ellipse: { cx: 12, cy: 5, rx: 9, ry: 3 } }],
  trend: ['M22 7 13.5 15.5 8.5 10.5 2 17', 'M16 7h6v6'],
  layers: ['m12.83 2.18 8.58 3.91a1 1 0 0 1 0 1.83l-8.58 3.9a2 2 0 0 1-1.66 0L2.6 7.91a1 1 0 0 1 0-1.83l8.58-3.9a2 2 0 0 1 1.66 0Z',
    'm22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65', 'm22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65'],
};

export default function Icon({ name, size = 16, stroke = 2, title, className, style }) {
  const parts = P[name];
  if (!parts) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
         className={className} style={style}
         aria-hidden={title ? undefined : 'true'} role={title ? 'img' : undefined}>
      {title && <title>{title}</title>}
      {parts.map((p, i) => {
        if (typeof p === 'string') return <path key={i} d={p} />;
        const [tag, attrs] = Object.entries(p)[0];
        const Tag = tag;
        return <Tag key={i} {...attrs} />;
      })}
    </svg>
  );
}
