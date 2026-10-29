#!/usr/bin/env bash
# Commit MarketIt's state (data/) back to the repo, retrying if another run pushed first.
set -euo pipefail
git config user.name "marketit-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "no state changes"
  exit 0
fi
git commit -q -m "MarketIt: ${1:-update state}"
for delay in 2 4 8 16; do
  if git pull -q --rebase && git push -q; then
    exit 0
  fi
  echo "push failed, retrying in ${delay}s"
  sleep "$delay"
done
echo "could not push state" >&2
exit 1
