#!/usr/bin/env bash
# MealMate Pi setup (PLT-06, plan § 11.2) and the shared function library of the host scripts.
#
# Bootstrap on a freshly flashed card (Raspberry Pi OS Lite 64-bit, see docs/operations.md):
#
#   curl -fsSLO https://github.com/Bublemann/MealMate/releases/download/v<ver>/setup.sh
#   sha256sum setup.sh            # compare with the release notes
#   sudo bash setup.sh --version <ver> [--restore <snapshot-dir>]
#
# Modes (all idempotent; re-running is always safe):
#   --version <ver>              fresh install / re-run: steps 1-9 of plan § 11.2. A re-run keeps
#                                the installed (pinned) version; only update.sh moves forward
#   --restore <snapshot-dir>     the same on a new card, but with the identity and data of a
#                                backup snapshot (plan § 11.6); needs --version on a fresh card
#   --update-host-files [--from <deploy-dir>]
#                                install compose.yml, bin/ and the systemd units from a deploy
#                                directory (used by update.sh with the new image's files)
#   --rotate-secret              new MEALMATE_SECRET_KEY, restart (logs everyone out, OPS-10)
#   --set-backup-key <type> <key>
#                                the Mac's backup-pull key for mmbackup (read-only rrsync)
#   --skip-system                skip steps 1-4 and user creation (tests; also
#                                MEALMATE_SKIP_SYSTEM=1)
#
# Sourced by the scripts in bin/ (backup.sh, update.sh, ...) for the shared functions; nothing
# runs then. Every path and tool can be overridden for tests (docs/operations.md, "Test
# overrides"): MEALMATE_ROOT (default /srv/mealmate), DOCKER, TAILSCALE, COSIGN, CURL, SYSTEMCTL,
# SQLITE3, PYTHON3, RSYNC, SETPRIV, APT_GET and the MEALMATE_* variables in mm_init below.
set -euo pipefail

# --- Pinned constants -------------------------------------------------------------------------

MM_DEFAULT_IMAGE=ghcr.io/bublemann/mealmate
MM_APP_UID=10001

# cosign release binary, verified by SHA-256 (from the release's cosign_checksums.txt, checked
# against the downloaded binaries). Bump both together.
MM_COSIGN_VERSION=v3.1.3
MM_COSIGN_SHA256_ARM64=c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a
MM_COSIGN_SHA256_AMD64=4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71

# Signed build provenance of build-image.yml on a release tag (SEC-12, plan § 11.5).
MM_OIDC_ISSUER=https://token.actions.githubusercontent.com
MM_IDENTITY_REGEXP='^https://github\.com/Bublemann/MealMate/\.github/workflows/build-image\.yml@refs/tags/v[0-9].*$'

# Fingerprints of the apt repository signing keys (primary keys).
MM_DOCKER_KEY_FPR=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
MM_TAILSCALE_KEY_FPR=${TAILSCALE_KEY_FPR:-2596A99EAAB33821893C0A79458CA832957F5868}

MM_SNAPSHOT_RE='^[0-9]{8}T[0-9]{6}Z$'
MM_DIGEST_RE='^sha256:[0-9a-f]{64}$'
# state/bad-digest keeps the most recent entries only.
MM_BAD_DIGEST_KEEP=20

# --- Environment ------------------------------------------------------------------------------

mm_init() {
  MM_PROG=${1:-setup}
  MM_ROOT=${MEALMATE_ROOT:-/srv/mealmate}
  MM_ROOT=${MM_ROOT%/}
  MM_IMAGE=${MEALMATE_IMAGE:-$MM_DEFAULT_IMAGE}
  MM_DATA=$MM_ROOT/data
  MM_STATE=$MM_ROOT/state
  MM_BACKUPS=$MM_ROOT/backups
  MM_BIN=$MM_ROOT/bin
  MM_ENV_FILE=$MM_ROOT/.env
  MM_OVERRIDE=$MM_STATE/override.env
  MM_SYSTEMD_DIR=${MEALMATE_SYSTEMD_DIR:-/etc/systemd/system}
  MM_TS_STATE_DIR=${MEALMATE_TAILSCALE_STATE_DIR:-/var/lib/tailscale}
  MM_SSH_DIR=${MEALMATE_SSH_DIR:-/etc/ssh}
  MM_BACKUP_USER=${MEALMATE_BACKUP_USER:-mmbackup}
  MM_BACKUP_GROUP=${MEALMATE_BACKUP_GROUP:-mmbackup}
  MM_BACKUP_HOME=${MEALMATE_BACKUP_HOME:-}
  # shellcheck disable=SC2034 # backup.sh: data/media as read by the app user (uid 10001)
  MM_MEDIA_MIRROR=$MM_ROOT/media-mirror
  # shellcheck disable=SC2034 # update.sh: written before deploying, removed with the result
  MM_UPDATE_MARKER=$MM_STATE/update-in-progress
  MM_LOCAL_URL=${MEALMATE_LOCAL_URL:-http://127.0.0.1:8080}
  # Healthy = N consecutive good checks INTERVAL seconds apart, same container, no restart.
  MM_HEALTH_TIMEOUT=${MEALMATE_HEALTH_TIMEOUT:-180}
  MM_HEALTH_STABLE_CHECKS=${MEALMATE_HEALTH_STABLE_CHECKS:-3}
  MM_HEALTH_STABLE_INTERVAL=${MEALMATE_HEALTH_STABLE_INTERVAL:-10}
  MM_HEALTH_POLL_INTERVAL=${MEALMATE_HEALTH_POLL_INTERVAL:-2}
  # shellcheck disable=SC2034 # update.sh: health of the current version before an update
  MM_PRECHECK_TIMEOUT=${MEALMATE_PRECHECK_TIMEOUT:-60}
  MM_COSIGN_ATTEMPTS=${MEALMATE_COSIGN_ATTEMPTS:-3}
  MM_COSIGN_RETRY_DELAY=${MEALMATE_COSIGN_RETRY_DELAY:-30}
  MM_LOCK_WAIT=${MEALMATE_LOCK_WAIT:-900}
  MM_SKIP_SYSTEM=${MEALMATE_SKIP_SYSTEM:-0}
  DOCKER=${DOCKER:-docker}
  TAILSCALE=${TAILSCALE:-tailscale}
  COSIGN=${COSIGN:-/usr/local/bin/cosign}
  CURL=${CURL:-curl}
  SYSTEMCTL=${SYSTEMCTL:-systemctl}
  SQLITE3=${SQLITE3:-sqlite3}
  PYTHON3=${PYTHON3:-python3}
  RSYNC=${RSYNC:-rsync}
  SETPRIV=${SETPRIV:-setpriv}
  APT_GET=${APT_GET:-apt-get}
  # mm-compose and child scripts see the same root and tools.
  export MEALMATE_ROOT=$MM_ROOT DOCKER TAILSCALE COSIGN CURL SYSTEMCTL SQLITE3 PYTHON3 RSYNC \
    SETPRIV APT_GET
  # cosign keeps its Sigstore trust root under $HOME; systemd does not set it for root units.
  export HOME=${HOME:-/root}
  export PATH=$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  MM_RUNLOG=${MM_RUNLOG:-}
  umask 022
}

# --- Logging and healthchecks.io --------------------------------------------------------------

mm_log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) ${MM_PROG:-mealmate}: $*"
  printf '%s\n' "$line" >&2
  if [ -n "${MM_RUNLOG:-}" ]; then
    printf '%s\n' "$line" >>"$MM_RUNLOG" 2>/dev/null || true
  fi
}

