# MealMate operations runbook

| | |
|---|---|
| For | The owner, who runs MealMate on a Raspberry Pi 3 and pulls backups to a Mac |
| Covers | First setup, Tailscale, alerts, the Mac backup pull, backups, restore / SD card swap, updates and rollback, secret rotation, troubleshooting |
| Background | [`plan.md`](plan.md) §§ 11 and 13; requirements OPS, PLT, SEC-09/11/12 in [`requirements.md`](requirements.md) |

Everything on the Pi is done by scripts; this runbook says when to run which one and what to check. Commands that start with `sudo` run on the Pi (over SSH), commands without it on the Mac unless stated otherwise.

**Quick reference (on the Pi):**

| Task | Command |
|---|---|
| App status / logs | `sudo /srv/mealmate/bin/mm-compose ps` · `sudo /srv/mealmate/bin/mm-compose logs --tail 100 app` |
| Timers and their last runs | `systemctl list-timers 'mealmate-*'` |
| Log of a host script | `journalctl -u mealmate-backup -u mealmate-update --since today` |
| Manual backup | `sudo /srv/mealmate/bin/backup.sh --label manual` (or "Back up now" on the admin page) |
| Update now | `sudo /srv/mealmate/bin/update.sh` |
| New secret key | `sudo /srv/mealmate/bin/setup.sh --rotate-secret` |
| Password reset link (e.g. for the last admin) | `sudo /srv/mealmate/bin/mm-compose exec app mealmate reset-link <username>` |

---

## 1. How it fits together

- The app is **one container** (`app`) started by Docker Compose from `/srv/mealmate/compose.yml`, on the host network, listening on `127.0.0.1:8080` only.
- `tailscale serve` terminates HTTPS for `https://mealmate.<tailnet>.ts.net` and forwards to it. That address is the only one.
- systemd timers run the host scripts in `/srv/mealmate/bin/`: backups, the nightly update, the heartbeat and disk checks, and the app's own background jobs.
- The Mac pulls finished backups every hour over SSH with a read-only key.
- healthchecks.io emails you when a check fails or goes silent.

### 1.1 Layout on the Pi

```
/srv/mealmate/
├── compose.yml         # from the running image (never edit; updates replace it)
├── env.example         # documentation of .env
├── .env                # 0600 root: MEALMATE_SECRET_KEY, MEALMATE_PUBLIC_URL, IMAGE_TAG, HC_* URLs
├── data/               # the container's volume (uid 10001): mealmate.db, media/, pre-migrate/,
│                       # status/backup-request (written by the admin page)
├── media-mirror/       # uid 10001, 0700: the photos as the app user reads them (backup.sh, SEC-09)
├── backups/            # finished snapshots <UTC time>/ (readable by mmbackup); .partial-* while writing
├── state/              # host only (0700): override.env (IMAGE_REF pin), previous-digest, bad-digest,
│                       # update-in-progress (while an update runs), deploy.lock, backup.lock,
│                       # markers of setup/restore; status/ (backup.json, disk.json; the app reads
│                       # it read-only at /status)
└── bin/                # setup.sh, mm-compose, backup.sh, update.sh, heartbeat.sh, disk-check.sh, prune.py
```

`bin/`, `compose.yml` and the systemd units (`/etc/systemd/system/mealmate-*`) come from the running image: every successful update installs the matching version (PLT-07). Don't edit them in place; changes belong in the repository.

**Symlink safety (SEC-09).** The scripts run as root and never write to an existing path in `data/`, which the container can write. They write a temp file in `state/`, `chown -h` it and `mv -fT` it into place (a rename replaces a planted symlink instead of following it), move the container's backup copy out of `data/` before checking it (it must then be one regular file, not a symlink or hard link), and remove the backup request file with `rm -f`. The photos in `data/media` are read with the app user's rights only (`setpriv` to uid 10001, no groups) into `media-mirror/`, so a directory swapped for a symlink while rsync walks it can never expose more than the container can read anyway; root then snapshots the mirror, which only that rsync writes. The mirror costs one extra copy of the photos on the SD card.

**One deploy lock.** `update.sh`, `setup.sh` (before it touches the system, Tailscale, directories, images or Compose) and `setup.sh --rotate-secret` all take `state/deploy.lock`, so they never run at the same time; the heartbeat stays silent while it is held.

### 1.2 Timers

| Unit | When | Runs | Pings |
|---|---|---|---|
| `mealmate-backup.timer` | 00:15, 06:15, 12:15, 18:15 | `backup.sh` | `backup` |
| `mealmate-backup.path` | when `data/status/backup-request` exists | `mealmate-backup-manual.service` → `backup.sh --label manual` | `backup` |
| `mealmate-update.timer` | 04:30 | `update.sh` | `update` |
| `mealmate-heartbeat.timer` | every 5 min (first 3 min after boot) | `heartbeat.sh` | `heartbeat` |
| `mealmate-disk.timer` | hourly | `disk-check.sh` | `disk` |
| `mealmate-off-refresh.timer` | 03:00 | `mm-compose exec -T app mealmate jobs off-refresh` (skipped while the running version has no such job) | – |
| `mealmate-cleanup.timer` | 03:30 | `mm-compose exec -T app mealmate jobs cleanup` | – |
| `mealmate-restore-test.timer` | the 1st of each month, 05:15 | `backup.sh --verify-latest` | `backup` |

That is seven timers plus one path unit: `systemctl list-timers 'mealmate-*'` shows the timers, `systemctl list-units 'mealmate-*.path'` the path unit.

Unattended upgrades reboot the Pi at **03:45** when a package needs it; the update runs after that.

---

## 2. Before the first setup (owner checklist, plan § 13)

1. **Tailscale:** create the account; in the admin console enable **MagicDNS** and **HTTPS certificates**. Your tailnet name becomes public in certificate transparency logs, which is harmless.
2. **Tailscale policy** (Access controls): add the tag owner and replace the default allow-all with grants like these (adapt the owner groups; O-2 is checked in M1):

   ```json
   {
     "tagOwners": { "tag:mealmate": ["autogroup:admin"] },
     "grants": [
       { "src": ["autogroup:member"], "dst": ["autogroup:member"], "ip": ["*"] },
       { "src": ["autogroup:member"], "dst": ["tag:mealmate"], "ip": ["tcp:22", "tcp:443"] },
       { "src": ["autogroup:shared"], "dst": ["tag:mealmate"], "ip": ["tcp:443"] }
     ]
   }
   ```

   Nothing has `tag:mealmate` as its source, so the Pi cannot reach any other device. Shared users reach only HTTPS on the Pi. If shared users cannot connect, upstream reports suggest granting the Pi's tailnet IP (`100.x.y.z/32`) instead of the tag for `autogroup:shared`.
