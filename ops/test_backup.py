import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('backup', Path(__file__).with_name('backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_deployed_revision_uses_release_marker_without_git_checkout(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'APP', Path(directory)):
            (Path(directory) / '.revision').write_text('481a263deadbeef\n')
            with patch.object(backup, 'run') as run:
                self.assertEqual(backup.deployed_revision(), '481a263deadbeef')
                run.assert_not_called()

    def test_backup_seals_expected_database_before_resuming(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / 'app'
            root = Path(directory) / 'nas'
            app.mkdir()
            (root / 'snapshots').mkdir(parents=True)
            (root / 'blobs').mkdir()
            media = app / 'media'
            media.mkdir()
            for name in ['compose.yaml', '.env.example', 'Dockerfile', 'requirements.txt', 'requirements.lock']:
                (app / name).write_text('sanitized')
            state = {'table_counts': {'auth_user': 1}, 'migrations': ['core.0001'], 'columns': [], 'constraints': []}
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(stdout=b'web\nworker\n' if 'ps' in command else b'deadbeef')
            def get_state():
                self.assertFalse(any('start' in command for command in calls))
                return state
            with patch.object(backup, 'APP', app), patch.object(backup, 'ROOT', root), patch.object(backup, 'MEDIA', media), patch.object(backup, 'run', side_effect=run), patch.object(backup, 'db'), patch.object(backup, 'database_state', side_effect=get_state):
                result = backup.backup()
                manifest = backup.verify(root / 'snapshots' / result['snapshot'])
                self.assertEqual(manifest['database'], state)
                self.assertEqual(manifest['format'], 2)
                self.assertTrue(any('start' in command for command in calls))

    def test_restore_mismatch_fails_and_cleans_temporary_database(self):
        expected = {'table_counts': {'auth_user': 1}, 'migrations': ['core.0001'], 'columns': [], 'constraints': []}
        for changed in [dict(expected, table_counts={'auth_user': 0}), dict(expected, migrations=['core.0002']), dict(expected, columns=['missing'])]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'snapshot'
                path.mkdir()
                (path / 'database.dump').write_bytes(b'dump')
                with patch.object(backup, 'verify', return_value={'format': 2, 'database': expected, 'media': {}}), patch.object(backup, 'database_state', return_value=changed), patch.object(backup, 'db'), patch.object(backup, 'sql') as sql:
                    with self.assertRaisesRegex(RuntimeError, 'differ from snapshot'):
                        backup.restore_test(path)
                    created = sql.call_args_list[0].args[0].split()[2].rstrip(';')
                    self.assertRegex(created, r'^fitness_restore_[a-f0-9]{32}$')
                    self.assertEqual(sql.call_args_list[-1].args[0], 'DROP DATABASE ' + created + ' WITH (FORCE);')

    def test_failed_backup_resumes_only_originally_running_services(self):
        for failure in [RuntimeError('dump failed'), InterruptedError('terminated')]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, patch.object(backup, 'ROOT', Path(directory)):
                (Path(directory) / 'snapshots').mkdir()
                with patch.object(backup, 'run', return_value=SimpleNamespace(stdout=b'web\ndb\n')) as run, patch.object(backup, 'db', side_effect=failure):
                    with self.assertRaises(type(failure)):
                        backup.backup()
                    commands = [call.args[0] for call in run.call_args_list]
                    self.assertEqual(commands[-2][-2:], ['stop', 'web'])
                    self.assertEqual(commands[-1][-2:], ['start', 'web'])

    def test_status_preserves_backup_freshness_across_verification_and_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'STATE', Path(directory) / 'status.json'):
            backup.record_status({'status': 'backup_ok', 'at': 'first', 'snapshot': 'snapshot-one'})
            backup.record_status({'status': 'verify_ok', 'at': 'second'})
            backup.record_status({'status': 'failed', 'at': 'third'})
            state = json.loads(backup.STATE.read_text())
            self.assertEqual(state['last_backup_at'], 'first')
            self.assertEqual(state['last_backup_snapshot'], 'snapshot-one')
            self.assertEqual(state['status'], 'failed')

    def test_retention_keeps_daily_and_weekly(self):
        today = dt.datetime(2026, 9, 15)
        names = [(today - dt.timedelta(days=n)).strftime('%Y%m%dT%H%M%SZ') + '-1234abcd' for n in range(100)]
        keep = backup.retention(names)
        self.assertTrue(set(names[:14]) <= keep)
        self.assertLessEqual(len(keep), 22)
        weeks = {dt.datetime.strptime(n[:16], '%Y%m%dT%H%M%SZ').strftime('%G-W%V') for n in keep}
        self.assertEqual(len(weeks), 8)
        self.assertNotIn(names[-1], keep)

    def test_daily_deduplicates_multiple_runs(self):
        self.assertEqual(backup.retention(['20260915T000000Z-1234abcd', '20260915T010000Z-1234abcd']), {'20260915T010000Z-1234abcd'})

    def test_mount_missing_fails_closed(self):
        with patch.object(backup.os.path, 'ismount', return_value=False), patch.object(backup, 'run') as run:
            with self.assertRaises(RuntimeError):
                backup.mounted()
            run.assert_not_called()

    def test_mount_accepts_systemd_automount_plus_expected_cifs(self):
        output = b'autofs systemd-1\ncifs   //192.168.1.38/server-backup\n'
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'MOUNT', Path(directory)), patch.object(backup, 'ROOT', Path(directory) / 'Fitness'), patch.object(backup.os.path, 'ismount', return_value=True), patch.object(backup, 'run', return_value=SimpleNamespace(stdout=output)):
            backup.mounted()

    def test_checksums_corruption_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'ROOT', Path(directory)):
            root = Path(directory)
            path = root / 'snapshots/20260915T000000Z-1234abcd'
            path.mkdir(parents=True)
            (root / 'blobs').mkdir()
            (path / 'database.dump').write_bytes(b'dump')
            (path / 'config.json').write_text('{}')
            (path / 'manifest.json').write_text(json.dumps({'media': {}}))
            def seal():
                backup.atomic_json(path / 'checksums.json', {name: backup.digest(path / name) for name in ['database.dump', 'config.json', 'manifest.json']})
            seal()
            self.assertEqual(backup.verify(path)['media'], {})
            (path / 'database.dump').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                backup.verify(path)
            (path / 'manifest.json').write_text(json.dumps({'media': {'../escape': 'a' * 64}}))
            seal()
            with self.assertRaises(ValueError):
                backup.verify(path)

    def test_prune_removes_only_unreferenced_blobs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'ROOT', Path(directory)):
            root = Path(directory)
            path = root / 'snapshots/20260915T000000Z-1234abcd'
            path.mkdir(parents=True)
            (root / 'blobs').mkdir()
            orphan = root / 'blobs' / ('a' * 64)
            orphan.write_bytes(b'orphan')
            unrelated = root / 'blobs/readme'
            unrelated.write_text('untouched')
            for name, value in [('database.dump', b'dump'), ('config.json', b'{}'), ('manifest.json', b'{"media": {}}')]:
                (path / name).write_bytes(value)
            backup.atomic_json(path / 'checksums.json', {name: backup.digest(path / name) for name in ['database.dump', 'config.json', 'manifest.json']})
            backup.prune()
            self.assertFalse(orphan.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
