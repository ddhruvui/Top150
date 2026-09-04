// Local entry point: listen on a port. (Vercel uses api/index.js instead.)
import { app, servesFrontend } from './app.js';
import * as reports from './reports.js';

const PORT = process.env.PORT || 8787;

app.listen(PORT, async () => {
  console.log(`API on http://localhost:${PORT}`);
  const st = reports.status();
  const where = st.source === 'file' ? st.reports_dir : `mongodb ${st.db} · bundle ${st.bundle}`;
  try {
    const s = await reports.summary();
    console.log(`  reports: ${where} `
      + (s ? `(built ${s.generated_utc}, verdict ${s.gates?.verdict})` : '(NOT PUBLISHED YET)'));
  } catch (err) {
    console.log(`  reports: ${where} — UNREACHABLE: ${err.message}`);
  }
  if (servesFrontend) console.log('  serving the built frontend from ../frontend/dist');
});
