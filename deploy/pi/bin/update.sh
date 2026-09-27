#!/usr/bin/env bash
# MealMate update with provenance verification and automatic rollback (OPS-05/06, PLT-03/07,
# SEC-12, plan § 11.5). Run nightly by mealmate-update.timer; can be run by hand:
#
#   sudo /srv/mealmate/bin/update.sh
#
# 0. Take state/deploy.lock. If state/update-in-progress exists, an earlier run was cut short:
#    finish it if the new version runs and is healthy, else roll back (step 7); nothing else.
# 1. Resolve the digest of ghcr.io/bublemann/mealmate:$IMAGE_TAG (the tag, never the pin). If it
#    is the running digest or a recorded bad digest: ping success and stop.
# 2. Verify its signed build provenance (cosign, retried). A verification failure records it as
#    bad; a network, registry or TUF problem only pings /fail, and the next run tries again.
# 3. Check that the current version is healthy (else ping /fail and stop). Pull the new one,
#    record the running digest in state/previous-digest, backup.sh --label pre-update.
# 4. Write state/update-in-progress, pin IMAGE_REF=<image>@<digest> in state/override.env and
#    `mm-compose up -d` (the entrypoint snapshots the database and migrates it).
# 5. Wait up to 180 s for stable health: the local endpoint plus the heartbeat's HTTPS check.
# 6. Healthy: install the new host files from the image (setup.sh --update-host-files), remove
#    other mealmate images except the current and the previous one, ping success.
# 7. Not healthy: record the bad digest, pin the previous one, stop, put the pre-update database
#    back (checked: integrity and the manifest's Alembic revision), always start the previous
#    version, ping /fail with what failed.
set -euo pipefail

here=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lib=$here/setup.sh
[ -f "$lib" ] || lib=$here/../setup.sh
# shellcheck source=deploy/pi/setup.sh
source "$lib"
mm_init update

case ${1:-} in
  "") ;;
  -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
  *) mm_die "unknown argument: $1" ;;
esac

hc_url=$(mm_env_get HC_UPDATE_URL)
result=fail

# shellcheck disable=SC2329 # called by the EXIT trap
finish() {
  local status=$?
  if [ "$status" -eq 0 ] && [ "$result" = ok ]; then
    mm_ping "$hc_url" ok
  else
    mm_ping "$hc_url" fail
  fi
  mm_end_runlog
  exit "$status"
}

# Removes images of this repository except the current and the previous digest (never prune).
remove_old_images() {
  local keep_current=$1 keep_previous=$2 repo tag digest
  while read -r repo tag digest; do
    [ "$repo" = "$MM_IMAGE" ] || continue
    if [ "$digest" = "$keep_current" ] || [ "$digest" = "$keep_previous" ]; then
      continue
    fi
    # Both references, so an image pulled by tag (before the pins existed) goes as well.
    if [ "$tag" != "<none>" ]; then
      "$DOCKER" image rm "$MM_IMAGE:$tag" >/dev/null 2>&1 || true
    fi
    if [ "$digest" != "<none>" ]; then
      if "$DOCKER" image rm "$MM_IMAGE@$digest" >/dev/null 2>&1; then
        mm_log "removed the old image $digest"
      fi
    fi
  done < <("$DOCKER" image ls --digests --format '{{.Repository}} {{.Tag}} {{.Digest}}' "$MM_IMAGE")
}

# Step 6: the new version is healthy.
complete_update() {
  local new=$1 previous=$2
  mm_log "the new version is healthy"
  rm -f -- "$MM_UPDATE_MARKER"
  if ! mm_host_files_from_image "$new"; then
    mm_die "updated to $new, but installing its host files failed; re-run sudo $MM_BIN/setup.sh to install them from the running image"
  fi
  remove_old_images "$new" "$previous"
  mm_log "updated $tag from $previous to $new"
  result=ok
}

