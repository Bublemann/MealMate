#!/usr/bin/env bash
# MealMate backup (OPS-01/02/07/08, plan § 11.3). Run by mealmate-backup.timer (every 6 hours),
# mealmate-backup.path (the admin page's "Back up now"), update.sh (before an update) and the
# monthly mealmate-restore-test.timer (--verify-latest).
#
#   backup.sh [--label regular|pre-update|manual]   a new snapshot in backups/<UTC time>/
#   backup.sh --verify-latest                       integrity + checksum of the newest snapshot
#
# A snapshot is written to backups/.partial-<ts>/ and renamed when complete: db.sqlite3,
# media/ (read as the app user through media-mirror/; unchanged photos hard-linked to the
# previous snapshot), secrets/ (.env, Tailscale state, SSH host keys, the backup key) and
# manifest.json. Then retention (prune.py), state/status/backup.json for the admin page and the
# healthchecks.io ping. On success the snapshot name is the last line on stdout.
set -euo pipefail

here=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lib=$here/setup.sh
[ -f "$lib" ] || lib=$here/../setup.sh
# shellcheck source=deploy/pi/setup.sh
source "$lib"
mm_init backup

label=regular
mode=backup
while [ $# -gt 0 ]; do
  case $1 in
    --label) label=${2:?--label needs a value}; shift 2 ;;
    --verify-latest) mode=verify; shift ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
    *) mm_die "unknown argument: $1" ;;
  esac
done
case $label in
  regular | pre-update | manual) ;;
  *) mm_die "--label must be regular, pre-update or manual" ;;
esac

hc_url=$(mm_env_get HC_BACKUP_URL)
group=$MM_BACKUP_GROUP
snapshot=
partial=

# The admin page's request file (OPS-08): removed first, so the path unit does not trigger
# again. `rm -f` removes a symlink instead of following it.
consume_request() {
  if mm_is_plain_dir "$MM_DATA/status"; then
    rm -f -- "$MM_DATA/status/backup-request"
  fi
}

finish() {
  local status=$?
  if [ -n "$partial" ] && [ -e "$partial" ]; then
    rm -rf -- "$partial"
  fi
  if [ "$mode" = backup ]; then
    local ok=false message size=null snap=null
    if [ "$status" -eq 0 ]; then
      ok=true
      size=$(du -sb -- "$MM_BACKUPS/$snapshot" | cut -f1)
      snap="\"$snapshot\""
      message="backup $snapshot ($label) complete"
    else
      message=$(tail -n 1 -- "$MM_RUNLOG" 2>/dev/null | cut -d' ' -f3- | head -c 300)
      message=${message:-backup failed}
    fi
    mm_write_status backup.json "$(jq -cn --arg finished_at "$(mm_now)" --arg label "$label" \
      --argjson ok "$ok" --argjson snapshot "$snap" --argjson size_bytes "$size" \
      --arg message "$message" \
      '{finished_at: $finished_at, label: $label, ok: $ok, snapshot: $snapshot,
        size_bytes: $size_bytes, message: $message}')" || true
  fi
  if [ "$status" -eq 0 ]; then
    mm_ping "$hc_url" ok
  else
    mm_log "failed"
    mm_ping "$hc_url" fail
  fi
  mm_end_runlog
  exit "$status"
}

verify_latest() {
  local latest dir sha file expected
  latest=$(mm_latest_snapshot) || mm_die "no snapshot to verify"
  dir=$MM_BACKUPS/$latest
  mm_log "verifying snapshot $latest"
  mm_is_plain_file "$dir/manifest.json" || mm_die "$latest has no manifest.json"
  sha=$(jq -r '.db_sha256 // empty' "$dir/manifest.json")
  [ "$(mm_sha256 "$dir/db.sqlite3")" = "$sha" ] || mm_die "$latest: db.sqlite3 does not match the manifest"
  mm_check_db "$dir/db.sqlite3" >/dev/null || mm_die "$latest: integrity check failed"
  while IFS=$'\t' read -r file expected; do
    [ "$(mm_sha256 "$dir/$file")" = "$expected" ] || mm_die "$latest: $file does not match the manifest"
  done < <(jq -r '.files // {} | to_entries[] | "\(.key)\t\(.value)"' "$dir/manifest.json")
  mm_log "snapshot $latest verified (integrity ok, checksums match)"
}

# Moves the container's copy out of data/ and accepts only a single regular file: after the
# rename the container can no longer reach it, so the checks cannot be raced.
take_db_copy() {
  local copy=$partial/db.sqlite3
  mm_is_plain_dir "$MM_DATA/status" || mm_die "$MM_DATA/status is not a directory"
  mv -fT -- "$MM_DATA/status/backup.sqlite3" "$copy"
  if ! mm_is_plain_file "$copy" || [ "$(stat -c %h -- "$copy")" != 1 ]; then
    rm -f -- "$copy"
    mm_die "the database copy is not a single regular file (symlink or hard link)"
  fi
  chown -h "0:$group" "$copy"
  chmod 0640 "$copy"
}

copy_secrets() {
  local dir=$partial/secrets file home
  install -d -m 0750 -o 0 -g "$group" "$dir" "$dir/ssh"
  install -m 0640 -o 0 -g "$group" "$MM_ENV_FILE" "$dir/env"
  if [ -f "$MM_TS_STATE_DIR/tailscaled.state" ]; then
    install -m 0640 -o 0 -g "$group" "$MM_TS_STATE_DIR/tailscaled.state" "$dir/tailscaled.state"
  else
    mm_log "WARNING: no Tailscale state in $MM_TS_STATE_DIR"
  fi
  for file in "$MM_SSH_DIR"/ssh_host_*; do
    if [ -f "$file" ]; then
      install -m 0640 -o 0 -g "$group" "$file" "$dir/ssh/${file##*/}"
    fi
  done
  home=$(mm_backup_home)
  if [ -n "$home" ] && [ -f "$home/.ssh/authorized_keys" ]; then
    install -m 0640 -o 0 -g "$group" "$home/.ssh/authorized_keys" "$dir/mmbackup_authorized_keys"
  fi
}

