"""Exercise firmware handling using tiny synthetic files, never device firmware."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


HELPER_PATH = Path(__file__).resolve().parents[1] / 'scripts/ci/firmware-bundle.py'
SPEC = importlib.util.spec_from_file_location('firmware_bundle', HELPER_PATH)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class FirmwareBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.files = {
            'qcom/device/board.bin': b'synthetic board firmware\x00\xff',
            'audio.bin': b'synthetic audio firmware',
        }
        self.rows = {
            name: {'path': name, 'size': len(data),
                   'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in self.files.items()
        }
        self.source = self.base / 'source'
        for name, data in self.files.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def write_archive(self, archive, entries):
        with tarfile.open(archive, 'w:gz') as out:
            for name, data, kind in entries:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                if kind == tarfile.REGTYPE:
                    entry.size = len(data)
                    out.addfile(entry, io.BytesIO(data))
                else:
                    entry.linkname = '../outside.bin'
                    out.addfile(entry)

    def regular_entries(self):
        return [(name, data, tarfile.REGTYPE) for name, data in self.files.items()]

    def test_pack_is_deterministic_and_roundtrips_nested_files(self):
        first, second = self.base / 'first.tar.gz', self.base / 'second.tar.gz'
        bundle.pack(self.source, first, self.rows)
        # Source permissions and dictionary order must not affect the bundle.
        (self.source / 'audio.bin').chmod(0o600)
        bundle.pack(self.source, second, dict(reversed(list(self.rows.items()))))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        destination = self.base / 'unpacked'
        bundle.unpack(first, destination, self.rows)
        self.assertEqual(
            {str(path.relative_to(destination)): path.read_bytes()
             for path in destination.rglob('*') if path.is_file()}, self.files)
        bundle.verify(destination, self.rows)

    def test_untrusted_archives_fail_without_publishing_partial_output(self):
        valid = self.regular_entries()
        name, data, kind = valid[0]
        cases = {
            'parent-traversal': valid + [('../outside.bin', b'bad', tarfile.REGTYPE)],
            'absolute-path': valid + [('/outside.bin', b'bad', tarfile.REGTYPE)],
            'symlink': valid[1:] + [(name, b'', tarfile.SYMTYPE)],
            'hardlink': valid[1:] + [(name, b'', tarfile.LNKTYPE)],
            'duplicate': valid + [valid[0]],
            'bad-hash': valid[1:] + [(name, b'X' * len(data), kind)],
            'bad-size': valid[1:] + [(name, data + b'X', kind)],
            'missing': valid[1:],
        }
        for case, entries in cases.items():
            with self.subTest(case=case):
                case_directory = self.base / case
                case_directory.mkdir()
                archive = case_directory / 'input.tar.gz'
                destination = case_directory / 'output'
                self.write_archive(archive, entries)
                with self.assertRaises(ValueError):
                    bundle.unpack(archive, destination, self.rows)
                # No partially verified destination or temporary payload remains.
                self.assertEqual(list(case_directory.iterdir()), [archive])
                self.assertFalse((self.base / 'outside.bin').exists())

    def test_unpack_preserves_existing_destination(self):
        archive = self.base / 'input.tar.gz'
        bundle.pack(self.source, archive, self.rows)
        destination = self.base / 'existing'
        destination.mkdir()
        sentinel = destination / 'keep.txt'
        sentinel.write_bytes(b'keep existing contents')
        with self.assertRaises(ValueError):
            bundle.unpack(archive, destination, self.rows)
        self.assertEqual(list(destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'keep existing contents')

    def test_pack_preserves_existing_archive(self):
        archive = self.base / 'existing.tar.gz'
        archive.write_bytes(b'keep existing archive')
        with self.assertRaises(ValueError):
            bundle.pack(self.source, archive, self.rows)
        self.assertEqual(archive.read_bytes(), b'keep existing archive')

    def test_dangling_output_symlinks_are_preserved(self):
        absent_target = self.base / 'must-not-be-created'
        archive = self.base / 'linked.tar.gz'
        archive.symlink_to(absent_target)
        with self.assertRaises(ValueError):
            bundle.pack(self.source, archive, self.rows)
        self.assertTrue(archive.is_symlink())
        self.assertFalse(absent_target.exists())
        valid_archive = self.base / 'valid.tar.gz'
        bundle.pack(self.source, valid_archive, self.rows)
        destination = self.base / 'linked-directory'
        destination.symlink_to(absent_target)
        with self.assertRaises(ValueError):
            bundle.unpack(valid_archive, destination, self.rows)
        self.assertTrue(destination.is_symlink())
        self.assertFalse(absent_target.exists())

    def test_pack_rejects_invalid_sources_before_creating_archive(self):
        source_file = self.source / 'audio.bin'
        original = source_file.read_bytes()
        outside = self.base / 'external.bin'
        outside.write_bytes(original)
        for case in ('missing', 'symlink', 'bad-hash'):
            with self.subTest(case=case):
                source_file.unlink()
                if case == 'symlink':
                    source_file.symlink_to(outside)
                elif case == 'bad-hash':
                    source_file.write_bytes(b'X' * len(original))
                archive = self.base / f'{case}.tar.gz'
                with self.assertRaises(ValueError):
                    bundle.pack(self.source, archive, self.rows)
                self.assertFalse(archive.exists())
                if source_file.is_symlink() or source_file.exists():
                    source_file.unlink()
                source_file.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
