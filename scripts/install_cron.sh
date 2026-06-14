#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/var/www/fear_and_greed_new}"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
LOG_FILE="$PROJECT_DIR/output.log"
CRON_MARKER="# fear_and_greed_new weekday batch"
CRON_LINE="0 17 * * 1-5 cd $PROJECT_DIR && ENV=production $PYTHON_BIN main.py >> $LOG_FILE 2>&1 $CRON_MARKER"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

current_cron="$(mktemp)"
next_cron="$(mktemp)"

crontab -l > "$current_cron" 2>/dev/null || true

# Remove the old managed entry, then append the current one.
grep -vF "$CRON_MARKER" "$current_cron" > "$next_cron" || true
printf '%s\n' "$CRON_LINE" >> "$next_cron"

crontab "$next_cron"

rm -f "$current_cron" "$next_cron"

echo "Installed cron entry:"
echo "$CRON_LINE"