# Rollback steps 3-5: the pre-update database into data/ (a rename, never through a planted
# symlink), checked against the snapshot's manifest. Returns 1 if anything failed.
restore_database() {
  local dir=$1 expected revision=
  if ! cp -- "$dir/db.sqlite3" "$MM_STATE/restore.tmp"; then
    rm -f -- "$MM_STATE/restore.tmp"
    mm_log "ERROR: copying $dir/db.sqlite3 failed"
    return 1
  fi
  if ! { chmod 0640 "$MM_STATE/restore.tmp" &&
    chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_STATE/restore.tmp" &&
    mv -fT -- "$MM_STATE/restore.tmp" "$MM_DATA/mealmate.db"; }; then
    rm -f -- "$MM_STATE/restore.tmp"
    mm_log "ERROR: moving the database into $MM_DATA failed"
    return 1
  fi
  expected=$(jq -r '.alembic_revision // empty' "$dir/manifest.json") || expected=
  if mm_is_plain_file "$MM_DATA/mealmate.db" && revision=$(mm_check_db "$MM_DATA/mealmate.db") &&
    [ -n "$expected" ] && [ "$revision" = "$expected" ]; then
    mm_log "database restored: integrity ok, revision $revision as in the snapshot"
    return 0
  fi
  mm_log "ERROR: the restored database does not match the snapshot (revision '${revision:-?}', expected '${expected:-?}')"
  return 1
}

# Step 7. What makes the previous version the target comes first, so even a rollback that is
# cut short leaves the Pi pinned to it (and the next run finishes it); every later step is
# guarded, and the previous version is always started at the end.
rollback() {
  local new=$1 previous=$2 snapshot=$3 failed=''
  mm_log "the new version is not healthy; rolling back to $previous and the database of snapshot $snapshot"
  mm_record_bad_digest "$new" || failed+=', recording the bad digest'
  mm_pin "$previous" || failed+=', pinning the previous digest'
  mm_compose stop || failed+=', stopping the app'
  rm -f -- "$MM_DATA/mealmate.db-wal" "$MM_DATA/mealmate.db-shm" "$MM_DATA/mealmate.db-journal" ||
    failed+=', removing the -wal/-shm/-journal files'
  if [[ ! $snapshot =~ $MM_SNAPSHOT_RE ]] || ! mm_is_plain_dir "$MM_BACKUPS/$snapshot"; then
    mm_log "ERROR: the pre-update snapshot '$snapshot' is missing"
    failed+=', restoring the database'
  elif ! restore_database "$MM_BACKUPS/$snapshot"; then
    failed+=', restoring the database'
  fi
  if ! mm_compose up -d; then
    mm_log "ERROR: starting the previous version failed"
    failed+=', starting the previous version'
  fi
  rm -f -- "$MM_UPDATE_MARKER"

  if mm_wait_healthy "$MM_HEALTH_TIMEOUT"; then
    mm_log "rolled back: the previous version $previous is healthy"
  elif [ -z "$failed" ]; then
    # Every rollback step worked, yet the version that was healthy before the update fails too
    # (the pre-update check passed): the problem is elsewhere (Tailscale, network, the Pi).
    mm_unrecord_bad_digest "$new" || true
    mm_log "ERROR: the previous version is not healthy either, although every rollback step worked; the problem is probably not $new, so it is NOT recorded as bad (the next update tries it again once the current version is healthy); check $MM_BIN/mm-compose logs app and tailscale serve status"
    failed=', the previous version is not healthy either'
  else
    mm_log "ERROR: the previous version is not healthy either; check $MM_BIN/mm-compose logs app"
    failed+=', the previous version is not healthy'
  fi
  if [ -n "$failed" ]; then
    mm_log "ERROR: rollback to $previous incomplete; failed: ${failed#, }"
  else
    mm_log "rollback to $previous complete; $new is recorded as bad"
  fi
}

# Step 0: an earlier run ended between writing the marker and its result (power loss, OOM,
# a killed process). Decides by what is pinned and what actually runs; always exits.
recover_interrupted() {
  local new previous snapshot pinned running
  new=$(mm_env_get digest "$MM_UPDATE_MARKER")
  previous=$(mm_env_get previous "$MM_UPDATE_MARKER")
  snapshot=$(mm_env_get snapshot "$MM_UPDATE_MARKER")
  if [[ ! $new =~ $MM_DIGEST_RE ]] || [[ ! $previous =~ $MM_DIGEST_RE ]]; then
    mm_die "$MM_UPDATE_MARKER is unreadable; compare state/override.env with state/previous-digest by hand (docs/operations.md, section 10), then delete it"
  fi
  mm_log "the update from $previous to $new did not finish (the run was interrupted)"
  pinned=$(mm_env_get IMAGE_REF "$MM_OVERRIDE")
  running=$(mm_running_image) || running=
  if [ "$pinned" = "$MM_IMAGE@$new" ] && [ "$running" = "$MM_IMAGE@$new" ] &&
    mm_wait_healthy "$MM_HEALTH_TIMEOUT"; then
    mm_log "$new is running and healthy; finishing that update"
    complete_update "$new" "$previous"
    exit 0
  fi
  if [ "$running" = "$MM_IMAGE@$previous" ] && mm_wait_healthy "$MM_HEALTH_TIMEOUT"; then
    # Cut short before `mm-compose up` replaced the container, or after a rollback started
    # the previous version again: the database is the previous version's own.
    mm_pin "$previous"
    rm -f -- "$MM_UPDATE_MARKER"
    mm_die "the previous version $previous is running and healthy; the pin is back on it and the next run tries the update again"
  fi
  rollback "$new" "$previous" "$snapshot"
  exit 1
}

