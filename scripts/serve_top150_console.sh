#!/usr/bin/env bash
# Serve the research console against the TOP-150 experiment bundle
# (reports/top150) on its own port — the production console on 8787 /
# reports/latest is untouched.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export REPORTS_DIR="${REPORTS_DIR:-$ROOT/reports/top150}"
export PORT="${PORT:-8790}"
cd "$ROOT/app/backend"
exec npm start
