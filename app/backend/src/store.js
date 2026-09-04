// Paper-book persistence. Mongo (one document per bundle in `paper_books`)
// whenever MONGO_URI is configured — Vercel has no durable disk, and a Mongo
// book is also shared between the deployed UI and a local run. Otherwise, or
// when PAPER_DATA_DIR is given (the tests do this), a single JSON file written
// atomically, exactly as before.
import fs from 'node:fs';
import path from 'node:path';
import { BUNDLE, hasMongo, col } from './db.js';

const FILE_MODE = Boolean(process.env.PAPER_DATA_DIR) || !hasMongo();
const DATA_DIR = process.env.PAPER_DATA_DIR || path.resolve(process.cwd(), 'data');
const FILE = path.join(DATA_DIR, 'paper_book.json');

export const storeKind = () => (FILE_MODE ? 'file' : 'mongo');
export const storeLocation = () => (FILE_MODE ? FILE : `paper_books/${BUNDLE}`);

export async function loadBook() {
  if (FILE_MODE) {
    try {
      return JSON.parse(fs.readFileSync(FILE, 'utf8'));
    } catch {
      return null;
    }
  }
  const doc = await col('paper_books').findOne({ _id: BUNDLE });
  if (!doc) return null;
  const { _id, ...state } = doc;
  return state;
}

export async function saveBook(state) {
  if (FILE_MODE) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const tmp = `${FILE}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(state, null, 1));
    fs.renameSync(tmp, FILE);          // atomic
    return state;
  }
  await col('paper_books').replaceOne(
    { _id: BUNDLE }, { _id: BUNDLE, ...state }, { upsert: true });
  return state;
}
