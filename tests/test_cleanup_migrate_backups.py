import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'cleanup_migrate_backups.py'
spec = importlib.util.spec_from_file_location('cleanup_migrate_backups', SCRIPT)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'backups'
        self.root.mkdir()
        for name in ['20260901-010101', '20260930-010101', 'customer-data']:
            (self.root / name).mkdir()
            (self.root / name / 'data').write_text('fixture')

    def test_preview_excludes_foreign_data_and_changes_nothing(self):
        plan = cleanup.make_plan(self.root, 0)
        self.assertEqual(['20260901-010101', '20260930-010101'], [p['name'] for p in plan['remove']])
        self.assertEqual(3, len(list(self.root.iterdir())))

    def test_apply_deletes_only_unchanged_reviewed_selection(self):
        cleanup.apply_plan(self.root, 1, cleanup.make_plan(self.root, 1))
        self.assertEqual({'20260930-010101', 'customer-data'}, {p.name for p in self.root.iterdir()})

    def test_changed_content_or_new_run_requires_new_preview(self):
        plan = cleanup.make_plan(self.root, 1)
        (self.root / '20260901-010101/data').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            cleanup.apply_plan(self.root, 1, plan)
        plan = cleanup.make_plan(self.root, 1)
        (self.root / '20261001-010101').mkdir()
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            cleanup.apply_plan(self.root, 1, plan)

    def test_tampered_plan_cannot_select_foreign_directory(self):
        plan = cleanup.make_plan(self.root, 1)
        plan['remove'].append(cleanup.fingerprint(self.root / 'customer-data'))
        with self.assertRaises(ValueError):
            cleanup.apply_plan(self.root, 1, plan)
        self.assertTrue((self.root / 'customer-data/data').is_file())

    def test_links_and_broad_roots_refused(self):
        for root in ['', '/', '/workspace', str(Path.home())]:
            with self.subTest(root=root), self.assertRaises(ValueError):
                cleanup.checked_root(root)
        link = self.base / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            cleanup.checked_root(link)
        (self.root / '20260901-010101/escape').symlink_to(self.base)
        with self.assertRaises(ValueError):
            cleanup.make_plan(self.root, 0)

    def test_shell_entry_defaults_to_preview_and_apply_needs_plan(self):
        command = ['bash', str(SCRIPT.with_name('cleanup-migrate-backups.sh')), '0', str(self.root)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('preview', json.loads(result.stdout)['action'])
        result = subprocess.run([*command, '--apply'], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(3, len(list(self.root.iterdir())))


if __name__ == '__main__':
    unittest.main()
