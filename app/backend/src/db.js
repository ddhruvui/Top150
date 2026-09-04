// MongoDB access. One client per process, cached on globalThis so serverless
// warm invocations (and `node --watch` reloads) reuse the pool instead of
// paying a fresh TLS handshake per request. The driver connects lazily on the
// first operation, so importing this module never blocks.
import { MongoClient } from 'mongodb';
import { loadDotEnv, mongoUri } from './env.js';

loadDotEnv();

export const DB_NAME = process.env.MONGO_DB || 'Top150';
/** Which report bundle this API serves — `reports/<bundle>` locally, the
 *  `<bundle>/<section>` documents in Mongo. */
export const BUNDLE = process.env.BUNDLE || 'top150';

export const hasMongo = () => Boolean(mongoUri());

const g = globalThis;
export function client() {
  if (!g.__top150MongoClient) {
    const uri = mongoUri();
    if (!uri) throw new Error('MONGO_URI is not set');
    g.__top150MongoClient = new MongoClient(uri, {
      maxPoolSize: 5,
      serverSelectionTimeoutMS: 8000,
    });
  }
  return g.__top150MongoClient;
}

export const db = () => client().db(DB_NAME);
export const col = (name) => db().collection(name);