mm_die() {
  mm_log "ERROR: $*"
  exit 1
}

# Collects this run's own log lines (never app logs) for the healthchecks.io ping body.
mm_start_runlog() {
  MM_RUNLOG=$(mktemp "$MM_STATE/.log-$MM_PROG.XXXXXX")
}

mm_end_runlog() {
  if [ -n "${MM_RUNLOG:-}" ]; then
    rm -f -- "$MM_RUNLOG"
  fi
  MM_RUNLOG=
}

# mm_ping <url> ok|fail [message]: pings a check; the body defaults to the last log lines.
mm_ping() {
  local url=$1 kind=$2 body=${3:-}
  if [ -z "$url" ]; then
    return 0
  fi
  if [ "$kind" = fail ]; then
    url="${url%/}/fail"
  fi
  if [ -z "$body" ] && [ -n "${MM_RUNLOG:-}" ] && [ -f "$MM_RUNLOG" ]; then
    body=$(tail -n 20 -- "$MM_RUNLOG")
  fi
  if ! printf '%s\n' "$body" | head -c 10000 |
    "$CURL" -fsS -m 15 --retry 3 -o /dev/null --data-binary @- "$url"; then
    mm_log "WARNING: could not reach the healthchecks.io ping URL"
  fi
}

# --- Files ------------------------------------------------------------------------------------

