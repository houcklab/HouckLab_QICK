#!/usr/bin/env bash
# usage: land_fix.sh <tag> [path ...]
# Snapshots the main tree's changes (all, or only the given paths) into a fresh worktree at HEAD, runs the full
# suite there with REGRESSION_UPDATE=1 (regenerates the golden), then classifies new golden vs HEAD golden.
set -u
TAG=$1; shift
REPO=$(git rev-parse --show-toplevel); SCRATCH=${QICKLAB_SCRATCH:-$HOME/.cache/qicklab-refactor}; mkdir -p $SCRATCH/logs
WT=$SCRATCH/wt_$TAG; LOG=$SCRATCH/logs/fix_$TAG.log; TOOLS=$REPO/docs/dev/refactor-2026-10/tools
cd $REPO || exit 2
git worktree remove --force $WT 2>/dev/null; git worktree prune
git worktree add --detach -q $WT HEAD || exit 2
if [ $# -gt 0 ]; then
  git diff HEAD --binary -- "$@" | git -C $WT apply || { echo "apply failed" > $LOG; exit 2; }
  for f in $(git ls-files --others --exclude-standard -- "$@"); do mkdir -p "$WT/$(dirname $f)"; cp "$f" "$WT/$f"; done
else
  git diff HEAD --binary | git -C $WT apply || { echo "apply failed" > $LOG; exit 2; }
  for f in $(git ls-files --others --exclude-standard); do mkdir -p "$WT/$(dirname $f)"; cp "$f" "$WT/$f"; done
fi
cd $WT && { [ -f $REPO/.venv/bin/activate ] && source $REPO/.venv/bin/activate || source $REPO/.venv/Scripts/activate; }
git status --short > $LOG
{ python -m compileall -q qicklab devices runners tests && echo "compile OK" && ruff check --select F qicklab runners tests devices && ruff format --check qicklab devices runners tests | tail -1; } >> $LOG 2>&1 || { echo "FAST-LADDER FAILED" >> $LOG; exit 1; }
REGRESSION_UPDATE=1 python -m pytest tests -p no:cacheprovider >> $LOG 2>&1; RC=$?
echo "PYTEST_EXIT=$RC" >> $LOG
python $TOOLS/classify_golden.py <(git show HEAD:tests/regression/golden_cstq03.json) tests/regression/golden_cstq03.json > $SCRATCH/logs/fix_${TAG}_classify.txt 2>&1
echo "CLASSIFY_DONE" >> $LOG
exit $RC
