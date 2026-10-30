"""Exercise bounded crash capture and MTP controller selection on private fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'sources/freedom/system_files'


@unittest.skipUnless(UPSTREAM.exists(), 'Fetch the pinned Freedom source first')
class FreedomUserspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.env = dict(os.environ)
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        (self.bin / 'logger').write_text('#!/bin/sh\nexit 0\n')
        (self.bin / 'logger').chmod(0o755)
        self.env['PATH'] = str(self.bin) + ':' + self.env['PATH']

    def prepare(self, package, files, patch):
        for name, source in files.items():
            shutil.copyfile(UPSTREAM / source, self.work / name)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(ROOT / 'packages' / package / patch)],
                       cwd=self.work, check=True, stdout=subprocess.DEVNULL)

    def diagnostics(self):
        self.prepare('freedom-diagnostics', {
            'save-devcoredump': 'usr/libexec/armada/save-devcoredump',
            '40-armada-wake-ledger': 'usr/lib/systemd/system-sleep/40-armada-wake-ledger',
            'armada_sleep_debug.py': 'usr/lib/armada/armada_sleep_debug.py',
        }, 'bounded-capture.patch')
        self.cores = self.work / 'cores'
        self.out = self.work / 'saved'
        self.env.update(ARMADA_DEVCOREDUMP_CLASS_ROOT=str(self.cores), ARMADA_DEVCOREDUMP_DIR=str(self.out),
                        ARMADA_DEVCOREDUMP_MAX_BYTES='64', ARMADA_DEVCOREDUMP_MAX_FILES='2',
                        ARMADA_DEVCOREDUMP_TOTAL_BYTES='80')

    def capture(self, number, payload):
        device = self.cores / ('devcd' + str(number))
        device.mkdir(parents=True)
        (device / 'data').write_bytes(payload)
        subprocess.run(['bash', str(self.work / 'save-devcoredump'), device.name], env=self.env, check=True)

    def test_large_dump_is_explicitly_truncated_and_private(self):
        self.diagnostics()
        self.capture(1, b'x' * 100)
        dumps = list(self.out.glob('*.devcore'))
        self.assertEqual(len(dumps), 1)
        self.assertIn('.truncated.', dumps[0].name)
        self.assertEqual(dumps[0].read_bytes(), b'x' * 64)
        self.assertEqual(dumps[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.out.glob('*.part')))

    def test_dump_history_honors_count_and_bytes(self):
        self.diagnostics()
        for i in range(4):
            self.capture(i, bytes([i]) * 30)
        dumps = sorted(self.out.glob('*.devcore'))
        self.assertEqual(len(dumps), 2)
        self.assertLessEqual(sum(p.stat().st_size for p in dumps), 80)
        self.assertEqual({p.read_bytes()[0] for p in dumps}, {2, 3})
        self.capture(5, b'z' * 100)
        self.assertLessEqual(sum(p.stat().st_size for p in self.out.glob('*.devcore')), 80)

    def test_empty_dump_is_not_saved(self):
        self.diagnostics()
        self.capture(0, b'')
        self.assertFalse(list(self.out.glob('*.devcore')))

    def test_dump_device_path_traversal_is_rejected(self):
        self.diagnostics()
        result = subprocess.run(['bash', str(self.work / 'save-devcoredump'), '../data'], env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.out.exists())

    def test_wake_ledger_is_bounded_and_records_irq(self):
        self.diagnostics()
        irq = self.work / 'irq'
        irq.write_text('42\n')
        interrupts = self.work / 'interrupts'
        interrupts.write_text('42: 1 0 GIC pmic_pwrkey\n')
        ledger = self.work / 'wake-ledger.log'
        ledger.write_text('old\n' * 500)
        self.env.update(ARMADA_WAKE_LEDGER=str(ledger), ARMADA_WAKE_IRQ=str(irq), ARMADA_INTERRUPTS=str(interrupts))
        subprocess.run(['bash', str(self.work / '40-armada-wake-ledger'), 'post', 'suspend'], env=self.env, check=True)
        lines = ledger.read_text().splitlines()
        self.assertLessEqual(len(lines), 500)
        self.assertIn('wake_irq=42 (pmic_pwrkey) mode=suspend', lines[-1])

    def mtp(self):
        self.prepare('freedom-mtp', {
            'mtp-gadget': 'usr/libexec/armada/mtp-gadget',
            'storage-lib': 'usr/lib/armada/storage-lib',
            'armada-mtp.service': 'usr/lib/systemd/system/armada-mtp.service',
        }, 'arch-session-and-usb.patch')
        self.udc = self.work / 'udc'
        self.udc.mkdir()
        self.configfs = self.work / 'configfs'
        (self.configfs / 'armada-mtp').mkdir(parents=True)
        self.bound = self.configfs / 'armada-mtp/UDC'
        self.bound.write_text('')
        self.env.update(ARMADA_MTP_CONFIGFS_ROOT=str(self.configfs), ARMADA_MTP_UDC_CLASS=str(self.udc),
                        ARMADA_MTP_RUNTIME=str(self.work / 'run'), ARMADA_STORAGE_LIB=str(self.work / 'storage-lib'))

    def bind(self):
        return subprocess.run(['bash', str(self.work / 'mtp-gadget'), 'bind'], env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_mtp_does_not_bind_without_a_device_controller(self):
        self.mtp()
        self.assertNotEqual(self.bind().returncode, 0)
        self.assertEqual(self.bound.read_text(), '')

    def test_mtp_refuses_ambiguous_controller_selection(self):
        self.mtp()
        (self.udc / 'one').mkdir()
        (self.udc / 'two').mkdir()
        self.assertNotEqual(self.bind().returncode, 0)
        self.assertEqual(self.bound.read_text(), '')

    def test_mtp_binds_existing_controller_without_role_override(self):
        self.mtp()
        (self.udc / 'a600000.usb').mkdir()
        result = self.bind()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.bound.read_text(), 'a600000.usb')
        self.assertFalse((self.work / 'run/previous-role').exists())


if __name__ == '__main__':
    unittest.main()