3. **healthchecks.io:** create an account with the email integration (ntfy optional) and the checks from § 5. At least `heartbeat` and `disk` before the first setup.
4. **Raspberry Pi Imager:** Raspberry Pi OS Lite **64-bit** onto the SD card (16 GB or more), with the OS customisation:
   - hostname `mealmate`;
   - your user name and a password (only used for `sudo` if your user needs one);
   - SSH enabled, **public-key authentication only**, with the public key of `~/.ssh/id_ed25519_mealmate` from your Mac;
   - locale and time zone (Europe/Berlin).
5. **Tailscale apt key:** check its fingerprint once, as described in § 13.5 item 1 (`setup.sh` pins it, but it could not be verified independently when the script was written).
6. Wire the Pi to your router with Ethernet and the official 2.5 A power supply, boot it and log in: `ssh -i ~/.ssh/id_ed25519_mealmate <you>@mealmate.local` (the `.local` name works on the home network before Tailscale runs).

---

## 3. First setup of the Pi

1. Pick the release to install on its [releases page](https://github.com/Bublemann/MealMate/releases), e.g. `2.0.0-alpha.1` (pre-releases follow `2.0-pre`, releases `2.0`).
2. On the Pi, download `setup.sh` and check it against the checksum in the **release notes** (the notes are shown by GitHub; the `setup.sh.sha256` asset lets `sha256sum -c` do the comparison):

   ```bash
   VER=2.0.0-alpha.1
   curl -fsSLO "https://github.com/Bublemann/MealMate/releases/download/v$VER/setup.sh"
   curl -fsSLO "https://github.com/Bublemann/MealMate/releases/download/v$VER/setup.sh.sha256"
   sha256sum -c setup.sh.sha256   # "setup.sh: OK"; also compare the hash with the release notes
   sudo bash setup.sh --version "$VER"
   ```

3. The script works in numbered steps and logs each one (`step 1: …`). What they do:
   1. **System update and packages:** `apt full-upgrade`; `unattended-upgrades`, `rsync`, `sqlite3`, `curl`, `jq`, `gnupg`, `python3`; **cosign** v3.1.3 as a release binary whose SHA-256 is pinned in the script. Unattended upgrades cover Debian security, Raspberry Pi, Docker and Tailscale packages with an automatic reboot at 03:45 (`/etc/apt/apt.conf.d/52mealmate-unattended-upgrades`).
   2. **System settings:** `cgroup_enable=memory` in `/boot/firmware/cmdline.txt` (the original is kept as `cmdline.txt.before-mealmate`); swap only as compressed RAM (zram: `rpi-swap` with `Mechanism=zram` on Trixie, `zram-tools` on Bookworm, `dphys-swapfile` removed); journald in RAM; `noatime`; Docker log caps (10 MB × 3).
   3. **SSH:** `/etc/ssh/sshd_config.d/01-mealmate.conf`: keys only, no root login. The script refuses if your user has no `authorized_keys`, so you cannot lock yourself out.

      **Reboot:** the first run changes the kernel command line and swap, so it stops here and prints *"A reboot is needed …"*. Run `sudo reboot`, log in again and run **the same command** again. The re-run checks that the memory cgroup and zram are active and continues.
   4. **Docker Engine and Tailscale** from their apt repositories (arm64, keys in `signed-by` keyrings). Each downloaded key file must hold exactly one primary key with the fingerprint pinned in `setup.sh` (Docker `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`, Tailscale `2596 A99E AAB3 3821 893C 0A79 458C A832 957F 5868`), else the script stops. **Check the Tailscale fingerprint yourself on the first install** (it could not be verified when the script was written): see § 13.5. If Tailscale ever rotates its key, compare the new one the same way and pass `TAILSCALE_KEY_FPR=<new fingerprint>`. The script warns if the unattended-upgrades origins don't match what `apt-cache policy` shows (O-9).
   5. **Tailscale login:** `tailscale up --advertise-tags=tag:mealmate` prints a login URL. Open it, log in and approve the Pi. The tag turns off key expiry and makes the Pi a server, not your device. Then `tailscale set --auto-update` and `tailscale serve --bg --https=443 http://127.0.0.1:8080`.
   6. **Directories and users:** `/srv/mealmate` as in § 1.1, and the user `mmbackup` with an empty `authorized_keys` (the Mac installer fills it).
   7. **`.env` and the image:** `.env` gets a random `MEALMATE_SECRET_KEY` (`openssl rand`), `MEALMATE_PUBLIC_URL` from `tailscale status`, `IMAGE_TAG` from `--version` (`2.0.0-alpha.1` → `2.0-pre`, `2.0.0` → `2.0`) and the four healthchecks.io ping URLs, which it asks for (empty skips a check; a typo that is not an `http(s)://` URL is asked for again; you can add them to `.env` later). Then it resolves the tag to a digest, **verifies its signed build provenance** with cosign (the same function `update.sh` uses), pulls it by digest and **pins** it in `state/override.env`, so what runs is exactly what was verified. A digest listed in `state/bad-digest` is never installed.
   8. **Host files and units** from that image: compose file, `bin/`, the systemd units; the timers are enabled.
   9. **Start:** `mm-compose up -d`, waits for the health check locally and through `https://mealmate.<tailnet>.ts.net`, then asks for the **first admin** (`mealmate create-admin`: username, display name, password).
4. Check the result:
   - in the Tailscale console the Pi shows `tag:mealmate` and "Expiry disabled";
   - `systemctl list-timers 'mealmate-*'` lists the seven timers, and `systemctl list-units 'mealmate-*.path'` shows `mealmate-backup.path` active;
   - open `https://mealmate.<tailnet>.ts.net` on your iPhone and log in as the admin;
   - the healthchecks.io checks turn green within minutes (`heartbeat`, `disk`; `backup` after 00:15/06:15/12:15/18:15).
5. Share the Pi with each household member from the Tailscale console (Share…), then create their invites on the admin page.

Re-running `setup.sh` (`sudo /srv/mealmate/bin/setup.sh`, or the bootstrap command) is always safe: it skips what is done, keeps `.env` (adding missing keys) and the data, and **keeps the installed version**: the digest pinned in `state/override.env` (or, if the pin was emptied, the digest of the running container, which it pins again). If that image is no longer on the Pi, it is verified and pulled again by digest. The host files and units are reinstalled from it. A re-run never moves to a newer digest of the tag, that is `update.sh`'s job, and stops if the installed digest is listed in `state/bad-digest`. Only when nothing is installed (or Docker cannot tell the running image's digest) does it resolve `IMAGE_TAG` like a fresh install.

