#!/usr/bin/env bash
# Run on a machine with a Taiwan IP to refresh the shops that block GitHub's servers
# (config sources/stores marked "local_only": 順發, 3D列印基地站).
# It merges their prices into today's entry from the GitHub run, re-renders the page and pushes.
#
#   scripts/local_run.sh          # refresh local-only shops and push
#   scripts/local_run.sh --full   # backup path: run the whole tracker here instead of on GitHub
#
# Telegram/ntfy secrets for alerts can go in scripts/.env (gitignored): TELEGRAM_BOT_TOKEN=... etc.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f scripts/.env ] && set -a && . scripts/.env && set +a
git pull --rebase --autostash -q
if [ "${1:-}" = "--full" ]; then
  python3 -m tracker run --save-raw build/raw.html
else
  python3 -m tracker local
fi
git add data docs
if ! git diff --cached --quiet; then
  git commit -qm "data: $(TZ=Asia/Taipei date +%F) (local)"
  git pull --rebase -q && git push -q
  echo "pushed"
else
  echo "no changes"
fi
