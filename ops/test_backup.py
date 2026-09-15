import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup', Path(__file__).with_name('backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
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