# mm_env_get <key> [file]: the value of KEY=value in an env file (empty if missing).
mm_env_get() {
  local file=${2:-$MM_ENV_FILE} line
  if [ ! -f "$file" ]; then
    return 0
  fi
  line=$(grep -E "^$1=" -- "$file" | tail -n 1) || true
  line=${line#*=}
  line=${line%\"}
  line=${line#\"}
  printf '%s' "$line"
}

# mm_write_file <dest> <mode> <owner> [tmpdir] < content: atomic replace via a temp file in the
# same filesystem, `chown -h` and `mv -fT`; a rename replaces a planted symlink instead of
# following it (SEC-09, plan § 11.1).
mm_write_file() {
  local dest=$1 mode=$2 owner=$3 dir=${4:-} tmp
  if [ -z "$dir" ]; then
    dir=$(dirname -- "$dest")
  fi
  tmp=$(mktemp "$dir/.mm-tmp.XXXXXX")
  if ! cat >"$tmp"; then
    rm -f -- "$tmp"
    return 1
  fi
  chmod "$mode" "$tmp"
  chown -h "$owner" "$tmp"
  mv -fT -- "$tmp" "$dest"
}

# mm_install_file <src> <dest> <mode>: atomic install; a running script keeps its old inode.
mm_install_file() {
  local tmp
  tmp=$(mktemp "$(dirname -- "$2")/.mm-new.XXXXXX")
  cp -- "$1" "$tmp"
  chmod "$3" "$tmp"
  chown -h 0:0 "$tmp"
  mv -fT -- "$tmp" "$2"
}

# mm_env_set <key> <value>: sets KEY in .env (mode 0600, root).
mm_env_set() {
  local key=$1 value=$2
  {
    if [ -f "$MM_ENV_FILE" ]; then
      grep -vE "^$key=" -- "$MM_ENV_FILE" || true
    fi
    printf '%s=%s\n' "$key" "$value"
  } | mm_write_file "$MM_ENV_FILE" 0600 0:0
}

# mm_write_status <name> <json>: state/status/<name>, read by the app at /status (read-only).
mm_write_status() {
  printf '%s\n' "$2" | mm_write_file "$MM_STATE/status/$1" 0644 0:0 "$MM_STATE"
}

mm_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

# A regular file that is not a symlink (for anything read from the container-writable data/).
mm_is_plain_file() {
  [ -f "$1" ] && [ ! -L "$1" ]
}

mm_is_plain_dir() {
  [ -d "$1" ] && [ ! -L "$1" ]
}

# mm_lock <name> <wait-seconds>: holds state/<name>.lock until the script exits. `deploy` is
# the one lock of everything that changes the running version, the pin, Tailscale or .env
# (update.sh, setup.sh, --rotate-secret); the heartbeat stays silent while it is held.
mm_lock() {
  local fd
  exec {fd}>"$MM_STATE/$1.lock"
  flock -w "$2" "$fd"
}

# True while another script holds state/<name>.lock.
mm_lock_held() {
  [ -e "$MM_STATE/$1.lock" ] && ! flock -n "$MM_STATE/$1.lock" true
}

mm_sha256() {
  sha256sum -- "$1" | cut -d' ' -f1
}

# mm_sqlite <file> <sql>: read-only, immutable access (never creates -wal/-shm/-journal files).
mm_sqlite() {
  "$SQLITE3" -batch -noheader "file:$1?mode=ro&immutable=1" "$2"
}

# mm_check_db <file>: integrity check; prints the Alembic revision.
mm_check_db() {
  local result
  result=$(mm_sqlite "$1" 'PRAGMA integrity_check;') || return 1
  if [ "$result" != ok ]; then
    mm_log "integrity check of $1 failed: $(printf '%s' "$result" | head -n 3 | tr '\n' ' ')"
    return 1
  fi
  mm_sqlite "$1" 'SELECT version_num FROM alembic_version;'
}

# Newest complete snapshot in backups/ (by name).
mm_latest_snapshot() {
  local name latest=
  for name in "$MM_BACKUPS"/*; do
    name=${name##*/}
    if [[ $name =~ $MM_SNAPSHOT_RE ]] && mm_is_plain_dir "$MM_BACKUPS/$name"; then
      latest=$name
    fi
  done
  [ -n "$latest" ] && printf '%s' "$latest"
}

mm_find_prune() {
  local here
  here=$(dirname -- "${BASH_SOURCE[0]}")
  for candidate in "$MM_BIN/prune.py" "$here/prune.py" "$here/../common/prune.py"; do
    if [ -f "$candidate" ]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

mm_backup_home() {
  if [ -n "$MM_BACKUP_HOME" ]; then
    printf '%s' "$MM_BACKUP_HOME"
  else
    getent passwd "$MM_BACKUP_USER" | cut -d: -f6
  fi
}

# --- Docker and the image ---------------------------------------------------------------------

mm_compose() {
  "$MM_BIN/mm-compose" "$@"
}

mm_container() {
  mm_compose ps -q app 2>/dev/null | head -n 1
}

# The image reference the running app container was created from (e.g. <image>@sha256:...).
mm_running_image() {
  local cid
  cid=$(mm_container)
  [ -n "$cid" ] && "$DOCKER" inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null
}

# The digest the app runs: the IMAGE_REF pin, else the running image's repo digest.
mm_current_digest() {
  local ref cid image digest
  ref=$(mm_env_get IMAGE_REF "$MM_OVERRIDE")
  if [[ $ref == *@sha256:* ]]; then
    printf '%s' "${ref##*@}"
    return 0
  fi
  cid=$(mm_container)
  if [ -z "$cid" ]; then
    return 1
  fi
  image=$("$DOCKER" inspect --format '{{.Image}}' "$cid") || return 1
  digest=$("$DOCKER" image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" |
    grep -F "$MM_IMAGE@" | head -n 1) || true
  [ -n "$digest" ] && printf '%s' "${digest##*@}"
}

# The digest a tag points to in the registry (the multi-arch index).
mm_resolve_digest() {
  local digest
  digest=$("$DOCKER" buildx imagetools inspect "$MM_IMAGE:$1" --format '{{json .Manifest}}' |
    jq -r '.digest // empty') || return 1
  if [[ ! $digest =~ $MM_DIGEST_RE ]]; then
    mm_log "unexpected digest for $MM_IMAGE:$1: '$digest'"
    return 1
  fi
  printf '%s' "$digest"
}

# Classifies a failed cosign run by its stderr (on stdin): prints `definite` when cosign proved
# that the image has no valid provenance from this repository's release workflow (no matching
# attestation, wrong identity or issuer, bad signature), else `transient` (network, registry,
# TUF or Rekor trouble, anything unknown). Only a definite failure blacklists a digest; the
# transient patterns win, so a network error inside a verification message is never definite.
# The patterns follow the messages of cosign v3 (pkg/cosign/verify.go, verify_attestation.go).
mm_cosign_failure_kind() {
  local text transient definite
  transient='dial tcp|i/o timeout|timed? ?out|deadline exceeded|connection (refused|reset)'
  transient+='|no such host|TLS handshake|network is unreachable|temporary failure'
  transient+='|unexpected EOF|status code [45][0-9][0-9]|too many requests|service unavailable'
  transient+='|bad gateway|internal server error|UNAUTHORIZED|DENIED|TOOMANYREQUESTS'
  transient+='|MANIFEST_UNKNOWN|NAME_UNKNOWN|(^|[^a-z])tuf([^a-z]|$)|trusted root|rekor'
  definite='no matching attestations|no valid bundles|none of the attestations matched'
  definite+='|none of the expected identities matched|expected [a-z ]+ not found in certificate'
  definite+='|no matching signatures|no signatures found|invalid signature'
  definite+='|signature in bundle does not match|failed to verify signature'
  definite+='|no matching CertificateIdentity'
  text=$(cat)
  if grep -qiE -- "$transient" <<<"$text"; then
    echo transient
  elif grep -qiE -- "$definite" <<<"$text"; then
    echo definite
  else
    echo transient
  fi
}

# mm_verify_provenance <digest>: signed build provenance from this repository's release
# workflow (SEC-12, plan § 11.5). Returns 0 if verified, 1 if cosign proved it invalid (a
# definite failure), 2 if it could not be checked (after MM_COSIGN_ATTEMPTS tries with a
# growing pause). cosign's last error lines go to the log and so into the /fail ping.
mm_verify_provenance() {
  local digest=$1 attempt err kind line
  err=$(mktemp)
  for ((attempt = 1; attempt <= MM_COSIGN_ATTEMPTS; attempt++)); do
    mm_log "verifying the build provenance of $MM_IMAGE@$digest (attempt $attempt of $MM_COSIGN_ATTEMPTS)"
    if "$COSIGN" verify-attestation --type slsaprovenance1 \
      --certificate-oidc-issuer "$MM_OIDC_ISSUER" \
      --certificate-identity-regexp "$MM_IDENTITY_REGEXP" \
      "$MM_IMAGE@$digest" >/dev/null 2>"$err"; then
      rm -f -- "$err"
      mm_log "build provenance verified"
      return 0
    fi
    while IFS= read -r line; do
      mm_log "cosign: $line"
    done < <(grep -v '^[[:space:]]*$' "$err" | tail -n 5 | cut -c 1-400)
    kind=$(mm_cosign_failure_kind <"$err")
    if [ "$kind" = definite ]; then
      rm -f -- "$err"
      mm_log "cosign: the provenance is invalid (a verification failure, not a network problem)"
      return 1
    fi
    if ((attempt < MM_COSIGN_ATTEMPTS)); then
      mm_log "cosign could not check the provenance; trying again in $((MM_COSIGN_RETRY_DELAY * attempt)) s"
      sleep "$((MM_COSIGN_RETRY_DELAY * attempt))"
    fi
  done
  rm -f -- "$err"
  return 2
}

mm_is_bad_digest() {
  [ -f "$MM_STATE/bad-digest" ] && grep -qxF -- "$1" "$MM_STATE/bad-digest"
}

# Appends a digest to state/bad-digest (oldest first, the last MM_BAD_DIGEST_KEEP kept).
mm_record_bad_digest() {
  {
    if [ -f "$MM_STATE/bad-digest" ]; then
      grep -vxF -- "$1" "$MM_STATE/bad-digest" || true
    fi
    printf '%s\n' "$1"
  } | tail -n "$MM_BAD_DIGEST_KEEP" | mm_write_file "$MM_STATE/bad-digest" 0644 0:0
  mm_log "recorded $1 as bad in state/bad-digest; it is skipped until a newer digest appears on the tag"
}

mm_unrecord_bad_digest() {
  if [ -f "$MM_STATE/bad-digest" ]; then
    { grep -vxF -- "$1" "$MM_STATE/bad-digest" || true; } |
      mm_write_file "$MM_STATE/bad-digest" 0644 0:0
  fi
}

mm_pin() {
  printf 'IMAGE_REF=%s@%s\n' "$MM_IMAGE" "$1" | mm_write_file "$MM_OVERRIDE" 0600 0:0
}

mm_app_healthy_local() {
  "$CURL" -fsS -m 5 --noproxy '*' -o /dev/null "$MM_LOCAL_URL/api/health" 2>/dev/null
}

# The heartbeat's check: through `tailscale serve` with its certificate (plan § 11.4).
mm_app_healthy_public() {
  local url
  url=$(mm_env_get MEALMATE_PUBLIC_URL)
  [ -n "$url" ] && "$CURL" -fsS -m 10 -o /dev/null "${url%/}/api/health" 2>/dev/null
}

# The app container's identity and restarts: "<id> <restart count> <started at>".
mm_container_state() {
  local cid
  cid=$(mm_container)
  [ -n "$cid" ] && "$DOCKER" inspect --format '{{.Id}} {{.RestartCount}} {{.State.StartedAt}}' \
    "$cid" 2>/dev/null
}

# mm_wait_healthy <seconds> [local]: waits for *stable* health, the local endpoint plus the
# public HTTPS check (unless `local`): MM_HEALTH_STABLE_CHECKS good checks in a row,
# MM_HEALTH_STABLE_INTERVAL seconds apart, all in the same container without a restart in
# between. A version that answers once and then crashes (and is restarted) never counts.
mm_wait_healthy() {
  local deadline=$((SECONDS + $1)) mode=${2:-} streak=0 state last=
  while ((SECONDS < deadline)); do
    state=$(mm_container_state) || state=
    if [ -n "$state" ] && mm_app_healthy_local && { [ "$mode" = local ] || mm_app_healthy_public; }; then
      if [ "$state" = "$last" ]; then
        streak=$((streak + 1))
      else
        streak=1
        last=$state
      fi
      if ((streak >= MM_HEALTH_STABLE_CHECKS)); then
        return 0
      fi
      sleep "$MM_HEALTH_STABLE_INTERVAL"
    else
      streak=0
      last=
      sleep "$MM_HEALTH_POLL_INTERVAL"
    fi
  done
  return 1
}

# mm_host_files_from_image <digest>: the image's /opt/mealmate/deploy, installed by the image's
# own setup.sh --update-host-files (PLT-07).
mm_host_files_from_image() {
  local tmp cid status=0
  tmp=$(mktemp -d "$MM_STATE/.hostfiles.XXXXXX")
  cid=$("$DOCKER" create "$MM_IMAGE@$1")
  "$DOCKER" cp "$cid:/opt/mealmate/deploy" "$tmp/deploy" >/dev/null || status=1
  "$DOCKER" rm -v "$cid" >/dev/null || true
  if [ "$status" -eq 0 ] && [ ! -f "$tmp/deploy/pi/setup.sh" ]; then
    mm_log "the image has no deploy/pi/setup.sh (older than milestone M8)"
    status=1
  fi
  if [ "$status" -eq 0 ]; then
    bash "$tmp/deploy/pi/setup.sh" --update-host-files --from "$tmp/deploy" || status=1
  fi
  rm -rf -- "$tmp"
  return "$status"
}

# --- Host files and systemd units (--update-host-files, step 8) -------------------------------

mm_units_in() {
  local unit
  for unit in "$1"/pi/systemd/*.service "$1"/pi/systemd/*.timer "$1"/pi/systemd/*.path; do
    if [ -f "$unit" ]; then
      printf '%s\n' "${unit##*/}"
    fi
  done
}

mm_install_host_files() {
  local src=$1 file name unit enable=()
  for file in compose.yml pi/setup.sh pi/bin/mm-compose common/prune.py; do
    [ -f "$src/$file" ] || mm_die "$src is not a deploy directory (missing $file)"
  done
  install -d -m 0755 -o 0 -g 0 "$MM_ROOT" "$MM_BIN"
  mm_install_file "$src/compose.yml" "$MM_ROOT/compose.yml" 0644
  mm_install_file "$src/pi/env.example" "$MM_ROOT/env.example" 0644
  mm_install_file "$src/pi/setup.sh" "$MM_BIN/setup.sh" 0755
  mm_install_file "$src/common/prune.py" "$MM_BIN/prune.py" 0755
  for file in "$src"/pi/bin/*; do
    mm_install_file "$file" "$MM_BIN/${file##*/}" 0755
  done

  install -d -m 0755 "$MM_SYSTEMD_DIR"
  while read -r unit; do
    if [ "$MM_ROOT" = /srv/mealmate ]; then
      mm_install_file "$src/pi/systemd/$unit" "$MM_SYSTEMD_DIR/$unit" 0644
    else
      sed "s|/srv/mealmate|$MM_ROOT|g" -- "$src/pi/systemd/$unit" |
        mm_write_file "$MM_SYSTEMD_DIR/$unit" 0644 0:0
    fi
    case $unit in
      *.timer | *.path) enable+=("$unit") ;;
    esac
  done < <(mm_units_in "$src")

  # Units a newer version no longer ships.
  for file in "$MM_SYSTEMD_DIR"/mealmate-*.service "$MM_SYSTEMD_DIR"/mealmate-*.timer \
    "$MM_SYSTEMD_DIR"/mealmate-*.path; do
    name=${file##*/}
    if [ -f "$file" ] && [ ! -f "$src/pi/systemd/$name" ]; then
      mm_log "removing the unit $name"
      "$SYSTEMCTL" disable --now "$name" >/dev/null 2>&1 || true
      rm -f -- "$file"
    fi
  done
  "$SYSTEMCTL" daemon-reload
  "$SYSTEMCTL" enable --now "${enable[@]}"
  mm_log "host files and ${#enable[@]} timers/path units installed from $src"
}

# --- Setup steps ------------------------------------------------------------------------------

mm_os_codename() {
  # shellcheck disable=SC1091
  (. /etc/os-release && printf '%s' "${VERSION_CODENAME:-}")
}

mm_arch() {
  dpkg --print-architecture
}

# Step 1: system update, packages, cosign, unattended-upgrades.
mm_step_packages() {
  export DEBIAN_FRONTEND=noninteractive
  mm_log "step 1: system update and packages"
  apt-get update
  apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold full-upgrade
  apt-get -y install unattended-upgrades rsync sqlite3 curl jq openssl ca-certificates gnupg \
    python3
  mm_install_cosign

  cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
  # Debian's 50unattended-upgrades already covers Debian security; lists add up across files.
  cat >/etc/apt/apt.conf.d/52mealmate-unattended-upgrades <<'EOF'
// MealMate (setup.sh, PLT-02, O-9): also the Raspberry Pi, Docker and Tailscale repositories,
// with an automatic reboot at night when an update needs one.
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
        "origin=Raspberry Pi Foundation,codename=${distro_codename},label=Raspberry Pi Foundation";
        "origin=Docker,label=Docker CE";
        "origin=Tailscale,label=Tailscale";
};
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:45";
EOF
}