---

## 4. Tailscale sharing and access

- The Pi is **shared** with each user (node sharing), so users only see the Pi; they don't use seats in your tailnet.
- Users install the Tailscale app and leave it on (VPN On Demand).
- The invite on the admin page can carry the Tailscale share link (two-step share).
- To remove someone: revoke the share in the Tailscale console and deactivate the user on the admin page.

---

## 5. healthchecks.io

| Check | Period | Grace | Pinged by | URL in |
|---|---|---|---|---|
| `heartbeat` | 5 min | 10 min | Pi, `heartbeat.sh` | Pi `.env` `HC_HEARTBEAT_URL` |
| `backup` | 6 h | 2 h | Pi, `backup.sh` (every backup and the monthly test restore) | Pi `.env` `HC_BACKUP_URL` |
| `mac-pull` | 1 day | 2 days | Mac, `pull.sh` | Mac `~/.mealmate-backup/config` `HC_MACPULL_URL` |
| `update` | 1 day | 1 day | Pi, `update.sh` (every nightly run) | Pi `.env` `HC_UPDATE_URL` |
| `disk` | 1 h | 1 h | Pi, `disk-check.sh` (fails below 20 % free) | Pi `.env` `HC_DISK_URL` |
| `image-scan` | 7 days | 2 days | GitHub Actions, `image-scan.yml` | Actions secret `HC_SCAN_URL` |

- A failure pings the check's `/fail` URL with the script's own last log lines (never app logs), so the alert email says what went wrong.
- The heartbeat retries a failure twice (15 s apart) and stays silent while `state/deploy.lock` is held (`update.sh`, `setup.sh`, `--rotate-secret`); the grace period covers the few minutes of an update.
- To change a URL on the Pi: `sudo nano /srv/mealmate/.env` (no restart needed; the URLs never reach the container).

---

## 6. The Mac backup pull

