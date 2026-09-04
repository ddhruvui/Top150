// Vercel entry point. vercel.json rewrites every request here and the request
// keeps its original path, so the Express app routes /api/* exactly as it does
// locally. Nothing else lives under api/ — one function, one cold start.
import { app } from '../src/app.js';

export default app;