mm_install_cosign() {
  local arch sha tmp
  arch=$(mm_arch)
  case $arch in
    arm64) sha=$MM_COSIGN_SHA256_ARM64 ;;
    amd64) sha=$MM_COSIGN_SHA256_AMD64 ;;
    *) mm_die "no pinned cosign for architecture $arch" ;;
  esac
  if [ -x "$COSIGN" ] && [ "$(mm_sha256 "$COSIGN")" = "$sha" ]; then
    return 0
  fi
  mm_log "installing cosign $MM_COSIGN_VERSION ($arch)"
  tmp=$(mktemp -d)
  "$CURL" -fsSL -o "$tmp/cosign" \
    "https://github.com/sigstore/cosign/releases/download/$MM_COSIGN_VERSION/cosign-linux-$arch"
  if [ "$(mm_sha256 "$tmp/cosign")" != "$sha" ]; then
    rm -rf -- "$tmp"
    mm_die "cosign download does not match the pinned SHA-256 $sha"
  fi
  install -m 0755 -o 0 -g 0 "$tmp/cosign" "$COSIGN"
  rm -rf -- "$tmp"
}

MM_REBOOT_MARKER=/var/lib/mealmate-setup/reboot-requested

# Asks for a reboot, unless this boot already follows the reboot setup.sh asked for: then the
# problem is reported and the setup goes on instead of asking again and again.
mm_needs_reboot() {
  if [ -f "$MM_REBOOT_MARKER" ] &&
    [ "$(cat "$MM_REBOOT_MARKER")" != "$(cat /proc/sys/kernel/random/boot_id)" ]; then
    mm_log "WARNING: $1 even after the reboot; continuing (see docs/operations.md, O-9)"
    return 0
  fi
  mm_log "$1 (needs a reboot)"
  MM_REBOOT=1
}