**Requirements:** the Mac is in your tailnet, FileVault is on, [Homebrew](https://brew.sh) is installed, and you can `ssh <you>@mealmate.<tailnet>.ts.net`. A Time Machine disk that gets these backups must be encrypted (OPS-10).

1. Download the deploy bundle `mealmate-deploy-<ver>.tar.gz` of the installed release and check it against the release notes, or use a checkout of the repository:

   ```bash
   shasum -a 256 mealmate-deploy-2.0.0-alpha.1.tar.gz   # compare with the release notes
   tar xzf mealmate-deploy-2.0.0-alpha.1.tar.gz && cd mealmate-deploy-2.0.0-alpha.1
   bash mac/install-backup-pull.sh --pi <you>@mealmate.<tailnet>.ts.net --hc-url https://hc-ping.com/<uuid>
   ```

2. What the installer changes (re-running it is safe and updates everything):
   - `brew install rsync python3` (Homebrew rsync ≥ 3.5.1; macOS's own openrsync is not used, O-5);
   - `~/.mealmate-backup/`: `bin/pull.sh`, `bin/prune.py`, `config`, `known_hosts`, `pull.log`;
   - the key `~/.ssh/id_ed25519_mealmate_backup` (no passphrase), installed on the Pi through your own SSH login with `setup.sh --set-backup-key`, as `restrict,command="rrsync -ro /srv/mealmate/backups"` for `mmbackup`;
   - the Pi's SSH host key, read over your existing SSH connection and pinned in `~/.mealmate-backup/known_hosts` (it survives restores because the host keys are in the backup);
   - `~/MealMateBackups/` (outside iCloud Drive; don't move it into Desktop or Documents if those sync to iCloud);
   - `tailscale set --shields-up` on the Mac: no tailnet device, the Pi included, can open connections to the Mac;
   - the launchd agent `~/Library/LaunchAgents/de.mealmate.backup-pull.plist` (hourly, at login, and after sleep), loaded right away.
3. Check: `tail ~/.mealmate-backup/pull.log` shows `pulled <id> as <time>` lines, and the `mac-pull` check turns green.

**What `pull.sh` does** every hour:

1. Lists the Pi's snapshots. `.partial-*` and every name that isn't `YYYYMMDDTHHMMSSZ` are ignored (the names come from the Pi, which could be compromised).
2. Fetches each snapshot **not yet in the ledger** `~/MealMateBackups/pulled.txt` into `.staging/` (no symlinks, files over 50 MB skipped, unchanged photos hard-linked to the newest local snapshot), checks the database checksum in the manifest, and moves it to `~/MealMateBackups/snapshots/<Mac receive time>/`. A snapshot the Pi changes later is never fetched again, so nothing on the Mac is overwritten. A snapshot that fails its checksum is recorded as `rejected` and alerts once.
3. **Abnormal pull guard:** more new snapshots than `8 + 5 × days since the last successful pull`, or more than 2 GB → it stops, prunes nothing and pings `/fail`. The first pull into an empty ledger (a new Mac) is exempt.
4. Retention by receive time (§ 7.2); nothing younger than 7 days is deleted.
5. Pings `mac-pull`.

**After an "abnormal pull" alert:** check on the Pi what happened (`ls /srv/mealmate/backups`, `journalctl -u mealmate-backup`). Many snapshots after a long Mac holiday or a burst of manual backups are fine; unexpected ones mean the Pi may be compromised: then don't accept, follow § 11. To accept the batch once:

```bash
~/.mealmate-backup/bin/pull.sh --accept-abnormal
```

**Run a pull by hand** (e.g. before an SD card swap): `~/.mealmate-backup/bin/pull.sh`.
**Uninstall:** `launchctl bootout gui/$(id -u)/de.mealmate.backup-pull`, delete the plist, `~/.mealmate-backup` and (if wanted) `~/MealMateBackups`, and empty `/home/mmbackup/.ssh/authorized_keys` on the Pi.

---

## 7. Backups

### 7.1 What a snapshot contains

`/srv/mealmate/backups/<UTC time>/`, written as `.partial-<time>/` and renamed only when complete (OPS-01):

| Path | What |
|---|---|
| `db.sqlite3` | consistent copy via SQLite's backup API, integrity-checked in the container and again on the host |
| `media/` | the photos (read as the app user through `media-mirror/`); unchanged ones are hard links into the previous snapshot |
| `secrets/env` | `.env` (secret key, public URL, image tag, ping URLs) |
| `secrets/tailscaled.state` | the Pi's Tailscale identity |
| `secrets/ssh/ssh_host_*` | the SSH host keys |
| `secrets/mmbackup_authorized_keys` | the Mac's backup key |
| `manifest.json` | `snapshot`, `created_at`, `label` (`regular`/`pre-update`/`manual`), `app_version`, `app_commit`, `image_digest`, `alembic_revision`, `db_sha256`, `media_files`, `files` (SHA-256 of each secret) |

**Snapshots contain credentials** (OPS-10). Everything is `root:mmbackup`, files `0640`.

### 7.2 Retention (OPS-02)

`prune.py` runs after every backup on the Pi and after every pull on the Mac:

- **regular** snapshots: the newest per day for the 7 most recent days that have one, the newest per week for 4 weeks and the newest per month for 6 months (about 17). A gap in the backups never shrinks this history.
- **pre-update** and **manual** snapshots: kept for 7 days (on the Pi; the Mac ignores labels, which come from the Pi, and treats every snapshot as regular).
- **Never deleted:** the newest snapshot and anything younger than 7 days. On the Pi this keeps all ~28 backups of the last week in addition, which costs little: each is one database copy, photos are hard links.
- Days, weeks and months are local time on the machine running it: each snapshot's own local date, with the daylight saving time of that date.

Dry run: `sudo python3 /srv/mealmate/bin/prune.py --dry-run /srv/mealmate/backups`.

### 7.3 Manual backup (OPS-08)

Before planned maintenance:

- admin page → System → **Back up now** (creates `data/status/backup-request`; `mealmate-backup.path` starts the backup within seconds), or
- `sudo /srv/mealmate/bin/backup.sh --label manual`.

The result is shown on the admin page (from `state/status/backup.json`) and pinged to `backup`.

### 7.4 Monthly test restore (OPS-07)

`backup.sh --verify-latest` checks the newest snapshot read-only on the host: `PRAGMA integrity_check` via `file:…?mode=ro&immutable=1`, the database checksum and the secrets' checksums against the manifest. The result pings `backup`. Run it by hand the same way. The full restore is rehearsed on a spare card (§ 8).

---

## 8. Restore and SD card swap

> **Never run the old and the new card at the same time** (OPS-09). Both would claim the same Tailscale identity. Keep the old card out of every Pi once the new one has been set up.

### 8.1 Planned swap (or the restore drill on a spare card)

1. Start a backup and wait for it: admin page → **Back up now**, or `sudo /srv/mealmate/bin/backup.sh --label manual`.
2. Pull it to the Mac: `~/.mealmate-backup/bin/pull.sh`, and check `tail ~/.mealmate-backup/pull.log`.
3. Shut the Pi down: `sudo poweroff`. Take the old card out and put it away labelled.
4. Flash the new card with Imager exactly as in § 2 step 4 (same hostname, user and SSH key).
5. Boot the Pi with the new card and copy the snapshot from the Mac (the new card has new host keys, so SSH asks you to accept once; use the `.local` name on the home network):

   ```bash
   ls ~/MealMateBackups/snapshots/                       # newest = last; the manifest has the Pi's id
   cat ~/MealMateBackups/snapshots/<time>/manifest.json   # note app_version
   scp -r ~/MealMateBackups/snapshots/<time> <you>@mealmate.local:snapshot
   ```

6. On the Pi, bootstrap `setup.sh` of the **manifest's version** (§ 3 step 2) and restore:

   ```bash
   sudo bash setup.sh --version <app_version> --restore ~/snapshot
   ```

   The script first installs `jq` and `sqlite3` if the fresh card lacks them and checks the snapshot (manifest, checksum, integrity). After the reboot stop (run the same command again), it:
   1. stops `tailscaled`, copies the saved `tailscaled.state` into `/var/lib/tailscale/`, starts it: the Pi comes back as the **same node** with the same address, name, shares and certificate (O-1). `tailscale up` is never run;
   2. restores the SSH host keys (your Mac's `known_hosts` matches again), the `mmbackup` key and `.env`;
   3. deploys the snapshot's exact image digest (verified and not listed in `state/bad-digest`; else the verified digest of `IMAGE_TAG`);
   4. removes stale `-wal`/`-shm`/`-journal` files, restores `db.sqlite3` (integrity-checked) and `media/`, owned by uid 10001; anything that was in `data/` before is moved to `state/pre-restore-<time>/`;
   5. starts the app and waits for health.

   Running it again does not restore the data a second time (`state/restored-from`) and keeps the version that is installed by then (like any re-run, § 3).
7. Verify: the Tailscale console shows one `mealmate` machine (online, tagged); open the app on an iPhone: data and photos are there, and unsent offline ticks sync by themselves because the address is unchanged; `systemctl list-timers 'mealmate-*'`; the checks stay green; the Mac's next pull works without a host key warning.

**Fallback if the Tailscale state does not come back** (the script stops with an error): make sure the old card is not running, then log in as a new machine and restore the name and shares:

```bash
sudo tailscale up --advertise-tags=tag:mealmate --force-reauth
```

In the Tailscale console: delete the old `mealmate` machine, rename the new one to `mealmate`, and share it again with every user (they accept the new share once). Then `sudo bash setup.sh --version <ver> --restore ~/snapshot` again to finish.

### 8.2 Disaster (the Pi or its card died)

Same as § 8.1 from step 4, with the newest snapshot on the Mac. Changes since that snapshot are lost (at most about 6 hours, plus up to an hour until the Mac pulls).

---

## 9. Updates

- **Nightly (04:30), automatic:** `update.sh` checks the tag in `IMAGE_TAG`. Patch releases of your version line (e.g. `2.0.1`, `2.0.2` on `2.0`, every pre-release on `2.0-pre`) are installed after their provenance is verified.
- **Now:** `sudo /srv/mealmate/bin/update.sh` (does nothing if already up to date).
- **What it does** (plan § 11.5):
  0. takes `state/deploy.lock` (if `setup.sh` or another update holds it, it logs that and stops). If `state/update-in-progress` exists, an earlier run was cut short (power loss, crash, killed): it finishes or rolls back that update (see "Interrupted update" in § 10) and does nothing else in this run;
  1. resolves the digest of `ghcr.io/bublemann/mealmate:$IMAGE_TAG`; stops if it is the running one or one listed in `state/bad-digest`;
  2. verifies its signed build provenance: `cosign verify-attestation --type slsaprovenance1` with the GitHub Actions OIDC issuer and the identity `…/Bublemann/MealMate/.github/workflows/build-image.yml@refs/tags/v…`, up to 3 attempts (30 s, then 60 s apart). cosign's last error lines go into the log and the alert. Nothing is pulled or run unless it passes. Then:
     - **verification failure** (cosign proved the provenance invalid: an attestation of the wrong identity, issuer or type, invalid signature): the digest is added to `state/bad-digest`, `/fail`;
     - **not signed yet** (no attestation at all: *"no build provenance yet (a release may still be signing)"*): not installed, `/fail` only, not retried in this run; nothing is recorded, the next night tries again. `build-image.yml` adds the moving tags only after the attestation, so this means a release whose signing failed (or an image that was never signed);
     - **could not check** (network, registry, Sigstore TUF or Rekor trouble, anything else): `/fail` only; nothing is recorded, the next night tries again;
  3. **pre-update health gate:** checks the current version (locally and through the HTTPS address, stable as in step 5). If it is not healthy: `/fail` *"current version unhealthy, update skipped"*, nothing is changed (a rollback would have no healthy target). Then it pulls the new image by digest, writes the running digest to `state/previous-digest` and runs `backup.sh --label pre-update`;
  4. writes `state/update-in-progress` (new digest, previous digest, pre-update snapshot), pins `IMAGE_REF=…@<digest>` in `state/override.env` and runs `mm-compose up -d`; the entrypoint snapshots the database to `data/pre-migrate/` and runs the migrations;
  5. waits up to 180 s for **stable** health: 3 good checks in a row, 10 s apart, locally and through the HTTPS address, all in the same container without a restart in between (a version that answers once and then crashes does not count);
  6. healthy: removes `state/update-in-progress`, installs the new version's host files and units (`setup.sh --update-host-files` from the image), removes mealmate images other than the current and previous digest (`docker image rm`), pings `update`;
  7. not healthy: rolls back (§ 10).
- **Switching the version line** (`2.0-pre` → `2.0` at the 2.0.0 release, later `2.0` → `2.1`): edit one line, then update:

  ```bash
  sudo sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=2.0/' /srv/mealmate/.env
  sudo /srv/mealmate/bin/update.sh
  ```

- **Re-running `setup.sh` never updates** (§ 3): it keeps the installed digest. Moving forward is always `update.sh`.
- **Security patches** (SEC-11): fix or bump on `release/X.Y` through a PR → `release-publish kind=patch` → the Pi installs it the same night (or run `update.sh`) → merge the back-merge PR into `main`.

## 10. Rollback

If the new version is not healthy within 180 s, `update.sh` rolls back by itself. The first two steps make the previous version the target, so even a rollback that is cut short ends there; every later step is guarded, a failure is logged and the rollback goes on:

1. records the new digest in `state/bad-digest`;
2. pins the previous digest in `state/override.env`;
3. `mm-compose stop`;
4. removes `data/mealmate.db-wal`, `-shm` and `-journal`;
5. copies the pre-update snapshot's `db.sqlite3` to `state/restore.tmp`, `chown -h 10001:10001`, and `mv -fT` it to `data/mealmate.db`;
6. checks `PRAGMA integrity_check` **and** that `alembic_version` equals the snapshot manifest's revision (the email says `database restored: integrity ok, revision … as in the snapshot`);
7. **always** starts the previous version (`mm-compose up -d`) and removes `state/update-in-progress`;
8. waits for the previous version to be healthy and pings `update` `/fail`. The last log line says `rollback to … complete`, or `rollback to … incomplete; failed: …` with each step that failed (e.g. `restoring the database`).

If every rollback step worked but the previous version is not healthy either, the problem is not the new version (Tailscale, the network, the Pi): the new digest is taken off `state/bad-digest` again and the log says so (`… is NOT recorded as bad`). The pre-update health gate (§ 9 step 3) keeps the next night from trying again until the current version is healthy.

Only the database is rolled back; photos stay (a migration does not touch them). The Pi then **stays on the previous version** and skips the bad digest every night until a **newer** digest appears on the tag, i.e. the next release. `state/bad-digest` keeps the last 20 entries.

- **See the state:** `sudo cat /srv/mealmate/state/override.env /srv/mealmate/state/previous-digest /srv/mealmate/state/bad-digest`; `sudo cat /srv/mealmate/state/update-in-progress` exists only while an update runs (or after one was cut short).
- **Interrupted update:** if an update run was cut short after it pinned the new version (power loss, OOM, killed), `state/update-in-progress` is left behind and the next `update.sh` run decides by what is pinned and what runs: the new version pinned, running and (stably) healthy → the update is finished (host files, image clean-up, ping success; its data is kept, nothing is rolled back); the previous version running and healthy (the new one never started) → the pin goes back to it and the next run tries the update again (`/fail` once); anything else → the full rollback above. Don't delete the marker by hand unless you have checked `override.env` against `previous-digest`.
- **Retry a digest** marked bad (after a verification failure that was cosign's fault, or a rollback you have understood): delete its line from `state/bad-digest`, then `sudo /srv/mealmate/bin/update.sh`:

  ```bash
  sudo sed -i '/^sha256:<digest>$/d' /srv/mealmate/state/bad-digest
  sudo /srv/mealmate/bin/update.sh
  ```

  A failure to *check* the provenance (network, registry) is never recorded; the next night retries by itself.
- **Un-pin** (follow the tag again without verification of a specific digest; only for debugging): `sudo truncate -s 0 /srv/mealmate/state/override.env && sudo /srv/mealmate/bin/mm-compose up -d`. Never delete the file. To pin the running image again, re-run `sudo /srv/mealmate/bin/setup.sh` (it pins the running container's digest); the next update that installs a new digest pins as well.
- **Go back to the previous version by hand** (e.g. a bug found the next day). Don't do this around 04:30, when the nightly update runs. Take a backup and **always** record the current digest as bad, or the night reinstalls it:

  ```bash
  sudo /srv/mealmate/bin/backup.sh --label manual
  sudo sed -n 's/^IMAGE_REF=.*@//p' /srv/mealmate/state/override.env | sudo tee -a /srv/mealmate/state/bad-digest
  PREV=$(sudo cat /srv/mealmate/state/previous-digest)
  echo "IMAGE_REF=ghcr.io/bublemann/mealmate@$PREV" | sudo tee /srv/mealmate/state/override.env
  sudo /srv/mealmate/bin/mm-compose up -d
  ```

  If the app does not start because a migration made the database newer than that version (`sudo /srv/mealmate/bin/mm-compose logs app`), put the pre-update snapshot back instead; this also deploys the snapshot's own image, i.e. the previous version (changes since that snapshot are lost; the current data is moved to `state/pre-restore-<time>/`):

  ```bash
  ls /srv/mealmate/backups/        # the pre-update snapshot: its manifest.json has "label": "pre-update"
  sudo /srv/mealmate/bin/setup.sh --restore /srv/mealmate/backups/<snapshot>
  ```

  The restore also swaps in the snapshot's Tailscale state and restarts `tailscaled`, which drops an SSH session that runs over Tailscale: run it over `mealmate.local` on the home network, or inside `tmux`.

- `update.sh` refuses to update when it cannot tell which digest is running (nothing pinned and Docker knows no repo digest for the running image), because there would be no rollback target. Re-running `sudo /srv/mealmate/bin/setup.sh` fixes that: it pins the running image's digest if Docker knows it; otherwise (e.g. the image was pulled by tag and removed) it installs and pins the verified digest of `IMAGE_TAG`, like a fresh install.

---

## 11. Secret rotation and "Mac or backup lost" (OPS-10)

**Rotate the secret key** (logs everyone out, invite and reset links become invalid):

```bash
sudo /srv/mealmate/bin/setup.sh --rotate-secret
```

**If the Mac or a copy of a backup is lost or stolen** (a snapshot contains the secret key, the Tailscale identity and the SSH host keys):

1. **Tailscale identity:** in the Tailscale console remove the Pi; on the Pi `sudo tailscale up --advertise-tags=tag:mealmate --force-reauth`, approve it, rename it to `mealmate` and share it again with every user (§ 8.1 fallback). Then `sudo tailscale serve --bg --https=443 http://127.0.0.1:8080`.
2. **Secret key:** `sudo /srv/mealmate/bin/setup.sh --rotate-secret`.
3. **SSH host keys** (a thief could impersonate the Pi to the Mac): `sudo rm /etc/ssh/ssh_host_* && sudo dpkg-reconfigure openssh-server && sudo systemctl restart ssh`; on the Mac remove the old entry from `~/.ssh/known_hosts`.
4. **Backup key:** on the new or remaining Mac, delete `~/.ssh/id_ed25519_mealmate_backup*` and re-run `install-backup-pull.sh`; it creates a new key, replaces the one on the Pi and pins the new host key. If the Mac itself is gone, empty `/home/mmbackup/.ssh/authorized_keys` on the Pi right away.
5. **healthchecks.io:** regenerate the ping URLs of all checks and put the new ones into `/srv/mealmate/.env`, the Mac's `~/.mealmate-backup/config` and the `HC_SCAN_URL` Actions secret.
6. Take a manual backup, so a snapshot with the new credentials exists; old snapshots still contain the old ones and age out with the retention.

---

## 12. Troubleshooting

| Symptom | Look at | Typical fix |
|---|---|---|
| `heartbeat` failed: `tailscale: not running` | `tailscale status`, `journalctl -u tailscaled` | `sudo systemctl restart tailscaled`; key expiry must be off (tagged) |
| `heartbeat` failed: `https: …/api/health failed` | `sudo /srv/mealmate/bin/mm-compose ps`, `… logs --tail 100 app`, `tailscale serve status`, `curl -fsS http://127.0.0.1:8080/api/health` | `sudo /srv/mealmate/bin/mm-compose up -d`; `sudo tailscale serve --bg --https=443 http://127.0.0.1:8080` |
| `backup` failed | `journalctl -u mealmate-backup -u mealmate-backup-manual --since -1d`, `cat /srv/mealmate/state/status/backup.json` | the app must be running (`backup-db` runs inside it); disk space; *copying the photos as the app user failed*: something in `data/media` is not readable by uid 10001 (`sudo find /srv/mealmate/data/media ! -user 10001`), fix its owner |
| `backup` silent | `systemctl list-timers 'mealmate-*'`, `systemctl status mealmate-backup.timer` | re-run `setup.sh` to reinstall the units |
| `update` failed | `journalctl -u mealmate-update --since -1d` | see the email (cosign's own error lines are in it): *has no valid build provenance* → the digest is blacklisted in `state/bad-digest`; check the release on GitHub, and only if cosign was wrong, delete the line to retry (§ 10). *no build provenance yet* → the digest has no attestation (the release's `attest` job failed or has not run); nothing recorded, the next night retries. *could not check the build provenance* (network, registry, TUF/Rekor; already retried 3 times) and *cannot resolve* (network or registry down) → nothing recorded, the next night retries by itself. *current version unhealthy, update skipped* → fix the running version first (rows above). *rollback to … complete / incomplete; failed: …* → § 10. *did not finish* → an interrupted update, finished or rolled back by this run (§ 10) |
| `disk` failed | `df -h /`, `sudo du -sh /srv/mealmate/*`, `docker system df` | old images: `update.sh` keeps two; journald is in RAM; delete old `state/pre-restore-*` directories; `media-mirror/` is one extra copy of the photos (by design) |
| `mac-pull` failed | `~/.mealmate-backup/pull.log` | *abnormal pull* (§ 6); *rsync … too old*: `brew upgrade rsync`; host key errors after a new card without restore: re-run the installer |
| App does not start after an update | `sudo /srv/mealmate/bin/mm-compose logs app` (migration errors; the pre-migration copy is in `data/pre-migrate/`) | automatic rollback (§ 10) |
| Locked out as admin | – | `sudo /srv/mealmate/bin/mm-compose exec app mealmate reset-link <username>` |
| RAM | `docker stats --no-stream`, `free -m`, `swapon --show` (only `/dev/zram0`) | the container is limited to 400 MB |

- `mm-compose` is `docker compose` with the right project directory and env files; use it for every Compose command (`ps`, `logs`, `exec`, `up -d`, `stop`).
- Health: `curl -fsS http://127.0.0.1:8080/api/health` on the Pi checks the app (database query, data directory writable); `curl -fsS https://mealmate.<tailnet>.ts.net/api/health` also checks `tailscale serve` and the certificate.
- Admin page → System shows the version, the pinned image digest (`IMAGE_REF`, passed in by `compose.yml`), the last backup and the free disk space (from `state/status/`).

### Diagnostics for the iPhone platform tests (M1 only)

The `/diag` screen (Me → Diagnostics, admins only) needs the diagnostics endpoints, which are off by default. Switch them on for the tests and **off again afterwards**:

```bash
echo 'MEALMATE_DIAGNOSTICS_ENABLED=true' | sudo tee -a /srv/mealmate/.env && sudo /srv/mealmate/bin/mm-compose up -d
# afterwards:
sudo sed -i '/^MEALMATE_DIAGNOSTICS_ENABLED=/d' /srv/mealmate/.env && sudo /srv/mealmate/bin/mm-compose up -d
```

The screen and the endpoints are removed in M9.

### 12.1 Performance check (PERF-02)

From the Mac, against the Pi, as an existing user (not the admin you use daily), with the repository checked out:

```bash
cd e2e && uv run python perf/list_p95.py --base-url https://mealmate.<tailnet>.ts.net \
    --username anna --password-file ~/.mealmate-perf
```

It builds a list of 20 meals / ~150 lines, polls it like three phones and exits with 1 if a p95 is above 300 ms. Details and options: [`e2e/README.md`](../e2e/README.md#performance-perf-02). Also note idle RAM (`docker stats --no-stream`) and the cold start (`sudo /srv/mealmate/bin/mm-compose restart app` until `/api/health` answers; PERF-01/04).

---

## 13. Reference

### 13.1 Status files (shared with the app's admin page)

Written by the host into `/srv/mealmate/state/status/` (the app reads them read-only at `/status/`), atomically (temp file + `mv -fT`), mode `0644`, UTF-8 JSON, at most 4 KB:

- `backup.json`, after every backup run (`ok: false` on failure):

  ```json
  {"finished_at": "2026-09-27T12:15:04Z", "label": "regular", "ok": true,
   "snapshot": "20260927T121500Z", "size_bytes": 12345, "message": "backup 20260927T121500Z (regular) complete"}
  ```

  `label` is `regular`, `pre-update` or `manual`; `snapshot` and `size_bytes` are `null` on failure; `message` is a short status line.
- `disk.json`, hourly: `{"checked_at": "2026-09-27T12:00:01Z", "free_bytes": 1234, "total_bytes": 5678, "free_percent": 21.7}` (the file system of `/`).

### 13.2 `setup.sh` modes

| Command | Does |
|---|---|
| `setup.sh --version <ver>` | fresh install, or a re-run that keeps the installed version (§ 3; `--version` may be left out once `.env` exists) |
| `setup.sh --version <ver> --restore <dir>` | new card from a snapshot (§ 8) |
| `setup.sh --update-host-files [--from <deploy dir>]` | install compose file, scripts and units (used by `update.sh` with the new image's files; each file is replaced by an atomic rename) |
| `setup.sh --rotate-secret` | new secret key, restart (§ 11); waits for `state/deploy.lock` if an update or setup is running |
| `setup.sh --set-backup-key ssh-ed25519 <key>` | the Mac's read-only backup key (used by the Mac installer) |
| `setup.sh --skip-system …` | skip steps 1-4 and the user creation (tests) |

`setup.sh` is also the function library of the scripts in `bin/` (they `source` it; sourcing runs nothing), so the image verification in `setup.sh` and `update.sh` is the same code.

### 13.3 Test overrides

The deploy tests (`deploy/tests/`, `make test-deploy`, CI job "Deploy tests") run the real scripts against the real image, a local `registry:2` and a throw-away root. Every path and external tool can be overridden through the environment. **Never set these on the Pi.**

| Variable | Default | Purpose |
|---|---|---|
| `MEALMATE_ROOT` | `/srv/mealmate` | installation root (units are rewritten to it) |
| `MEALMATE_IMAGE` | `ghcr.io/bublemann/mealmate` | image repository (tests: the local registry) |
| `MEALMATE_SKIP_SYSTEM` | `0` | `1` = `--skip-system` |
| `MEALMATE_SYSTEMD_DIR` | `/etc/systemd/system` | where units are installed |
| `MEALMATE_TAILSCALE_STATE_DIR` | `/var/lib/tailscale` | `tailscaled.state` for backup/restore |
| `MEALMATE_SSH_DIR` | `/etc/ssh` | SSH host keys for backup/restore |
| `MEALMATE_BACKUP_USER` / `_GROUP` / `_HOME` | `mmbackup` / `mmbackup` / from passwd | the backup account |
| `MEALMATE_LOCAL_URL` | `http://127.0.0.1:8080` | local health check |
| `MEALMATE_HEALTH_TIMEOUT` | `180` | seconds to wait for health |
| `MEALMATE_HEALTH_STABLE_CHECKS` / `_STABLE_INTERVAL` / `_POLL_INTERVAL` | `3` / `10` / `2` | stable health: good checks in a row, seconds between them, seconds between failed checks |
| `MEALMATE_PRECHECK_TIMEOUT` | `60` | seconds for the pre-update health gate |
| `MEALMATE_COSIGN_ATTEMPTS` / `_RETRY_DELAY` | `3` / `30` | cosign attempts; pause before retry *n* is *n* × the delay |
| `MEALMATE_LOCK_WAIT` | `900` | seconds `setup.sh` and `--rotate-secret` wait for `state/deploy.lock` |
| `MEALMATE_HEARTBEAT_ATTEMPTS` / `_RETRY_DELAY` | `3` / `15` | heartbeat retries |
| `MEALMATE_DISK_PATH` / `MEALMATE_DISK_MIN_FREE_PERCENT` | `/` / `20` | disk check |
| `DOCKER`, `TAILSCALE`, `COSIGN`, `CURL`, `SYSTEMCTL`, `SQLITE3`, `PYTHON3`, `RSYNC`, `SETPRIV`, `APT_GET` | the real tools (`COSIGN=/usr/local/bin/cosign`) | tests use shims for `cosign`, `tailscale`, `systemctl`, `apt-get` and fault-injecting wrappers of `docker` and `curl` |
| Mac: `MM_PULL_CONFIG` and the `MM_*` keys of the config | `~/.mealmate-backup/config` | `MM_REMOTE` may be a local path in tests |

What the tests cannot cover is listed in § 13.5.

### 13.4 Decisions where the plan left details open

- **cosign** is pinned as the v3.1.3 release binary for linux-arm64 (and amd64) with SHA-256 values taken from the release's `cosign_checksums.txt` and checked against the downloaded binaries. The script refuses a mismatch.
- **setup.sh pins the verified digest** in `state/override.env` (the plan creates it empty): otherwise `mm-compose up` could start a tag that moved after verification. Emptying the file (§ 10) still falls back to the tag. **A re-run keeps the installed digest** and never deploys a digest from `state/bad-digest`; moving forward is only `update.sh`, which has the pre-update backup and the rollback.
- **Restore deploys the snapshot's own image digest** (after verifying it), so database and app version match; the next nightly update moves on as usual.
- **The pre-update database is the only thing a rollback restores**, as in the plan; photos are not touched by migrations.
- **Seven-day floor on both sides:** `prune.py` never deletes anything younger than 7 days, also on the Pi (more snapshots, no risk). The Mac ignores labels from the Pi.
- **The backup copy is moved out of `data/` first and then checked** (one regular file, link count 1): stronger than check-then-move, which a compromised container could race.
- **The Mac re-fetches a snapshot in full** if it fails its checksum after a hard-linked fetch (rsync's size+time quick check could link a file that only looks unchanged), and only then rejects it. Snapshot sizes for the 2 GB guard come from an rsync dry run.
- **The heartbeat stays silent during updates and setup** and retries failures, so a nightly update does not raise an alert; the check's grace period covers the gap.
- **`mealmate-off-refresh`** is skipped (not failed) while the running version has no `jobs off-refresh` (before milestone M7).
- **The manual backup unit** is `mealmate-backup.path` → `mealmate-backup-manual.service`, so it never collides with a running timer backup (both wait on the same lock).
- **`update.sh` refuses without a rollback target** (running digest unknown).
- **Only a definite verification failure blacklists a digest.** cosign's stderr is classified by message (one function, `mm_cosign_failure_kind`, patterns from cosign v3); network, registry, TUF and Rekor errors win over a verification message that contains them and are retried (3 attempts, then the next night). A bare *"no matching attestations"* (no attestation at all) is its own kind, `unsigned`: refused and reported, never recorded, because it is also what a release still being signed looks like (release 2.0.0-alpha.3 was blacklisted that way). `state/bad-digest` keeps the last 20 entries.
- **The rollback records the bad digest and pins the previous one first**, then restores the database step by step, each guarded, and always starts the previous version. If every step worked and the previous version still fails, the new digest is un-recorded: the fault is elsewhere, and the pre-update health gate stops the next attempt until the current version is healthy.
- **An interrupted update is finished, not rolled back, when the new version runs and is healthy:** rolling back would discard everything written since, possibly a whole day. Anything else is rolled back.
- **Stable health** (3 checks, 10 s apart, same container, no restart) instead of the first good answer, so a version that crashes shortly after starting is rolled back.
- **The admin page shows the pinned image:** `compose.yml` passes `IMAGE_REF` as `MEALMATE_IMAGE_DIGEST` (one line beyond plan § 11.1); the app keeps the `sha256:…` part.
- **There is no separate `restore.sh`;** `setup.sh --restore` is the one restore procedure (PLT-06).

### 13.5 What the owner verifies on the real Pi and Mac

The deploy tests run the real scripts against the real image, but these can only be checked on the hardware and accounts:

1. **Tailscale apt key fingerprint (first install):** `setup.sh` pins `2596A99EAAB33821893C0A79458CA832957F5868` for `https://pkgs.tailscale.com/stable/debian/<codename>.noarmor.gpg`; it could not be verified against an independent source when the script was written. Before the first run, on the Mac: `curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg | gpg --show-keys` and compare the primary key's fingerprint with Tailscale's documentation (or ask their support) and with the value in `setup.sh`. If they differ, stop and find out why. The Docker key (`9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`) is the one Docker documents.
2. The system steps 1-4 on Raspberry Pi OS: apt repositories, the unattended-upgrades origins (`apt-cache policy`, O-9), `cgroup_enable=memory` after the reboot, zram as the only swap, journald in RAM, `noatime`, Docker log caps, key-only SSH.
3. Tailscale: login with `tag:mealmate` and expiry disabled, `tailscale serve`, the certificate, and the state swap of a restore (O-1).
4. Real `cosign verify-attestation` against ghcr.io for a release, and what cosign prints when it fails (the classification in § 13.4 follows cosign v3's messages; an unknown message is treated as "could not check", which is safe but alerts every night).
5. `setpriv` reading `data/media` as uid 10001 on the Pi (every backup; a failure says *copying the photos as the app user failed*).
6. systemd timers and `mealmate-backup.path` (the admin page's "Back up now").
7. The update path on the Pi: a real nightly update and, once, a rollback drill (e.g. temporarily pinning a known digest).
8. rrsync with Homebrew rsync (O-5), the Mac installer and launchd.
