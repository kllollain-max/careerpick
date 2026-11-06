#!/usr/bin/env bash
# Persist only the Threads ledger and generated cards, preserving concurrent main.
set -euo pipefail
if [ -z "$(git status --porcelain -- threads_posted.json threads-images/)" ]; then
  exit 0
fi
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add threads_posted.json
if [ "${1:-}" = '--images' ]; then
  git add threads-images/
fi
if git diff --cached --quiet; then
  exit 0
fi
git commit -m "${THREADS_STATE_COMMIT_MESSAGE:-Record CareerPick Threads state}"
for attempt in 1 2 3 4 5; do
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort || true
    echo '::error::Threads history conflict; preserve evidence and reconcile'
    exit 1
  fi
  if git push origin HEAD:main; then
    exit 0
  fi
  sleep "$((attempt * 3))"
done
echo '::error::Threads state persistence failed after bounded retries'
exit 1