install -d -m 0700 "$MM_STATE"
mm_start_runlog
trap finish EXIT
if ! mm_lock deploy 0; then
  mm_log "update.sh, setup.sh or --rotate-secret is already running (state/deploy.lock)"
  result=ok
  exit 0
fi

tag=$(mm_env_get IMAGE_TAG)
[ -n "$tag" ] || mm_die "IMAGE_TAG is not set in $MM_ENV_FILE"

# 0. Interrupted run.
if [ -f "$MM_UPDATE_MARKER" ]; then
  recover_interrupted
fi

# 1. Resolve.
new=$(mm_resolve_digest "$tag") || mm_die "cannot resolve $MM_IMAGE:$tag"
current=$(mm_current_digest) || current=
if [ "$new" = "$current" ]; then
  mm_log "up to date: $MM_IMAGE:$tag is $new"
  result=ok
  exit 0
fi
if mm_is_bad_digest "$new"; then
  mm_log "$new on $tag was rolled back before; waiting for a newer digest"
  result=ok
  exit 0
fi
mm_log "new digest on $tag: $new (running: ${current:-unknown})"

# 2. Verify.
verified=0
mm_verify_provenance "$new" || verified=$?
case $verified in
  0) ;;
  1)
    mm_record_bad_digest "$new"
    mm_die "$MM_IMAGE@$new has no valid build provenance; not installed"
    ;;
  *) mm_die "could not check the build provenance of $MM_IMAGE@$new (cosign, network or registry trouble, see above); not installed and not recorded as bad, the next run tries again" ;;
esac

# 3. Prepare.
[ -n "$current" ] || mm_die "cannot tell which digest is running, so there is no rollback target; pin it in state/override.env first (docs/operations.md)"
mm_log "checking that the current version is healthy before updating"
if ! mm_wait_healthy "$MM_PRECHECK_TIMEOUT"; then
  mm_die "current version unhealthy, update skipped (fix it first: $MM_BIN/mm-compose logs app, tailscale serve status)"
fi
"$DOCKER" pull --quiet "$MM_IMAGE@$new" >/dev/null || mm_die "pulling $MM_IMAGE@$new failed"
printf '%s\n' "$current" | mm_write_file "$MM_STATE/previous-digest" 0644 0:0
snapshot=$("$MM_BIN/backup.sh" --label pre-update | tail -n 1) || mm_die "the pre-update backup failed; not updating"
[[ $snapshot =~ $MM_SNAPSHOT_RE ]] && [ -d "$MM_BACKUPS/$snapshot" ] ||
  mm_die "the pre-update backup did not report a snapshot"
mm_log "pre-update backup: $snapshot"

# 4. Deploy. The marker lets the next run finish or roll back if this one is cut short.
printf 'digest=%s\nprevious=%s\nsnapshot=%s\nstarted_at=%s\n' "$new" "$current" "$snapshot" \
  "$(mm_now)" | mm_write_file "$MM_UPDATE_MARKER" 0644 0:0
mm_pin "$new"
healthy=0
if mm_compose up -d; then
  # 5. Wait.
  if mm_wait_healthy "$MM_HEALTH_TIMEOUT"; then
    healthy=1
  fi
else
  mm_log "mm-compose up failed"
fi

if [ "$healthy" = 1 ]; then
  # 6. Healthy.
  complete_update "$new" "$current"
  exit 0
fi

# 7. Not healthy.
rollback "$new" "$current" "$snapshot"
exit 1
