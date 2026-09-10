#!/bin/bash
# Fetch one day's worth of Phase 10 Agent answers and stop.
#
# Run on an interval rather than once a day on purpose. The provider's quota
# resets on its own clock, not ours, and guessing that clock wrong costs a
# whole day of a seven-day job. A run that finds no quota left exits in
# seconds having fetched nothing, so checking often is close to free, and a
# run that finds quota takes whatever is there and saves it.
#
# Never destructive: every run resumes from the on-disk cache and only fetches
# prompts that have no answer yet.
set -uo pipefail

# FINISHED. Phase 10's agent arm reached 2,212 of 2,212 answers on 2026-09-09
# and the job was unloaded:
#
#   launchctl unload ~/Library/LaunchAgents/com.learnedmarket.phase10.plist
#
# Left in the repo because it is the record of how a four-day, rate-limited
# run was actually carried out, and because re-loading it is how a second
# provider's arm would be run. Re-loading it for *this* arm would only
# re-bind a frozen, tagged result to whatever HEAD happens to be - which is
# what the last two runs did, harmlessly but pointlessly, before it was
# stopped. They did confirm the numbers reproduce at a different commit.

REPO="/Users/luxier/learned_market"
LOG_DIR="$REPO/results/phase10/daily_logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

cd "$REPO" || exit 1
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
  ./.venv/bin/python experiments/phase10/run_phase10.py --provider groq
  echo "--- exit $? ---"
  echo
} >> "$LOG" 2>&1
