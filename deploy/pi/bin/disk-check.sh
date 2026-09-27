#!/usr/bin/env bash
# MealMate disk check (OPS-04, plan § 11.4), hourly via mealmate-disk.timer: writes the free
# space of / to state/status/disk.json (shown on the admin page) and pings HC_DISK_URL, or its
# /fail endpoint below 20 % free.
set -euo pipefail

here=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lib=$here/setup.sh
[ -f "$lib" ] || lib=$here/../setup.sh
# shellcheck source=deploy/pi/setup.sh
source "$lib"
mm_init disk

path=${MEALMATE_DISK_PATH:-/}
min_free=${MEALMATE_DISK_MIN_FREE_PERCENT:-20}

read -r total free < <(df -P -B1 -- "$path" | awk 'NR == 2 { print $2, $4 }')
[ -n "${total:-}" ] && [ "$total" -gt 0 ] || mm_die "df reported no size for $path"
percent=$(awk -v f="$free" -v t="$total" 'BEGIN { printf "%.1f", f * 100 / t }')

mm_write_status disk.json "$(jq -cn --arg checked_at "$(mm_now)" --argjson free_bytes "$free" \
  --argjson total_bytes "$total" --argjson free_percent "$percent" \
  '{checked_at: $checked_at, free_bytes: $free_bytes, total_bytes: $total_bytes,
    free_percent: $free_percent}')"

message="$percent % free on $path ($((free / 1024 / 1024)) MiB of $((total / 1024 / 1024)) MiB)"
url=$(mm_env_get HC_DISK_URL)
if awk -v p="$percent" -v m="$min_free" 'BEGIN { exit !(p < m) }'; then
  mm_log "low disk space: $message"
  mm_ping "$url" fail "low disk space: $message"
  exit 1
fi
mm_log "$message"
mm_ping "$url" ok "$message"
