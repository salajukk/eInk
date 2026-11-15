#!/bin/bash
# Install cron/eink.crontab onto the Pi, replacing only the marked
# "eink-managed" block. Other crontab entries on the Pi are preserved.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"
CRON_FILE="$SCRIPT_DIR/cron/eink.crontab"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${PI_TARGET:?Set PI_TARGET in deploy.env (copy deploy.env.example first)}"
[ -f "$CRON_FILE" ] || { echo "Missing $CRON_FILE"; exit 1; }

encoded=$(base64 < "$CRON_FILE" | tr -d '\n')

ssh "$PI_TARGET" "
set -euo pipefail
new_block=\$(printf '%s' '$encoded' | base64 -d)
existing=\$(crontab -l 2>/dev/null || true)
cleaned=\$(printf '%s\n' \"\$existing\" | sed '/^# >>> eink-managed >>>/,/^# <<< eink-managed <<</d')
{
  [ -n \"\$cleaned\" ] && printf '%s\n' \"\$cleaned\"
  printf '%s' \"\$new_block\"
} | crontab -
echo '--- installed crontab ---'
crontab -l
"
