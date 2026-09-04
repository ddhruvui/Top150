// Minimal .env loader — no dependency. KEY=VALUE lines, # comments, optional
// quotes. Reads ./.env and then ../../.env (the monorepo root) so one file at
// the root serves the backend, the publisher and the mirror script alike. A
// variable already in the environment always wins over the file, so Vercel's
// project settings are never overridden by anything on disk.
import fs from 'node:fs';
import path from 'node:path';

export function loadDotEnv(files = ['.env', '../../.env']) {
  for (const f of files) {
    const file = path.resolve(process.cwd(), f);
    let text;
    try {
      text = fs.readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    for (const raw of text.split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('#')) continue;
      const eq = line.indexOf('=');
      if (eq < 0) continue;
      const key = line.slice(0, eq).trim().replace(/^export\s+/, '');
      let val = line.slice(eq + 1).trim();
      if ((val.startsWith('"') && val.endsWith('"'))
          || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (process.env[key] === undefined) process.env[key] = val;
    }
  }
}

/** MONGO_URI with the Atlas-style `<db_password>` placeholder filled from
 *  DB_PASSWORD (URL-encoded, so any character in the password is safe). */
export function mongoUri() {
  const raw = process.env.MONGO_URI;
  if (!raw) return null;
  const pw = process.env.DB_PASSWORD;
  return pw ? raw.replace('<db_password>', encodeURIComponent(pw)) : raw;
}
