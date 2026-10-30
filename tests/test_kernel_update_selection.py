"""Retained module trees must not become automatic boot deployment targets."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'kernel_update_selection', ROOT/'packages/kshim-freedom/freedom-kernel-update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class KernelSelection(unittest.TestCase):
    def test_unowned_rollback_tree_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for release in ['7.2.6-9-freedom', '7.2.6-20-freedom', 'other']:
                p = root/release/'pkgbase'
                p.parent.mkdir()
                p.write_text('other-kernel' if release == 'other' else 'linux-freedom')

            def owner(args, **_kwargs):
                self.assertEqual(args[:4], ['pacman', '-Qqo', '--', str(Path(args[3]))])
                active = '/7.2.6-20-freedom/' in args[3]
                return subprocess.CompletedProcess(args, 0 if active else 1,
                                                   'linux-freedom\n' if active else '')

            with patch.object(update.subprocess, 'run', side_effect=owner) as query:
                self.assertEqual(update.installed_kernel_releases({'pkgbase': 'linux-freedom'}, root),
                                 {'7.2.6-20-freedom'})
                self.assertEqual(query.call_count, 2)

    def test_package_query_failure_aborts_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'candidate').mkdir()
            (root/'candidate/pkgbase').write_text('linux-freedom')
            result = subprocess.CompletedProcess([], 2, '', 'database error')
            with patch.object(update.subprocess, 'run', return_value=result), \
                 self.assertRaises(subprocess.CalledProcessError):
                update.installed_kernel_releases({'pkgbase': 'linux-freedom'}, root)


if __name__ == '__main__':
    unittest.main()
