# Backup and restore

## Scope and consistency

`ops/backup.py` owns only `/mnt/nas-backup/Fitness` and local `data/backup*` state. It verifies that `/mnt/nas-backup` is a CIFS mount before writing. Set `BACKUP_CIFS_SOURCE=//<NAS_IP>/server-backup` to require one exact source. An unavailable or unexpected mount fails closed, so the job cannot fill the root disk as a fallback. An advisory lock prevents overlapping backup, verification, pruning, and restore tests.

Version-2 snapshots contain the expected schema/table counts and migration state plus a PostgreSQL custom-format dump, SHA-256 manifest of every media file, checksums, Git revision and sanitized deployment files. Secrets, actual runtime environment, sessions outside the database, and unrelated applications are never copied as configuration. The database dump contains private health records and server sessions: protect NAS access accordingly. Source code is recoverable from the recorded Git revision and repository, not copied into archives.

The job stops only currently running Fitness web/worker services during database dump and media copy to keep files consistent with metadata, then restarts the same set even on error or SIGTERM/SIGHUP. This causes a brief nightly Fitness outage; the first large media backup can take longer. Other services stay running. An uncatchable kill or host crash can leave Fitness stopped: run `docker compose start web worker` after checking the journal. Do not run migrations/imports through independent management containers during a backup.

Media is stored once per SHA-256 content blob; snapshots refer to immutable blobs, requiring neither hardlinks nor full repeated media copies on CIFS. Snapshots publish by directory rename after all files/checksums exist. Verification detects accidental corruption; SHA-256 is not an authenticity signature against a NAS administrator. The share's availability and server durability still depend on NAS configuration.

Retention keeps the latest snapshot for each of the last 14 **available backup days**, plus the latest snapshot in each of the last 8 **available ISO weeks**. Missing schedules do not erase the last good history. After validating all retained snapshots, pruning removes older owned snapshots and media blobs with no retained references. Deleted/expired application photos can remain in backups up to the retained weekly history; application retention does not instantly erase historical backup copies. Partial failed snapshots are hidden and not restore candidates; inspect and manually remove only `.partial-*` files/directories belonging to Fitness after resolving failures.

## Commands

Run on the host as root (or an account with Docker and share access):

```sh
cd /srv/docker/apps/fitness
sudo python3 ops/backup.py backup
sudo python3 ops/backup.py verify
sudo python3 ops/backup.py restore-test
sudo python3 ops/backup.py prune
```

Use `--snapshot YYYYMMDDTHHMMSSZ-xxxxxxxx` to verify/test an older published snapshot. No command restores over the live database. `restore-test` creates a random `fitness_restore_<uuid>` database in the Fitness PostgreSQL container, restores with errors fatal, checks Django/auth/core schema and migration rows, compares every public table count, column/constraint definition and applied migration state exactly against the checksum-sealed state captured while writers were stopped, reconstructs all media in a temporary host directory and validates hashes. It drops only the temporary database in `finally`. Ensure local free space accommodates a second database and restored media. The database server must be running.

Structured last-operation status is `/srv/docker/apps/fitness/data/backup-status.json`; systemd journal retains complete backup/restore logs. Latest-operation status is replaced by each operation; `last_backup_at` and `last_backup_snapshot` preserve the last successful backup independently of verification, pruning or failures. `last_restore_test_at` preserves the last successful restore test. Use the journal for full history. Logs contain counts and object names, never record contents or secrets. No success ping integration is assumed.

Install only Fitness units:

```sh
sudo install -m 644 ops/fitness-backup.service ops/fitness-backup.timer ops/fitness-restore-test.service ops/fitness-restore-test.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fitness-backup.timer fitness-restore-test.timer
sudo systemctl list-timers fitness-backup.timer fitness-restore-test.timer
sudo journalctl -u fitness-backup.service -u fitness-restore-test.service
```

Daily backup runs 03:30 host time plus 0–15 minutes; Sunday isolated restore test runs 05:00 plus 0–15 minutes. Persistent timers catch missed runs. Confirm host timezone with `timedatectl`; it may differ from the app's Asia/Bangkok timezone.

## Disaster recovery and rollback

1. Preserve the failed live storage unchanged. Recover repository at the snapshot's `config.json` Git revision. Provision a separate project/database volume and media directory; keep public traffic on maintenance or the previous app.
2. Recover `runtime.env` from your separately protected password/secret vault, or generate a new Django secret/database credential and re-enter rotated provider/VAPID credentials. Backups intentionally cannot recover those secrets. A changed Django secret invalidates sessions; changed VAPID keys require push resubscription.
3. Verify the desired archive with this helper. In the separate recovery PostgreSQL service, stream `database.dump` to `pg_restore --no-owner --no-acl --exit-on-error` as its database owner into an empty database. Use `docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error' < /mnt/nas-backup/Fitness/snapshots/SNAPSHOT/database.dump` only from the **separate recovery project's directory** and after verifying its Compose project/volume identity.
4. Reconstruct media by reading `manifest.json`: for each relative path, copy the corresponding SHA-256-named blob from `Fitness/blobs` to the new media directory and check its hash. Reject absolute paths/`..`; set ownership 1000:1000. `restore-test` contains the exact reconstruction algorithm.
5. Run the snapshot-compatible image, login, inspect representative body/nutrition/workout records and photos, and verify `/health`. Upgrade schema only after taking a backup of this recovery state.
6. Switch the Fitness proxy only after recovery acceptance. Retain the previous data and deployment until acceptance. Do not run `docker compose down -v`, global prune, or restore directly over live data.

For an application-only rollback with compatible migrations, set `FITNESS_IMAGE_TAG` to the preserved previous image and recreate web/worker. If migrations are incompatible, restore snapshot code and data into separate storage as above. Reversing migrations blindly can lose data.

Local tests: `python3 -m unittest discover -s ops -p 'test_*.py' -v`. These never contact production or run Docker.
