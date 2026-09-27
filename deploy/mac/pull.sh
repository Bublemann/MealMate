#!/bin/bash
# MealMate backup pull on the owner's Mac (OPS-03, OPS-10, plan § 11.3). launchd runs it every
# hour (de.mealmate.backup-pull); it can also be run by hand:
#
#   ~/.mealmate-backup/bin/pull.sh [--accept-abnormal]
#
# 1. List the Pi's snapshots (rsync --list-only over the read-only rrsync key). `.partial-*` and
#    every name that is not YYYYMMDDTHHMMSSZ are ignored: the names come from a possibly
#    compromised Pi.
# 2. Fetch each snapshot not yet in the ledger pulled.txt into .staging/ (--no-links,
#    --max-size=50M, hard links to the newest local snapshot), check the manifest's database
#    checksum, move it to snapshots/<receive time> and add it to the ledger. Ledger entries are
#    never fetched again, so nothing on the Mac is overwritten.
# 3. Abnormal pull (more new snapshots than 8 + 5 x days since the last successful pull, or more
#    than 2 GB): stop, do not prune, ping /fail. The first pull into an empty ledger is exempt;
#    --accept-abnormal accepts one such batch after the owner has checked it.
# 4. Retention by receive time with prune.py (never anything younger than 7 days).
# 5. Ping HC_MACPULL_URL.
#
# Configuration: ~/.mealmate-backup/config (written by install-backup-pull.sh) or $MM_PULL_CONFIG.
# macOS ships bash 3.2, so this script avoids newer bash features.
set -euo pipefail
umask 077

accept_abnormal=0
case ${1:-} in
  "") ;;
  --accept-abnormal) accept_abnormal=1 ;;
  -h | --help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

config=${MM_PULL_CONFIG:-$HOME/.mealmate-backup/config}
# shellcheck source=/dev/null
. "$config"

: "${MM_REMOTE:?MM_REMOTE is not set in $config}"
MM_DEST=${MM_DEST:-$HOME/MealMateBackups}
MM_RSYNC=${MM_RSYNC:-rsync}
MM_PYTHON=${MM_PYTHON:-python3}
MM_PRUNE=${MM_PRUNE:-$(dirname "$0")/prune.py}
MM_SSH_KEY=${MM_SSH_KEY:-$HOME/.ssh/id_ed25519_mealmate_backup}
MM_KNOWN_HOSTS=${MM_KNOWN_HOSTS:-$HOME/.mealmate-backup/known_hosts}
MM_RSYNC_MIN_VERSION=${MM_RSYNC_MIN_VERSION:-3.5.1}
MM_MAX_BYTES=${MM_MAX_BYTES:-2000000000}
MM_LOG=${MM_LOG:-$HOME/.mealmate-backup/pull.log}
HC_MACPULL_URL=${HC_MACPULL_URL:-}
CURL=${CURL:-curl}

# Snapshot names; an unquoted variable keeps =~ a regex in bash 3.2 as in later versions.
id_re='^[0-9]{8}T[0-9]{6}Z$'
snapshots=$MM_DEST/snapshots
staging=$MM_DEST/.staging
ledger=$MM_DEST/pulled.txt
state=$MM_DEST/.state
runlog=
lock=$MM_DEST/.lock

log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) pull: $*"
  echo "$line" >&2
  if [ -n "$runlog" ]; then
    echo "$line" >>"$runlog"
  fi
}

ping_hc() { # ok|fail
  local url=$HC_MACPULL_URL
  if [ -z "$url" ]; then
    return 0
  fi
  if [ "$1" = fail ]; then
    url="${url%/}/fail"
  fi
  tail -n 20 "$runlog" | "$CURL" -fsS -m 15 --retry 3 -o /dev/null --data-binary @- "$url" ||
    log "WARNING: could not reach the healthchecks.io ping URL"
}

fail() {
  log "ERROR: $*"
  ping_hc fail
  exit 1
}

cleanup() {
  if [ -n "$runlog" ]; then
    rm -f "$runlog"
  fi
  rm -rf "$lock"
}

version_at_least() { # have want
  "$MM_PYTHON" -c 'import sys
def v(s): return [int(p) for p in s.split(".")]
sys.exit(0 if v(sys.argv[1]) >= v(sys.argv[2]) else 1)' "$1" "$2"
}

# rsync to the Pi with the dedicated key and the pinned host key; a local path (tests) needs no
# ssh.
run_rsync() {
  case $MM_REMOTE in
    *:*)
      "$MM_RSYNC" -e "ssh -i $MM_SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$MM_KNOWN_HOSTS" "$@"
      ;;
    *) "$MM_RSYNC" "$@" ;;
  esac
}

newest_local() {
  local name newest=
  for name in "$snapshots"/*; do
    name=${name##*/}
    if [[ $name =~ $id_re ]] && [ -d "$snapshots/$name" ]; then
      newest=$name
    fi
  done
  echo "$newest"
}

in_ledger() {
  [ -f "$ledger" ] && awk -v id="$1" '$1 == id { found = 1 } END { exit !found }' "$ledger"
}