# data/media is read with the app user's rights only (uid 10001, no groups): the container can
# change data/ while rsync walks it (e.g. swap a directory for a symlink between rsync's listing
# and its reads), and whatever that reaches must never be more than the container can read
# itself. The copy goes to media-mirror/ (the app user's, 0700, outside data/, so the container
# cannot reach it), incrementally; root then snapshots the mirror, whose only writer is this
# rsync. The filter keeps rsync on data/media, --no-links skips symlinks (also a symlinked
# media/). Exit code 24 (a photo deleted meanwhile) is fine.
copy_media() {
  local status=0
  if ! mm_is_plain_dir "$MM_MEDIA_MIRROR"; then
    rm -f -- "$MM_MEDIA_MIRROR"
    install -d -m 0700 -o "$MM_APP_UID" -g "$MM_APP_UID" "$MM_MEDIA_MIRROR"
  fi
  chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_MEDIA_MIRROR"
  chmod 0700 "$MM_MEDIA_MIRROR"
  "$SETPRIV" --reuid="$MM_APP_UID" --regid="$MM_APP_UID" --clear-groups -- \
    "$RSYNC" -rt --delete --no-links --chmod=D0700,F0600 \
    --include='/media/***' --exclude='*' -- "$MM_DATA/" "$MM_MEDIA_MIRROR/" >&2 || status=$?
  case $status in
    0 | 24) ;;
    *) mm_die "copying the photos as the app user (uid $MM_APP_UID) failed (rsync exit $status; see above)" ;;
  esac
}

run_backup() {
  local ts previous cid version commit digest revision files media_count
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  while [ -e "$MM_BACKUPS/$ts" ] || [ -e "$MM_BACKUPS/.partial-$ts" ]; do
    sleep 1
    ts=$(date -u +%Y%m%dT%H%M%SZ)
  done
  previous=$(mm_latest_snapshot) || previous=
  # Leftovers of an interrupted run.
  rm -rf -- "$MM_BACKUPS"/.partial-*
  partial=$MM_BACKUPS/.partial-$ts
  install -d -m 0750 -o 0 -g "$group" "$partial"
  mm_log "backup $ts ($label) started"

  # 1. Consistent copy via the SQLite backup API, integrity-checked by the app (OPS-01).
  mm_compose exec -T app mealmate backup-db /data/status/backup.sqlite3 >/dev/null ||
    mm_die "mealmate backup-db failed (is the app running?)"
  take_db_copy
  revision=$(mm_check_db "$partial/db.sqlite3") || mm_die "the database copy fails the integrity check"

  # 2. Photos; unchanged ones are hard links into the previous snapshot.
  copy_media
  "$RSYNC" -rtpog --no-links --chmod=D0750,F0640 --chown="0:$group" \
    ${previous:+--link-dest="$MM_BACKUPS/$previous"} \
    --include='/media/***' --exclude='*' -- "$MM_MEDIA_MIRROR/" "$partial/"
  install -d -m 0750 -o 0 -g "$group" "$partial/media"
  media_count=$(find "$partial/media" -type f | wc -l)

  # 3. Credentials (OPS-10).
  copy_secrets

  # 4. Manifest.
  cid=$(mm_container)
  version=$("$DOCKER" inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$cid" 2>/dev/null) || version=
  commit=$("$DOCKER" inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$cid" 2>/dev/null) || commit=
  digest=$(mm_current_digest) || digest=
  files=$(cd "$partial" && find secrets -type f | sort | while read -r f; do
    printf '%s\t%s\n' "$f" "$(mm_sha256 "$f")"
  done | jq -Rn '[inputs | split("\t") | {(.[0]): .[1]}] | add // {}')
  jq -n --arg snapshot "$ts" --arg created_at "$(mm_now)" --arg label "$label" \
    --arg app_version "$version" --arg app_commit "$commit" --arg image_digest "$digest" \
    --arg alembic_revision "$revision" --arg db_sha256 "$(mm_sha256 "$partial/db.sqlite3")" \
    --argjson media_files "$media_count" --argjson files "$files" \
    '{format: 1, snapshot: $snapshot, created_at: $created_at, label: $label,
      app_version: ($app_version | select(. != "") // null),
      app_commit: ($app_commit | select(. != "") // null),
      image_digest: ($image_digest | select(. != "") // null),
      alembic_revision: $alembic_revision, db_sha256: $db_sha256,
      media_files: $media_files, files: $files}' |
    mm_write_file "$partial/manifest.json" 0640 "0:$group"

  # Visible only once complete.
  mv -T -- "$partial" "$MM_BACKUPS/$ts"
  partial=
  snapshot=$ts
  mm_log "backup $ts ($label) complete: $media_count photos, revision $revision"

  # 5. Retention (OPS-02).
  "$PYTHON3" "$(mm_find_prune)" --labels manifest "$MM_BACKUPS" >&2 ||
    mm_log "WARNING: retention failed"
}

install -d -m 0700 "$MM_STATE"
mm_start_runlog
trap finish EXIT
if [ "$mode" = verify ]; then
  mm_lock backup 1800 || mm_die "another backup is still running"
  verify_latest
  exit 0
fi
if [ "$label" = manual ]; then
  consume_request
fi
mm_lock backup 1800 || mm_die "another backup is still running"
run_backup
printf '%s\n' "$snapshot"
