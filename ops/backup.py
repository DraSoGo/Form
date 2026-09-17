#!/usr/bin/env python3
"""Fitness-only NAS snapshots. Requires root/docker access, Python 3 and mounted CIFS."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import uuid

APP = Path('/srv/docker/apps/fitness')
MOUNT = Path('/mnt/nas-backup')
ROOT = MOUNT / 'Fitness'
EXPECTED_CIFS_SOURCE = os.environ.get('BACKUP_CIFS_SOURCE', '')
MEDIA = APP / 'data/media'
STATE = APP / 'data/backup-status.json'
SNAPSHOT = re.compile(r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')
DIGEST = re.compile(r'^[a-f0-9]{64}$')
REVISION = re.compile(r'^[a-f0-9]{7,64}$')


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def deployed_revision():
    marker = APP / '.revision'
    if marker.is_file():
        value = marker.read_text().strip()
        if not REVISION.fullmatch(value):
            raise RuntimeError('Invalid deployment revision marker')
        return value
    result = run(['git', '-C', str(APP), 'rev-parse', 'HEAD'], stdout=subprocess.PIPE)
    value = result.stdout.decode().strip()
    if not REVISION.fullmatch(value):
        raise RuntimeError('Invalid Git revision')
    return value


def db(args, **kwargs):
    return run(['docker', 'compose', '--project-directory', str(APP), 'exec', '-T', 'db', *args], **kwargs)


def sql(statement, database=None):
    # Only generated database names, never user-provided identifiers, enter this shell.
    args = ['sh', '-c', 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "${1:-$POSTGRES_DB}" -At', 'psql']
    if database:
        args.append(database)
    return db(args, input=statement.encode(), stdout=subprocess.PIPE).stdout.decode().strip()


def database_state(database=None):
    tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;", database).splitlines()
    if not {'django_migrations', 'auth_user'} <= set(tables) or not any(t.startswith('core_') for t in tables):
        raise RuntimeError('Application schema missing')
    counts = {}
    for table in tables:
        identifier = '"' + table.replace('"', '""') + '"'
        counts[table] = int(sql('SELECT count(*) FROM public.' + identifier, database))
    migrations = json.loads(sql("SELECT coalesce(json_agg(row_to_json(m) ORDER BY app,name), '[]'::json) FROM (SELECT app,name,applied FROM django_migrations) m;", database))
    if not migrations:
        raise RuntimeError('Application migrations empty')
    # pg_restore can compact dropped-column gaps, changing ordinal_position while
    # preserving every live column. Compare semantic column definitions only.
    columns = json.loads(sql("SELECT coalesce(json_agg(row_to_json(c) ORDER BY table_name,column_name), '[]'::json) FROM (SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public') c;", database))
    constraints = json.loads(sql("SELECT coalesce(json_agg(row_to_json(c) ORDER BY table_name,name), '[]'::json) FROM (SELECT r.relname AS table_name, con.conname AS name, pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con JOIN pg_class r ON r.oid=con.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public') c;", database))
    return {'table_counts': counts, 'migrations': migrations, 'columns': columns, 'constraints': constraints}


def record_status(result):
    try:
        previous = json.loads(STATE.read_text())
    except (FileNotFoundError, ValueError):
        previous = {}
    for field in ['last_backup_at', 'last_backup_snapshot', 'last_restore_test_at']:
        if field in previous:
            result[field] = previous[field]
    if result['status'] == 'backup_ok':
        result['last_backup_at'] = result['at']
        result['last_backup_snapshot'] = result['snapshot']
    elif result['status'] == 'restore_test_ok':
        result['last_restore_test_at'] = result['at']
    atomic_json(STATE, result)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def mounted():
    if not os.path.ismount(MOUNT):
        raise RuntimeError('NAS mount absent; refusing all backup writes')
    result = run(['findmnt', '-n', '-o', 'FSTYPE,SOURCE', '--target', str(MOUNT)], stdout=subprocess.PIPE).stdout.decode()
    mounts = [tuple(line.split()) for line in result.splitlines() if line.split()]
    expected = ('cifs', EXPECTED_CIFS_SOURCE) if EXPECTED_CIFS_SOURCE else None
    if expected and expected not in mounts:
        raise RuntimeError('Unexpected NAS mount source/type')
    if not expected and not any(filesystem == 'cifs' for filesystem, _ in mounts):
        raise RuntimeError('Unexpected NAS mount source/type')
    if ROOT.is_symlink():
        raise RuntimeError('Backup root must not be a symlink')


def published():
    return sorted((p for p in (ROOT / 'snapshots').iterdir() if SNAPSHOT.fullmatch(p.name) and p.is_dir()), reverse=True)


def retention(names):
    ordered = sorted(names, reverse=True)
    daily, weekly = {}, {}
    for name in ordered:
        stamp = dt.datetime.strptime(name[:16], '%Y%m%dT%H%M%SZ')
        daily.setdefault(stamp.date().isoformat(), name)
        weekly.setdefault(stamp.strftime('%G-W%V'), name)
    return set(list(daily.values())[:14]) | set(list(weekly.values())[:8])


def verify(path):
    if not SNAPSHOT.fullmatch(path.name) or path.parent != ROOT / 'snapshots':
        raise ValueError('Invalid snapshot path')
    checks = json.loads((path / 'checksums.json').read_text())
    if set(checks) != {'database.dump', 'manifest.json', 'config.json'}:
        raise ValueError('Invalid checksum manifest')
    for name, expected in checks.items():
        if digest(path / name) != expected:
            raise ValueError('Snapshot checksum mismatch: ' + name)
    manifest = json.loads((path / 'manifest.json').read_text())
    for name, sha in manifest['media'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or not DIGEST.fullmatch(sha):
            raise ValueError('Invalid media manifest')
        if digest(ROOT / 'blobs' / sha) != sha:
            raise ValueError('Media checksum mismatch: ' + name)
    return manifest


def prune():
    snapshots = published()
    keep = retention([p.name for p in snapshots])
    # Validate every retained reference before deleting any archive or blob.
    refs = set()
    for path in snapshots:
        if path.name in keep:
            refs.update(verify(path)['media'].values())
    for path in snapshots:
        if path.name not in keep:
            shutil.rmtree(path)
    for blob in (ROOT / 'blobs').iterdir():
        if DIGEST.fullmatch(blob.name) and blob.name not in refs:
            blob.unlink()


def backup():
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    path = ROOT / 'snapshots' / ('.partial-' + stamp)
    path.mkdir()
    # Freeze media mutations across DB dump/media copy, then always resume.
    compose = ['docker', 'compose', '--project-directory', str(APP)]
    running = run(compose + ['ps', '--status', 'running', '--services'], stdout=subprocess.PIPE).stdout.decode().splitlines()
    stopped = [name for name in ['web', 'worker'] if name in running]
    try:
        if stopped:
            run(compose + ['stop', *stopped])
        with (path / 'database.dump').open('wb') as out:
            db(['sh', '-c', 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl'], stdout=out)
            out.flush()
            os.fsync(out.fileno())
        expected_database = database_state()
        media = {}
        for source in sorted(MEDIA.rglob('*')):
            if source.is_symlink():
                raise ValueError('Media symlink refused')
            if not source.is_file():
                continue
            sha = digest(source)
            blob = ROOT / 'blobs' / sha
            if not blob.exists():
                tmp = blob.with_name('.partial-' + uuid.uuid4().hex)
                shutil.copyfile(source, tmp)
                if digest(tmp) != sha:
                    tmp.unlink()
                    raise RuntimeError('Media changed during copy')
                tmp.replace(blob)
            elif digest(blob) != sha:
                raise RuntimeError('Existing NAS blob corrupted')
            media[str(source.relative_to(MEDIA))] = sha
        atomic_json(path / 'manifest.json', {'format': 2, 'created': stamp, 'media': media, 'database': expected_database})
    finally:
        if stopped:
            run(compose + ['start', *stopped])
    revision = deployed_revision()
    config = {'revision': revision, 'files': {name: (APP / name).read_text() for name in ['compose.yaml', '.env.example', 'Dockerfile', 'requirements.txt', 'requirements.lock']}}
    atomic_json(path / 'config.json', config)
    atomic_json(path / 'checksums.json', {name: digest(path / name) for name in ['database.dump', 'manifest.json', 'config.json']})
    final = path.with_name(stamp)
    path.replace(final)
    verify(final)
    prune()
    return {'snapshot': stamp, 'media_files': len(media), 'status': 'backup_ok'}


def restore_test(path):
    manifest = verify(path)
    temporary_db = 'fitness_restore_' + uuid.uuid4().hex
    created = False
    try:
        sql('CREATE DATABASE ' + temporary_db + ';')
        created = True
        with (path / 'database.dump').open('rb') as stream:
            db(['sh', '-c', 'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --exit-on-error', 'restore', temporary_db], stdin=stream)
        restored_database = database_state(temporary_db)
        if manifest.get('format') != 2 or 'database' not in manifest:
            raise RuntimeError('Snapshot lacks expected database state; create a new backup')
        if restored_database != manifest['database']:
            raise RuntimeError('Restored schema, table counts or migration state differ from snapshot')
        counts = restored_database['table_counts']
        # Actually reconstruct media into isolated temporary local files and hash again.
        with tempfile.TemporaryDirectory(prefix='fitness-media-restore-') as folder:
            for name, sha in manifest['media'].items():
                destination = Path(folder) / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / 'blobs' / sha, destination)
                if digest(destination) != sha:
                    raise RuntimeError('Restored media mismatch')
        return {'status': 'restore_test_ok', 'snapshot': path.name, 'table_counts': counts, 'media_files': len(manifest['media'])}
    finally:
        if created:
            sql('DROP DATABASE ' + temporary_db + ' WITH (FORCE);')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['backup', 'verify', 'restore-test', 'prune'])
    parser.add_argument('--snapshot', help='Published snapshot name; defaults to newest')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError('Backup interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    os.umask(0o077)
    (APP / 'data').mkdir(parents=True, exist_ok=True)
    with (APP / 'data/backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            mounted()
            (ROOT / 'snapshots').mkdir(parents=True, exist_ok=True)
            (ROOT / 'blobs').mkdir(exist_ok=True)
            if args.command == 'backup':
                result = backup()
            elif args.command == 'prune':
                prune()
                result = {'status': 'prune_ok'}
            else:
                name = args.snapshot or published()[0].name
                path = ROOT / 'snapshots' / name
                result = restore_test(path) if args.command == 'restore-test' else {'status': 'verify_ok', 'media_files': len(verify(path)['media'])}
            result['at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            record_status(result)
            print(json.dumps(result, sort_keys=True))
        except Exception as exc:
            record_status({'status': 'failed', 'command': args.command, 'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error_type': type(exc).__name__})
            raise


if __name__ == '__main__':
    main()
