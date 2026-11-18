#!/usr/bin/env bash
# Backup path: run the tracker on this machine and push results.
# Use from cron/systemd if GitHub runners can't reach coolpc.com.tw.
# Notification secrets can be put in scripts/.env (gitignored): NTFY_TOPIC=... etc.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f scripts/.env ] && set -a && . scripts/.env && set +a
git pull --rebase --autostash -q
python3 -m tracker run --save-raw build/raw.html
git add data docs
if ! git diff --cached --quiet; then
  git commit -qm "data: $(TZ=Asia/Taipei date +%F) (local)"
  git push -q
fi