# Checks manifest.json against the files: the snapshot id and the SHA-256 of db.sqlite3.
check_snapshot() { # dir id
  "$MM_PYTHON" - "$1" "$2" <<'EOF'
import hashlib, json, os, sys
directory, expected_id = sys.argv[1], sys.argv[2]
def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)
try:
    with open(os.path.join(directory, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
except (OSError, ValueError) as exc:
    fail(f"manifest.json unreadable: {exc}")
if not isinstance(manifest, dict) or manifest.get("snapshot") != expected_id:
    fail("manifest.json does not belong to this snapshot")
digest = hashlib.sha256()
try:
    with open(os.path.join(directory, "db.sqlite3"), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
except OSError as exc:
    fail(f"db.sqlite3 missing: {exc}")
if digest.hexdigest() != manifest.get("db_sha256"):
    fail("db.sqlite3 does not match the manifest checksum")
EOF
}

mkdir -p "$MM_DEST" "$snapshots" "$state"
if [ -f "$MM_LOG" ] && [ "$(wc -c <"$MM_LOG")" -gt 524288 ]; then
  tail -n 500 "$MM_LOG" >"$MM_LOG.tmp" && cat "$MM_LOG.tmp" >"$MM_LOG" && rm -f "$MM_LOG.tmp"
fi
if ! mkdir "$lock" 2>/dev/null; then
  if [ -f "$lock/pid" ] && kill -0 "$(cat "$lock/pid")" 2>/dev/null; then
    echo "another pull is running" >&2
    exit 0
  fi
  rm -rf "$lock"
  mkdir "$lock"
fi
echo $$ >"$lock/pid"
runlog=$(mktemp "$state/run.XXXXXX")
trap cleanup EXIT

have=$("$MM_RSYNC" --version 2>/dev/null | sed -n '1s/.*version \([0-9][0-9.]*\).*/\1/p')
if [ -z "$have" ] || ! version_at_least "$have" "$MM_RSYNC_MIN_VERSION"; then
  fail "rsync ${have:-?} is too old (need >= $MM_RSYNC_MIN_VERSION; brew upgrade rsync)"
fi

# 1. List (directories only; symlinks and files on the Pi are never snapshots).
listing=$(run_rsync --list-only "${MM_REMOTE}./") || fail "listing the snapshots on the Pi failed"
new_ids=
new_count=0
rejected=0
set -f # the names are untrusted: no globbing while splitting the listing
for name in $(echo "$listing" | awk '$1 ~ /^d/ { print $NF }'); do
  case $name in
    . | .partial-*) continue ;;
  esac
  if ! [[ $name =~ $id_re ]]; then
    rejected=$((rejected + 1))
    continue
  fi
  if ! in_ledger "$name"; then
    new_ids="$new_ids $name"
    new_count=$((new_count + 1))
  fi
done
set +f
if [ "$rejected" -gt 0 ]; then
  log "WARNING: ignored $rejected unexpected names on the Pi"
fi
new_ids=$(echo "$new_ids" | tr ' ' '\n' | grep . | sort || true)

# 3. Abnormal-pull guard (before anything is fetched).
if [ "$new_count" -gt 0 ] && [ -s "$ledger" ] && [ "$accept_abnormal" -eq 0 ]; then
  now=$(date +%s)
  last=$(cat "$state/last-success" 2>/dev/null || echo "$now")
  limit=$(awk -v n="$now" -v l="$last" 'BEGIN { d = (n - l) / 86400; if (d < 0) d = 0; printf "%d", 8 + 5 * d }')
  if [ "$new_count" -gt "$limit" ]; then
    fail "abnormal pull: $new_count new snapshots (limit $limit); check the Pi, then run pull.sh --accept-abnormal"
  fi
  newest=$(newest_local)
  bytes=0
  for id in $new_ids; do
    size=$(run_rsync -rtH --no-links --max-size=50M --dry-run --stats \
      ${newest:+--link-dest="$snapshots/$newest"} "${MM_REMOTE}$id/" "$staging/dry-run/" |
      awk -F': ' '/^Total transferred file size/ { gsub(/[^0-9]/, "", $2); print $2 }') ||
      fail "sizing $id failed"
    bytes=$((bytes + ${size:-0}))
  done
  if [ "$bytes" -gt "$MM_MAX_BYTES" ]; then
    fail "abnormal pull: $bytes bytes in $new_count new snapshots (limit $MM_MAX_BYTES); check the Pi, then run pull.sh --accept-abnormal"
  fi
fi

# 2. Fetch.
failures=0
fetched=0
fetch() { # id [link-dest]
  rm -rf "$staging"
  mkdir -p "$staging"
  run_rsync -rtH --no-links --max-size=50M ${2:+--link-dest="$snapshots/$2"} \
    "${MM_REMOTE}$1/" "$staging/$1/"
}

for id in $new_ids; do
  newest=$(newest_local)
  if ! fetch "$id" "$newest"; then
    log "fetching $id failed; retried on the next run"
    failures=$((failures + 1))
    continue
  fi
  # rsync's quick check (size and time) could hard-link a file of the previous snapshot that
  # only looks unchanged; a snapshot that fails its check is fetched once more in full.
  if ! check_snapshot "$staging/$id" "$id" 2>/dev/null && [ -n "$newest" ]; then
    fetch "$id" || true
  fi
  if ! problem=$(check_snapshot "$staging/$id" "$id" 2>&1); then
    log "rejected $id: $problem"
    echo "$id rejected $(date -u +%Y%m%dT%H%M%SZ)" >>"$ledger"
    failures=$((failures + 1))
    continue
  fi
  received=$(date -u +%Y%m%dT%H%M%SZ)
  while [ -e "$snapshots/$received" ]; do
    sleep 1
    received=$(date -u +%Y%m%dT%H%M%SZ)
  done
  mv "$staging/$id" "$snapshots/$received"
  echo "$id $received" >>"$ledger"
  fetched=$((fetched + 1))
  log "pulled $id as $received"
done
rm -rf "$staging"

# 4. Retention by receive time; labels come from the Pi and are ignored.
"$MM_PYTHON" "$MM_PRUNE" --labels ignore "$snapshots" >&2 || fail "retention failed"

if [ "$failures" -gt 0 ]; then
  fail "$failures of $new_count new snapshots failed"
fi
date +%s >"$state/last-success"
log "ok: $fetched new snapshots, $(newest_local) is the newest"
ping_hc ok