# Step 2: memory cgroup, zram swap, fewer SD card writes. Sets MM_REBOOT when a reboot is needed.
mm_step_system() {
  local cmdline=/boot/firmware/cmdline.txt codename changed
  mm_log "step 2: memory cgroup, zram, fewer SD card writes"
  [ -f "$cmdline" ] || cmdline=/boot/cmdline.txt
  if ! grep -qw cgroup_enable=memory "$cmdline"; then
    cp -n -- "$cmdline" "$cmdline.before-mealmate"
    sed -i '1 s/[[:space:]]*$/ cgroup_enable=memory/' "$cmdline"
    mm_log "added cgroup_enable=memory to $cmdline"
  fi
  if ! grep -qw cgroup_enable=memory /proc/cmdline; then
    mm_needs_reboot "the memory cgroup is not active"
  fi

  codename=$(mm_os_codename)
  if [ "$codename" = bookworm ]; then
    apt-get -y install zram-tools
    printf 'ALGO=zstd\nPERCENT=50\nPRIORITY=100\n' >/etc/default/zramswap
    "$SYSTEMCTL" restart zramswap || mm_needs_reboot "zramswap did not start"
  else
    # Trixie and later: rpi-swap, zram only (no swap file writeback).
    apt-get -y install rpi-swap || mm_log "WARNING: rpi-swap is not available on $codename"
    install -d -m 0755 /etc/rpi/swap.conf.d
    printf '# MealMate (setup.sh): compressed swap in RAM only, no file on the SD card.\n[Main]\nMechanism=zram\n' \
      >/etc/rpi/swap.conf.d/90-mealmate.conf
  fi
  if dpkg -s dphys-swapfile >/dev/null 2>&1; then
    dphys-swapfile swapoff || true
    apt-get -y purge dphys-swapfile
    rm -f /var/swap
  fi
  if swapon --show=TYPE,NAME --noheadings | grep -v zram | grep -q .; then
    mm_needs_reboot "swap outside zram is active"
  fi

  install -d -m 0755 /etc/systemd/journald.conf.d
  changed=$(printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=32M\n')
  if [ "$(cat /etc/systemd/journald.conf.d/90-mealmate.conf 2>/dev/null)" != "$changed" ]; then
    printf '%s\n' "$changed" >/etc/systemd/journald.conf.d/90-mealmate.conf
    "$SYSTEMCTL" restart systemd-journald
  fi

  awk 'BEGIN { OFS = "\t" }
       ($2 == "/" || $2 == "/boot/firmware") && $4 !~ /(^|,)noatime(,|$)/ { $4 = $4 ",noatime" }
       { print }' /etc/fstab | mm_write_file /etc/fstab 0644 0:0
  mount -o remount,noatime / || true

  install -d -m 0755 /etc/docker
  local daemon='{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}'
  if [ -f /etc/docker/daemon.json ]; then
    daemon=$(jq --argjson caps "$daemon" '. + $caps' /etc/docker/daemon.json)
  fi
  if [ "$(jq -S . /etc/docker/daemon.json 2>/dev/null)" != "$(printf '%s' "$daemon" | jq -S .)" ]; then
    printf '%s\n' "$daemon" | jq . | mm_write_file /etc/docker/daemon.json 0644 0:0
    if command -v dockerd >/dev/null; then
      "$SYSTEMCTL" restart docker
    fi
  fi
}

# Step 3: key-only SSH, no root login.
mm_step_ssh() {
  local user=${SUDO_USER:-} home
  mm_log "step 3: SSH hardening"
  if [ -n "$user" ] && [ "$user" != root ]; then
    home=$(getent passwd "$user" | cut -d: -f6)
    if [ ! -s "$home/.ssh/authorized_keys" ]; then
      mm_die "$user has no SSH key in $home/.ssh/authorized_keys; refusing to turn off password logins (set the key in Raspberry Pi Imager)"
    fi
  fi
  # sshd uses the first value it reads; 01- sorts before Imager's and cloud-init's files.
  cat >/etc/ssh/sshd_config.d/01-mealmate.conf <<'EOF'
# MealMate (setup.sh, PLT-02): keys only, no root login.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
  sshd -t
  "$SYSTEMCTL" reload ssh
}

# mm_key_has_fpr <key file> <fingerprint>: the file holds exactly one primary key, and it has
# this fingerprint (a subkey's fingerprint or a second key in the file does not count).
mm_key_has_fpr() {
  local primaries
  primaries=$(gpg --batch --show-keys --with-colons "$1" 2>/dev/null |
    awk -F: '$1 == "pub" { want = 1; next } $1 == "fpr" && want { print $10 } { want = 0 }') ||
    return 1
  [ "$primaries" = "$2" ]
}

# Step 4: Docker Engine and Tailscale from their apt repositories.
mm_step_install() {
  local codename arch tmp
  codename=$(mm_os_codename)
  arch=$(mm_arch)
  mm_log "step 4: Docker Engine and Tailscale ($codename, $arch)"
  tmp=$(mktemp -d)
  install -d -m 0755 /etc/apt/keyrings
  "$CURL" -fsSL -o "$tmp/docker.asc" https://download.docker.com/linux/debian/gpg
  mm_key_has_fpr "$tmp/docker.asc" "$MM_DOCKER_KEY_FPR" ||
    mm_die "the Docker repository key does not have the fingerprint $MM_DOCKER_KEY_FPR"
  install -m 0644 "$tmp/docker.asc" /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian %s stable\n' \
    "$arch" "$codename" >/etc/apt/sources.list.d/docker.list

  "$CURL" -fsSL -o "$tmp/tailscale.gpg" "https://pkgs.tailscale.com/stable/debian/$codename.noarmor.gpg"
  mm_key_has_fpr "$tmp/tailscale.gpg" "$MM_TAILSCALE_KEY_FPR" ||
    mm_die "the Tailscale repository key does not have the fingerprint $MM_TAILSCALE_KEY_FPR (compare with https://pkgs.tailscale.com/stable/ and pass TAILSCALE_KEY_FPR=... if Tailscale rotated it)"
  install -m 0644 "$tmp/tailscale.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
  printf 'deb [arch=%s signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian %s main\n' \
    "$arch" "$codename" >/etc/apt/sources.list.d/tailscale.list
  rm -rf -- "$tmp"

  apt-get update
  apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
    docker-compose-plugin tailscale
  "$SYSTEMCTL" enable --now docker tailscaled

  # O-9: the unattended-upgrades origins must match what these repositories publish.
  local policy origin
  policy=$(apt-cache policy)
  for origin in 'o=Docker,.*l=Docker CE' 'o=Tailscale' 'o=Raspberry Pi Foundation'; do
    if ! grep -qE "$origin" <<<"$policy"; then
      mm_log "WARNING: no apt source matches '$origin'; check /etc/apt/apt.conf.d/52mealmate-unattended-upgrades against 'apt-cache policy' (O-9)"
    fi
  done
}

mm_ts_backend_state() {
  "$TAILSCALE" status --json 2>/dev/null | jq -r '.BackendState // empty' || true
}

mm_public_url_from_tailscale() {
  local name
  name=$("$TAILSCALE" status --json | jq -r '.Self.DNSName // empty')
  name=${name%.}
  [ -n "$name" ] || mm_die "tailscale status has no DNS name (is MagicDNS on?)"
  printf 'https://%s' "$name"
}

# Step 5: Tailscale. On --restore the saved node state goes in before tailscaled ever logs in
# (O-1), and `tailscale up` never runs.
mm_step_tailscale() {
  local snapshot=${1:-} id marker=$MM_STATE/restored-tailscale i
  mm_log "step 5: Tailscale"
  if [ -n "$snapshot" ]; then
    id=$(jq -r .snapshot "$snapshot/manifest.json")
    if [ "$(cat "$marker" 2>/dev/null)" != "$id" ]; then
      [ -f "$snapshot/secrets/tailscaled.state" ] ||
        mm_die "the snapshot has no secrets/tailscaled.state"
      mm_log "swapping in the Tailscale node state of snapshot $id"
      "$SYSTEMCTL" stop tailscaled
      install -d -m 0700 -o 0 -g 0 "$MM_TS_STATE_DIR"
      install -m 0600 -o 0 -g 0 "$snapshot/secrets/tailscaled.state" \
        "$MM_TS_STATE_DIR/tailscaled.state"
      "$SYSTEMCTL" start tailscaled
      printf '%s\n' "$id" | mm_write_file "$marker" 0644 0:0
    fi
    for i in $(seq 1 30); do
      [ "$(mm_ts_backend_state)" = Running ] && break
      [ "$i" -lt 30 ] && sleep 2
    done
    if [ "$(mm_ts_backend_state)" != Running ]; then
      mm_die "Tailscale did not come up with the restored state; see 'Restore fallback' in docs/operations.md (never run 'tailscale up' while the old card could still come back)"
    fi
  elif [ "$(mm_ts_backend_state)" != Running ]; then
    mm_log "logging in to Tailscale as tag:mealmate; open the URL below and approve the Pi"
    "$TAILSCALE" up --advertise-tags=tag:mealmate
  fi
  if ! "$TAILSCALE" status --json | jq -e '(.Self.Tags // []) | index("tag:mealmate")' >/dev/null; then
    mm_log "WARNING: the Pi does not carry tag:mealmate (key expiry stays on); see docs/operations.md"
  fi
  "$TAILSCALE" set --auto-update
  "$TAILSCALE" serve --bg --https=443 http://127.0.0.1:8080
}

# Step 6: directories and the mmbackup user.
mm_step_dirs() {
  local home sub
  mm_log "step 6: directories and users"
  if [ "$MM_SKIP_SYSTEM" != 1 ] && ! id -u "$MM_BACKUP_USER" >/dev/null 2>&1; then
    # A real shell: sshd runs the forced rrsync command through it.
    useradd --system --user-group --create-home --home-dir "/home/$MM_BACKUP_USER" \
      --shell /bin/sh "$MM_BACKUP_USER"
  fi
  home=$(mm_backup_home)
  [ -n "$home" ] || mm_die "no home directory for $MM_BACKUP_USER"
  install -d -m 0700 -o "$MM_BACKUP_USER" -g "$MM_BACKUP_GROUP" "$home/.ssh"
  if [ ! -e "$home/.ssh/authorized_keys" ]; then
    install -m 0600 -o "$MM_BACKUP_USER" -g "$MM_BACKUP_GROUP" /dev/null "$home/.ssh/authorized_keys"
  fi

  install -d -m 0755 -o 0 -g 0 "$MM_ROOT" "$MM_BIN"
  [ ! -L "$MM_DATA" ] || mm_die "$MM_DATA is a symlink"
  if [ ! -d "$MM_DATA" ]; then
    install -d -m 0750 -o "$MM_APP_UID" -g "$MM_APP_UID" "$MM_DATA"
  fi
  chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_DATA"
  # Inside the container-writable data/: only create what is missing, never chown through.
  for sub in status media; do
    if [ ! -e "$MM_DATA/$sub" ] && [ ! -L "$MM_DATA/$sub" ]; then
      mkdir -m 0750 -- "$MM_DATA/$sub"
      chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_DATA/$sub"
    fi
  done
  install -d -m 0700 -o 0 -g 0 "$MM_STATE"
  install -d -m 0755 -o 0 -g 0 "$MM_STATE/status"
  install -d -m 0750 -o 0 -g "$MM_BACKUP_GROUP" "$MM_BACKUPS"
  if [ ! -e "$MM_OVERRIDE" ]; then
    install -m 0600 -o 0 -g 0 /dev/null "$MM_OVERRIDE"
  fi
}

mm_tag_for_version() {
  local v=${1#v}
  if [[ $v =~ ^[0-9]+\.[0-9]+(-pre)?$ ]]; then
    printf '%s' "$v"
  elif [[ $v =~ ^([0-9]+)\.([0-9]+)\.[0-9]+(-[0-9A-Za-z.]+)?$ ]]; then
    printf '%s.%s%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]:+-pre}"
  else
    mm_die "--version must look like 2.0.0, 2.0.0-alpha.1 or 2.0-pre, not '$1'"
  fi
}

# mm_ask_hc_url <var> <check>: the ping URL from the environment or a prompt (empty skips the
# check). An invalid URL is asked for again (three times) on a terminal, else it fails, so a
# caller never writes an empty value by mistake: `value=$(mm_ask_hc_url ...) || mm_die ...`.
mm_ask_hc_url() {
  local var=$1 value=${!1:-} tries=0 prompt="healthchecks.io ping URL for $2 (empty to skip): "
  if [ -z "$value" ] && [ -t 0 ]; then
    read -r -p "$prompt" value
  fi
  while [ -n "$value" ] && [[ ! $value =~ ^https?://[^[:space:]]+$ ]]; do
    tries=$((tries + 1))
    if [ ! -t 0 ] || [ "$tries" -gt 3 ]; then
      mm_log "ERROR: $var must be an http(s) URL, not '$value'"
      return 1
    fi
    mm_log "'$value' is not an http(s) URL; try again"
    read -r -p "$prompt" value
  done
  printf '%s' "$value"
}

MM_HC_CHECKS=(HC_HEARTBEAT_URL:heartbeat HC_BACKUP_URL:backup HC_UPDATE_URL:update HC_DISK_URL:disk)

# A new .env: random secret key, the Tailscale HTTPS address, the version line, HC_* URLs.
mm_write_new_env() {
  local tag=$1 key url check value hc=()
  key=$(openssl rand -hex 32)
  url=$(mm_public_url_from_tailscale)
  for check in "${MM_HC_CHECKS[@]}"; do
    value=$(mm_ask_hc_url "${check%%:*}" "${check#*:}") || mm_die "no valid ${check%%:*}; .env not written"
    hc+=("${check%%:*}=$value")
  done
  {
    printf '# Written by setup.sh on %s; see env.example. Mode 0600, root only (SEC-02).\n' "$(mm_now)"
    printf 'MEALMATE_SECRET_KEY=%s\n' "$key"
    printf 'MEALMATE_PUBLIC_URL=%s\n' "$url"
    printf 'IMAGE_TAG=%s\n' "$tag"
    printf '%s\n' "${hc[@]}"
  } | mm_write_file "$MM_ENV_FILE" 0600 0:0
  mm_log "wrote $MM_ENV_FILE (public URL $url, image tag $tag)"
}

# Step 7a: .env (kept on re-runs; missing keys are added).
mm_step_env() {
  local tag=$1 check current value
  if [ ! -f "$MM_ENV_FILE" ]; then
    [ -n "$tag" ] || mm_die "--version is required for a fresh install"
    mm_write_new_env "$tag"
    return 0
  fi
  chmod 0600 "$MM_ENV_FILE"
  chown -h 0:0 "$MM_ENV_FILE"
  current=$(mm_env_get IMAGE_TAG)
  if [ -z "$current" ]; then
    [ -n "$tag" ] || mm_die ".env has no IMAGE_TAG; pass --version"
    mm_env_set IMAGE_TAG "$tag"
  elif [ -n "$tag" ] && [ "$tag" != "$current" ]; then
    mm_log "note: .env follows IMAGE_TAG=$current, not $tag; switching the version line is a manual edit of .env followed by bin/update.sh"
  fi
  for check in "${MM_HC_CHECKS[@]}"; do
    if ! grep -qE "^${check%%:*}=" "$MM_ENV_FILE"; then
      value=$(mm_ask_hc_url "${check%%:*}" "${check#*:}") || mm_die "no valid ${check%%:*}"
      mm_env_set "${check%%:*}" "$value"
    fi
  done
}

# Step 7b: the image (steps 7-8). Which digest:
# - a restore: the snapshot's own image (verified, not recorded as bad), else the tag's;
# - a re-run: the installed version, i.e. the pin (or the running container's digest if the
#   pin was emptied). It is never moved forward here, that is update.sh's job; the image is
#   pulled again (verified) only if it is gone;
# - a fresh install: the verified digest the tag points to.
# Never a digest listed in state/bad-digest. Then pin it and install the host files from it.
mm_step_image() {
  local restore=${1:-0} preferred=${2:-} tag digest=
  tag=$(mm_env_get IMAGE_TAG)
  if [ "$restore" = 1 ]; then
    if [ -z "$preferred" ]; then
      mm_log "the snapshot names no image digest; using the tag $tag"
    elif mm_is_bad_digest "$preferred"; then
      mm_log "the snapshot's image $preferred is recorded as bad; using the tag $tag instead"
    elif mm_verify_provenance "$preferred"; then
      digest=$preferred
    else
      mm_log "the snapshot's image $preferred cannot be verified; using the tag $tag instead"
    fi
  elif digest=$(mm_current_digest) && [[ $digest =~ $MM_DIGEST_RE ]]; then
    if mm_is_bad_digest "$digest"; then
      mm_die "the installed digest $digest is listed in state/bad-digest; pin a good one first (docs/operations.md, section 10)"
    fi
    mm_log "step 7: keeping the installed version $MM_IMAGE@$digest (newer versions come with update.sh)"
    if ! "$DOCKER" image inspect "$MM_IMAGE@$digest" >/dev/null 2>&1; then
      mm_log "the installed image is no longer on this Pi; pulling it again"
      mm_verify_provenance "$digest" || mm_die "$MM_IMAGE@$digest cannot be verified (see above)"
      "$DOCKER" pull --quiet "$MM_IMAGE@$digest" >/dev/null || mm_die "pulling $MM_IMAGE@$digest failed"
    fi
    mm_pin "$digest"
    mm_log "step 8: host files and systemd units from the image"
    mm_host_files_from_image "$digest" || mm_die "installing the host files from the image failed"
    return 0
  else
    digest=
  fi
  if [ -z "$digest" ]; then
    digest=$(mm_resolve_digest "$tag") || mm_die "cannot resolve $MM_IMAGE:$tag"
    if mm_is_bad_digest "$digest"; then
      mm_die "$MM_IMAGE:$tag points to $digest, which is listed in state/bad-digest; wait for the next release (docs/operations.md, section 10)"
    fi
    mm_verify_provenance "$digest" ||
      mm_die "$MM_IMAGE@$digest has no valid build provenance, or cosign could not check it (see above)"
  fi
  mm_log "step 7: pulling $MM_IMAGE@$digest"
  "$DOCKER" pull --quiet "$MM_IMAGE@$digest" >/dev/null || mm_die "pulling $MM_IMAGE@$digest failed"
  mm_pin "$digest"
  mm_log "step 8: host files and systemd units from the image"
  mm_host_files_from_image "$digest" || mm_die "installing the host files from the image failed"
}

# jq and sqlite3 for the snapshot checks, which run before step 1 installs the packages (a
# freshly flashed card has neither).
mm_check_tools_work() {
  jq --version >/dev/null 2>&1 && "$SQLITE3" -version >/dev/null 2>&1
}

mm_ensure_check_tools() {
  if mm_check_tools_work; then
    return 0
  fi
  mm_log "installing jq and sqlite3 for the snapshot checks"
  { "$APT_GET" update && "$APT_GET" -y install jq sqlite3; } >&2 ||
    mm_die "could not install jq and sqlite3"
  mm_check_tools_work || mm_die "jq or sqlite3 still does not work after installing them"
}

# mm_check_snapshot <dir>: a complete, intact snapshot (checked before anything is changed).
mm_check_snapshot() {
  local dir=$1 id sha
  mm_is_plain_dir "$dir" || mm_die "$dir is not a directory"
  mm_is_plain_file "$dir/manifest.json" || mm_die "$dir has no manifest.json"
  id=$(jq -r '.snapshot // empty' "$dir/manifest.json") || mm_die "unreadable manifest.json"
  [[ $id =~ $MM_SNAPSHOT_RE ]] || mm_die "manifest.json has no valid snapshot id"
  mm_is_plain_file "$dir/db.sqlite3" || mm_die "$dir has no db.sqlite3"
  sha=$(jq -r '.db_sha256 // empty' "$dir/manifest.json")
  [ "$(mm_sha256 "$dir/db.sqlite3")" = "$sha" ] || mm_die "db.sqlite3 does not match its checksum"
  mm_check_db "$dir/db.sqlite3" >/dev/null || mm_die "db.sqlite3 fails the integrity check"
  mm_is_plain_file "$dir/secrets/env" || mm_die "$dir has no secrets/env"
  mm_log "snapshot $id is complete (version $(jq -r '.app_version // "?"' "$dir/manifest.json"))"
}

# Restore of SSH host keys, the backup key and .env (plan § 11.6 step 4.2).
mm_restore_secrets() {
  local dir=$1 key home
  mm_log "restoring the SSH host keys, the backup key and .env"
  for key in "$dir"/secrets/ssh/ssh_host_*; do
    [ -f "$key" ] || continue
    case $key in
      *.pub) install -m 0644 -o 0 -g 0 "$key" "$MM_SSH_DIR/${key##*/}" ;;
      *) install -m 0600 -o 0 -g 0 "$key" "$MM_SSH_DIR/${key##*/}" ;;
    esac
  done
  "$SYSTEMCTL" reload ssh || "$SYSTEMCTL" restart ssh || mm_log "WARNING: could not reload sshd"
  home=$(mm_backup_home)
  if [ -f "$dir/secrets/mmbackup_authorized_keys" ]; then
    mm_write_file "$home/.ssh/authorized_keys" 0600 "$MM_BACKUP_USER:$MM_BACKUP_GROUP" \
      "$home/.ssh" <"$dir/secrets/mmbackup_authorized_keys"
  fi
  mm_write_file "$MM_ENV_FILE" 0600 0:0 <"$dir/secrets/env"
}

# The database and the photos of a snapshot, owned by the app user (plan § 11.6 step 4.3).
mm_restore_data() {
  local dir=$1 id marker=$MM_STATE/restored-from ts aside staging name
  id=$(jq -r .snapshot "$dir/manifest.json")
  if [ "$(cat "$marker" 2>/dev/null)" = "$id" ]; then
    mm_log "the data of snapshot $id was restored before (delete $marker to restore it again)"
    return 0
  fi
  if [ -f "$MM_ROOT/compose.yml" ]; then
    mm_compose stop >/dev/null 2>&1 || true
  fi
  mm_is_plain_dir "$MM_DATA" || mm_die "$MM_DATA is not a directory"
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  aside=$MM_STATE/pre-restore-$ts
  mkdir -m 0700 -- "$aside"
  # Renames never follow symlinks; whatever is there moves aside as it is.
  for name in mealmate.db media; do
    if [ -e "$MM_DATA/$name" ] || [ -L "$MM_DATA/$name" ]; then
      mv -fT -- "$MM_DATA/$name" "$aside/$name"
    fi
  done
  rm -f -- "$MM_DATA/mealmate.db-wal" "$MM_DATA/mealmate.db-shm" "$MM_DATA/mealmate.db-journal"

  cp -- "$dir/db.sqlite3" "$MM_STATE/restore.tmp"
  mm_check_db "$MM_STATE/restore.tmp" >/dev/null || mm_die "the restored database fails the integrity check"
  chmod 0640 "$MM_STATE/restore.tmp"
  chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_STATE/restore.tmp"
  mv -fT -- "$MM_STATE/restore.tmp" "$MM_DATA/mealmate.db"

  staging=$(mktemp -d "$MM_STATE/.restore-media.XXXXXX")
  if [ -d "$dir/media" ]; then
    "$RSYNC" -rt --no-links --chmod=D0750,F0640 -- "$dir/media/" "$staging/"
  fi
  chmod 0750 "$staging"
  chown -R -h "$MM_APP_UID:$MM_APP_UID" "$staging"
  mv -fT -- "$staging" "$MM_DATA/media"
  if [ ! -e "$MM_DATA/status" ] && [ ! -L "$MM_DATA/status" ]; then
    mkdir -m 0750 -- "$MM_DATA/status"
    chown -h "$MM_APP_UID:$MM_APP_UID" "$MM_DATA/status"
  fi
  rmdir -- "$aside" 2>/dev/null || mm_log "the previous data is kept in $aside (delete it when the restore is confirmed)"
  printf '%s\n' "$id" | mm_write_file "$marker" 0644 0:0
  printf '%s\n' "$id" | mm_write_file "$MM_STATE/admin-created" 0644 0:0
  mm_log "restored the database and $(find "$MM_DATA/media" -type f | wc -l) media files of snapshot $id"
}

# Step 9: start, wait for health, first admin.
mm_step_start() {
  local restore=$1
  mm_log "step 9: starting the app"
  mm_compose up -d --remove-orphans
  mm_wait_healthy "$MM_HEALTH_TIMEOUT" local ||
    mm_die "the app did not become healthy; see: $MM_BIN/mm-compose logs app"
  if mm_wait_healthy 120; then
    mm_log "the app answers on $(mm_env_get MEALMATE_PUBLIC_URL)"
  else
    mm_log "WARNING: the app is healthy locally but not through $(mm_env_get MEALMATE_PUBLIC_URL) (tailscale serve, certificate, MagicDNS)"
  fi
  if [ -z "$restore" ] && [ ! -f "$MM_STATE/admin-created" ]; then
    if [ -t 0 ]; then
      mm_log "creating the first admin account"
      mm_compose exec app mealmate create-admin
      printf '%s\n' "$(mm_now)" | mm_write_file "$MM_STATE/admin-created" 0644 0:0
    else
      mm_log "no terminal: create the first admin later with: sudo $MM_BIN/mm-compose exec app mealmate create-admin"
    fi
  fi
}

mm_rotate_secret() {
  [ -f "$MM_ENV_FILE" ] || mm_die "no $MM_ENV_FILE"
  mm_lock deploy "$MM_LOCK_WAIT" || mm_die "update.sh or setup.sh is running (state/deploy.lock); try again later"
  mm_env_set MEALMATE_SECRET_KEY "$(openssl rand -hex 32)"
  mm_log "new secret key written; restarting the app (everyone has to log in again)"
  mm_compose up -d
  mm_wait_healthy "$MM_HEALTH_TIMEOUT" local || mm_die "the app did not become healthy"
  mm_log "done"
}

mm_set_backup_key() {
  local type=$1 key=$2 home rrsync
  [ "$type" = ssh-ed25519 ] || mm_die "the backup key must be an ssh-ed25519 key"
  [[ $key =~ ^[A-Za-z0-9+/]+={0,3}$ ]] || mm_die "that does not look like a public key"
  rrsync=$(command -v rrsync || true)
  [ -n "$rrsync" ] || mm_die "rrsync is missing (it comes with the rsync package)"
  home=$(mm_backup_home)
  [ -d "$home/.ssh" ] || mm_die "run setup.sh first (no $home/.ssh)"
  printf 'restrict,command="%s -ro %s" %s %s mealmate-backup-pull\n' "$rrsync" "$MM_BACKUPS" \
    "$type" "$key" |
    mm_write_file "$home/.ssh/authorized_keys" 0600 "$MM_BACKUP_USER:$MM_BACKUP_GROUP" "$home/.ssh"
  mm_log "installed the backup key for $MM_BACKUP_USER (read-only access to $MM_BACKUPS)"
}

mm_setup_usage() {
  sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'
}

mm_setup_main() {
  local mode=install version='' tag='' restore='' from='' key_type='' key_value='' preferred=''
  local image_restore=0
  while [ $# -gt 0 ]; do
    case $1 in
      --version) version=${2:?--version needs a value}; shift 2 ;;
      --restore) mode=restore; restore=${2:?--restore needs a directory}; shift 2 ;;
      --update-host-files) mode=update-host-files; shift ;;
      --from) from=${2:?--from needs a directory}; shift 2 ;;
      --rotate-secret) mode=rotate-secret; shift ;;
      --set-backup-key)
        mode=set-backup-key
        key_type=${2:?--set-backup-key needs <type> <key>}
        key_value=${3:?--set-backup-key needs <type> <key>}
        shift 3
        ;;
      --skip-system) MEALMATE_SKIP_SYSTEM=1; shift ;;
      -h | --help) mm_setup_usage; return 0 ;;
      *) mm_setup_usage >&2; mm_die "unknown argument: $1" ;;
    esac
  done
  mm_init setup
  [ "$(id -u)" -eq 0 ] || mm_die "run as root (sudo bash setup.sh ...)"

  case $mode in
    update-host-files)
      mm_install_host_files "${from:-$(cd "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
      return 0
      ;;
    rotate-secret) mm_rotate_secret; return 0 ;;
    set-backup-key) mm_set_backup_key "$key_type" "$key_value"; return 0 ;;
  esac

  if [ -n "$version" ]; then
    tag=$(mm_tag_for_version "$version")
  fi
  if [ -n "$restore" ]; then
    restore=$(cd "$restore" && pwd)
    mm_ensure_check_tools
    mm_check_snapshot "$restore"
    preferred=$(jq -r '.image_digest // empty' "$restore/manifest.json")
    [[ $preferred =~ $MM_DIGEST_RE ]] || preferred=
    # The first run deploys the snapshot's image; a re-run keeps what is installed by then.
    if [ "$(cat "$MM_STATE/restored-from" 2>/dev/null)" != "$(jq -r .snapshot "$restore/manifest.json")" ]; then
      image_restore=1
    fi
  fi

  install -d -m 0755 -o 0 -g 0 "$MM_ROOT"
  install -d -m 0700 -o 0 -g 0 "$MM_STATE"
  # Before anything touches the system, Tailscale, the directories, images or Compose.
  mm_lock deploy "$MM_LOCK_WAIT" || mm_die "update.sh or another setup.sh is running (state/deploy.lock)"

  MM_REBOOT=0
  if [ "$MM_SKIP_SYSTEM" != 1 ]; then
    mm_step_packages
    mm_step_system
    mm_step_ssh
    if [ "$MM_REBOOT" = 1 ]; then
      install -d -m 0755 "$(dirname "$MM_REBOOT_MARKER")"
      cat /proc/sys/kernel/random/boot_id >"$MM_REBOOT_MARKER"
      mm_log "A reboot is needed before the setup can continue (memory cgroup / swap)."
      mm_log "Run:  sudo reboot   and afterwards the same setup.sh command again."
      return 0
    fi
    rm -f -- "$MM_REBOOT_MARKER"
    mm_step_install
  fi
  mm_step_tailscale "$restore"
  mm_step_dirs
  if [ -n "$restore" ]; then
    mm_restore_secrets "$restore"
  fi
  mm_step_env "$tag"
  mm_step_image "$image_restore" "$preferred"
  if [ -n "$restore" ]; then
    mm_restore_data "$restore"
  fi
  mm_step_start "$restore"
  mm_log "setup finished; timers: $SYSTEMCTL list-timers 'mealmate-*'"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  mm_setup_main "$@"
fi
