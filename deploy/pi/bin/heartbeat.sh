#!/usr/bin/env bash
# MealMate heartbeat (OPS-04, plan § 11.4), every 5 minutes via mealmate-heartbeat.timer:
#   1. tailscale status --json | jq -e '.BackendState == "Running"'
#   2. curl -fsS "$MEALMATE_PUBLIC_URL/api/health" (through tailscale serve and its certificate;
#      the app checks its database and that the data directory is writable)
# Both pass: ping HC_HEARTBEAT_URL; otherwise ping /fail with the name of the failed step. A
# failure is retried twice (15 s apart) before it counts. While update.sh, setup.sh or
# --rotate-secret holds state/deploy.lock the heartbeat stays silent instead of failing; the
# check's grace period covers that.
set -euo pipefail

here=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lib=$here/setup.sh
[ -f "$lib" ] || lib=$here/../setup.sh
# shellcheck source=deploy/pi/setup.sh
source "$lib"
mm_init heartbeat

attempts=${MEALMATE_HEARTBEAT_ATTEMPTS:-3}
delay=${MEALMATE_HEARTBEAT_RETRY_DELAY:-15}

if mm_lock_held deploy; then
  mm_log "update, setup or secret rotation in progress (state/deploy.lock); skipping this heartbeat"
  exit 0
fi

check() {
  if ! "$TAILSCALE" status --json 2>/dev/null | jq -e '.BackendState == "Running"' >/dev/null; then
    echo "tailscale: not running"
    return 1
  fi
  if ! mm_app_healthy_public; then
    echo "https: $(mm_env_get MEALMATE_PUBLIC_URL)/api/health failed"
    return 1
  fi
}

url=$(mm_env_get HC_HEARTBEAT_URL)
for ((i = 1; i <= attempts; i++)); do
  if failure=$(check); then
    mm_ping "$url" ok "ok"
    exit 0
  fi
  mm_log "attempt $i: $failure"
  if ((i < attempts)); then
    sleep "$delay"
  fi
done
mm_ping "$url" fail "$failure"
exit 1
