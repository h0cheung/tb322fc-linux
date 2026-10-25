"""Exercise replacement validation and rollback without touching a boot device."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'packages/kshim-freedom/kshim-android-base-replace.py'
spec = importlib.util.spec_from_file_location('android_base_replace', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def boot_image(marker):
    image = bytearray(16384)
    image[:8] = b'ANDROID!'
    struct.pack_into('<IIIII', image, 8, 128, 0, 0, 1584, 0)
    struct.pack_into('<I', image, 40, 4)
    image[4096:4224] = bytes([marker]) * 128
    image[4152:4156] = b'ARM\x64'
    image[-64:] = struct.pack('>4sIIQQQ28s', b'AVBf', 1, 0, 8192, 8192, 256, bytes(28))
    return bytes(image)


class AndroidBaseReplacement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.stock = self.root / 'stock.img'
        self.stock.write_bytes(boot_image(1))
        self.source = self.root / 'new.img'
        self.source.write_bytes(boot_image(2))
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(dict(stock_boot=str(self.stock), stock_boot_sha256=module.digest(self.stock),
                                              deploy_boot_a=True, pkgbase='linux-freedom')))
        self.latest = self.state / 'latest.json'
        self.latest.write_text('{"previous": true}\n')
        self.before = (self.stock.read_bytes(), self.config.read_bytes(), self.latest.read_bytes())
        self.verify = mock.patch.object(module.subprocess, 'run')
        self.info = mock.patch.object(module.subprocess, 'check_output', return_value=
                                      'Algorithm: SHA256_RSA4096\n    Partition Name: boot\n')
        self.verify.start()
        self.info.start()
        self.addCleanup(self.verify.stop)
        self.addCleanup(self.info.stop)

    def replace(self, check_only=False):
        return module.replace_base(self.source, self.config, 'test-kernel', check_only,
                                   state=self.state, lib=self.root)

    def assert_original(self):
        self.assertEqual(self.before, (self.stock.read_bytes(), self.config.read_bytes(), self.latest.read_bytes()))

    def fake_build(self, config, kernel, lock_fd):
        candidate_config = json.loads(config.read_text())
        self.assertEqual(candidate_config['stock_boot_sha256'], module.digest(self.source))
        # The live configuration is untouched throughout the build.
        self.assert_original()
        candidate = self.state / 'candidate.img'
        candidate.write_bytes(boot_image(3))
        self.latest.write_text(json.dumps(dict(release=kernel, deployed=False, image=str(candidate),
                                               sha256=module.digest(candidate))))

    def test_check_only_does_not_build_or_change_files(self):
        with mock.patch.object(module, 'build_candidate') as build:
            result = self.replace(True)
        self.assertFalse(result['changed'])
        build.assert_not_called()
        self.assert_original()
        self.assertFalse(list(self.state.glob('base-*')))

    def test_bad_footer_rejected_before_build(self):
        self.source.write_bytes(self.source.read_bytes()[:-64] + bytes(64))
        with mock.patch.object(module, 'build_candidate') as build:
            with self.assertRaisesRegex(ValueError, 'AVB footer'):
                self.replace()
        build.assert_not_called()
        self.assert_original()

    def test_compressed_kernel_rejected(self):
        data = bytearray(self.source.read_bytes())
        data[4152:4156] = bytes(4)
        self.source.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'uncompressed ARM64'):
            self.replace()
        self.assert_original()

    def test_footer_cannot_point_into_kernel(self):
        data = bytearray(self.source.read_bytes())
        data[-64:] = struct.pack('>4sIIQQQ28s', b'AVBf', 1, 0, 1, 1, 256, bytes(28))
        self.source.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'overlaps the kernel'):
            self.replace()
        self.assert_original()

    def test_signature_verification_failure_keeps_original(self):
        with mock.patch.object(module.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['verify'])):
            with self.assertRaises(subprocess.CalledProcessError):
                self.replace()
        self.assert_original()

    def test_build_failure_keeps_original(self):
        with mock.patch.object(module, 'build_candidate', side_effect=RuntimeError('build failed')):
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                self.replace()
        self.assert_original()
        self.assertEqual(json.loads(next(self.state.glob('base-*/result.json')).read_text())['status'],
                         'failed_original_restored')

    def test_missing_kernel_cannot_reuse_old_candidate(self):
        with mock.patch.object(module, 'build_candidate'):
            with self.assertRaisesRegex(RuntimeError, 'did not produce a new candidate'):
                self.replace()
        self.assert_original()

    def test_success_updates_base_and_only_hash_in_live_config(self):
        old_config = json.loads(self.config.read_text())
        with mock.patch.object(module, 'build_candidate', side_effect=self.fake_build):
            result = self.replace()
        old_config['stock_boot_sha256'] = module.digest(self.source)
        self.assertEqual(json.loads(self.config.read_text()), old_config)
        self.assertEqual(self.stock.read_bytes(), self.source.read_bytes())
        self.assertFalse(result['deployed'])
        self.assertEqual((Path(result['backup']) / 'previous-boot.img').read_bytes(), self.before[0])

    def test_config_commit_failure_restores_base_and_latest(self):
        copy = module.atomic_copy

        def fail_config(source, target):
            if source.name == 'new-config.json' and target == self.config:
                raise OSError('config commit failed')
            return copy(source, target)

        with mock.patch.object(module, 'build_candidate', side_effect=self.fake_build), \
                mock.patch.object(module, 'atomic_copy', side_effect=fail_config):
            with self.assertRaisesRegex(OSError, 'config commit failed'):
                self.replace()
        self.assert_original()

    def test_existing_hash_mismatch_refuses_replacement(self):
        self.stock.write_bytes(boot_image(4))
        with self.assertRaisesRegex(ValueError, 'Existing Android base differs'):
            self.replace()
        self.assertEqual(self.config.read_bytes(), self.before[1])


if __name__ == '__main__':
    unittest.main()
