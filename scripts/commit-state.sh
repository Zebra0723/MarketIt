#!/usr/bin/env bash
# Commit MarketIt's state (data/) back to the repo. If another run pushed in the meantime,
# rebase onto it; where both changed the same lines, this run's version wins, and any JSON
# file the merge left invalid is restored from this run's copy.
set -uo pipefail
git config user.name "marketit-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "no state changes"
  exit 0
fi
git commit -q -m "MarketIt: ${1:-update state}"
MINE=$(git rev-parse HEAD)

for delay in 2 4 8 16 32; do
  if git pull -q --rebase -X theirs; then
    fixed=0
    while IFS= read -r f; do
      if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
        echo "repairing $f after merge"
        git show "$MINE:$f" > "$f" && git add "$f" && fixed=1
      fi
    done < <(git ls-files 'data/*.json' 'data/**/*.json')
    if [ "$fixed" = 1 ]; then git commit -q -m "MarketIt: repair state after merge [skip ci]"; fi
    if git push -q; then
      exit 0
    fi
  else
    git rebase --abort 2>/dev/null || true
    git reset -q --hard "$MINE"
  fi
  echo "push failed, retrying in ${delay}s"
  sleep "$delay"
done
echo "could not push state" >&2
exit 1
