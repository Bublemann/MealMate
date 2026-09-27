#!/bin/bash
# Installs the MealMate backup pull on the owner's Mac (OPS-03, OPS-10, plan § 11.3). Run it from
# the unpacked deploy bundle (or a checkout); re-running it is safe and updates everything:
#
#   bash mac/install-backup-pull.sh --pi <you>@mealmate.<tailnet>.ts.net [--hc-url <ping URL>]
#
# --pi is your own SSH login on the Pi (the Imager user). The script
#  1. installs Homebrew rsync (>= 3.5.1; macOS's openrsync is not used, O-5) and python3;
#  2. copies pull.sh and prune.py to ~/.mealmate-backup/bin/;
#  3. creates the key ~/.ssh/id_ed25519_mealmate_backup (no passphrase) and installs it for the
#     Pi's mmbackup user, restricted to read-only rrsync on /srv/mealmate/backups;
#  4. pins the Pi's SSH host key (read over your existing SSH access) in
#     ~/.mealmate-backup/known_hosts; it survives restores, the host keys are in the backup;
#  5. creates ~/MealMateBackups/ (outside iCloud Drive) and checks FileVault;
#  6. runs `tailscale set --shields-up`, so the Pi cannot connect to the Mac;
#  7. writes ~/.mealmate-backup/config and the launchd agent
#     ~/Library/LaunchAgents/de.mealmate.backup-pull.plist (hourly, RunAtLoad) and loads it.
# macOS ships bash 3.2, so this script avoids newer bash features.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
pi=
hc_url=
while [ $# -gt 0 ]; do
  case $1 in
    --pi) pi=${2:?--pi needs <user>@<host>}; shift 2 ;;
    --hc-url) hc_url=${2:?--hc-url needs a URL}; shift 2 ;;
    -h | --help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "this installer is for macOS"
case $pi in
  *@*) ;;
  *) die "pass your SSH login on the Pi: --pi <user>@mealmate.<tailnet>.ts.net" ;;
esac
host=${pi#*@}
prune_src=$here/../common/prune.py
for file in "$here/pull.sh" "$here/de.mealmate.backup-pull.plist" "$prune_src"; do
  [ -f "$file" ] || die "missing $file (run this from the deploy bundle)"
done

app_dir=$HOME/.mealmate-backup
dest=$HOME/MealMateBackups
key=$HOME/.ssh/id_ed25519_mealmate_backup
known_hosts=$app_dir/known_hosts
config=$app_dir/config
plist=$HOME/Library/LaunchAgents/de.mealmate.backup-pull.plist
label=de.mealmate.backup-pull
SSH=${SSH:-ssh}
LAUNCHCTL=${LAUNCHCTL:-launchctl}

# 1. Homebrew rsync and python3.
BREW=${BREW:-$(command -v brew || true)}
for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -z "$BREW" ] && [ -x "$candidate" ]; then
    BREW=$candidate
  fi
done
[ -n "$BREW" ] || die "Homebrew is needed first: https://brew.sh"
say "Homebrew rsync and python3"
"$BREW" install rsync python3
"$BREW" upgrade rsync python3 || true
prefix=$("$BREW" --prefix)
rsync=$prefix/bin/rsync
python=$prefix/bin/python3
"$rsync" --version | head -n 1

# 2. Scripts.
say "scripts in $app_dir/bin"
mkdir -p "$app_dir/bin"
chmod 0700 "$app_dir"
cp "$here/pull.sh" "$app_dir/bin/pull.sh"
cp "$prune_src" "$app_dir/bin/prune.py"
chmod 0755 "$app_dir/bin/pull.sh" "$app_dir/bin/prune.py"

# 3. The pull key.
mkdir -p "$HOME/.ssh"
chmod 0700 "$HOME/.ssh"
if [ ! -f "$key" ]; then
  say "creating $key"
  ssh-keygen -q -t ed25519 -N '' -C "mealmate-backup-pull@$(hostname -s)" -f "$key"
fi

# 4. Pin the host key, read over your own (already trusted) SSH connection.
say "pinning the SSH host key of $host"
hostkey=$("$SSH" "$pi" cat /etc/ssh/ssh_host_ed25519_key.pub) || die "cannot reach $pi over SSH"
read -r host_type host_key _ <<<"$hostkey" || true
[ "$host_type" = ssh-ed25519 ] && [ -n "$host_key" ] || die "unexpected host key: $hostkey"
echo "$host $host_type $host_key" >"$known_hosts"
chmod 0600 "$known_hosts"

say "installing the key for mmbackup on the Pi (sudo may ask for your password)"
read -r key_type key_value _ <"$key.pub"
"$SSH" -t "$pi" sudo /srv/mealmate/bin/setup.sh --set-backup-key "$key_type" "$key_value"

# 5. Backup folder outside iCloud Drive; FileVault.
mkdir -p "$dest"
chmod 0700 "$dest"
if command -v fdesetup >/dev/null && ! fdesetup status | grep -q 'FileVault is On'; then
  echo "WARNING: FileVault is off. The backups contain credentials (OPS-10): turn it on in System Settings > Privacy & Security." >&2
fi

# 6. Shields up: the tailnet cannot open connections to this Mac.
TAILSCALE=${TAILSCALE:-$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)}
if "$TAILSCALE" set --shields-up; then
  say "Tailscale shields-up is on"
else
  echo "WARNING: could not run '$TAILSCALE set --shields-up'; turn off 'Allow incoming connections' in the Tailscale menu instead." >&2
fi

# 7. Configuration and the launchd agent.
if [ -z "$hc_url" ] && [ -f "$config" ]; then
  hc_url=$(sed -n 's/^HC_MACPULL_URL=//p' "$config" | tr -d "'\"")
fi
if [ -z "$hc_url" ] && [ -t 0 ]; then
  printf 'healthchecks.io ping URL for mac-pull (empty to skip): '
  read -r hc_url
fi
{
  echo "# MealMate backup pull, written by install-backup-pull.sh."
  printf 'MM_REMOTE=%q\n' "mmbackup@$host:"
  printf 'MM_DEST=%q\n' "$dest"
  printf 'MM_RSYNC=%q\n' "$rsync"
  printf 'MM_PYTHON=%q\n' "$python"
  printf 'MM_SSH_KEY=%q\n' "$key"
  printf 'MM_KNOWN_HOSTS=%q\n' "$known_hosts"
  printf 'HC_MACPULL_URL=%q\n' "$hc_url"
} >"$config"
chmod 0600 "$config"

mkdir -p "$(dirname "$plist")"
sed "s|__HOME__|$HOME|g" "$here/de.mealmate.backup-pull.plist" >"$plist"
plutil -lint "$plist" >/dev/null
"$LAUNCHCTL" bootout "gui/$(id -u)/$label" 2>/dev/null || true
"$LAUNCHCTL" bootstrap "gui/$(id -u)" "$plist"
say "installed; the first pull runs now. Log: $app_dir/pull.log, backups: $dest/snapshots"
