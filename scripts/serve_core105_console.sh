#!/usr/bin/env bash
# Serve the research console against the CORE-105 experiment bundle
# (reports/core105) on its own port — the production console on 8787 /
# reports/latest is untouched.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export REPORTS_DIR="${REPORTS_DIR:-$ROOT/reports/core105}"
export PORT="${PORT:-8790}"
cd "$ROOT/app/backend"
exec npm start
