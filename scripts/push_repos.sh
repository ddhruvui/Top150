#!/usr/bin/env bash
# Push this monorepo and its two deployable subtrees to GitHub in one go:
#
#   origin  https://github.com/ddhruvui/Top150.git    everything (current branch)
#   be      https://github.com/ddhruvui/Top150BE.git  app/backend  -> main  (Vercel)
#   fe      https://github.com/ddhruvui/Top150FE.git  app/frontend -> main  (Render)
#
# The deploy repos are git subtrees: each receives only the commits that touch
# its directory, so there is exactly one copy of the code to edit (here) and the
# deploy repos always match it. Edit here, commit, run this — Vercel and Render
# redeploy from their repos' main.
#
# If a deploy repo was edited directly (non-fast-forward), bring it back first:
#   git subtree pull --prefix=app/backend be main
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BRANCH="$(git branch --show-current)"

ensure_remote() { git remote get-url "$1" >/dev/null 2>&1 || git remote add "$1" "$2"; }
ensure_remote origin https://github.com/ddhruvui/Top150.git
ensure_remote be     https://github.com/ddhruvui/Top150BE.git
ensure_remote fe     https://github.com/ddhruvui/Top150FE.git

if [ -n "$(git status --porcelain)" ]; then
  echo "refusing: working tree not clean — commit or stash first" >&2
  exit 1
fi
# Secrets never travel: no .env variant may be tracked anywhere in the tree.
if git ls-files | grep -E '(^|/)\.env(\.[^/]*)?$' | grep -v '\.env\.example$'; then
  echo "refusing: an env file is tracked (above) — git rm --cached it first" >&2
  exit 1
fi

echo "-> origin $BRANCH   (all code)"
git push -u origin "$BRANCH"
echo "-> be main          (app/backend)"
git subtree push --prefix=app/backend be main
echo "-> fe main          (app/frontend)"
git subtree push --prefix=app/frontend fe main
echo "pushed: origin/$BRANCH, be/main, fe/main"
