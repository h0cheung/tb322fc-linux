import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('FREEDOM_SOURCE', ROOT / 'sources/freedom'))
UPSTREAM = SOURCE / 'system_files/usr/libexec/armada/armada-control'


@unittest.skipUnless(UPSTREAM.exists(), 'Fetch the pinned Freedom source first')
class ControlCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.work.name)
        path = cls.directory / 'armada-control'
        path.write_bytes(UPSTREAM.read_bytes())
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', cls.directory,
                        '-i', ROOT / 'packages/armada-control/arch-control-compat.patch'], check=True, capture_output=True)
        sys.path[:0] = [str(ROOT/'packages/armada-control'), str(SOURCE/'system_files/usr/lib/armada')]
        loader = importlib.machinery.SourceFileLoader('control_compat_test', str(path))
        cls.control = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(cls.control)

    @classmethod
    def tearDownClass(cls):
        del sys.path[:2]
        cls.work.cleanup()

    def test_native_plasma_session_names_and_real_user_home(self):
        home = self.directory/'home';state = home/'.config/steamos-manager/state.toml'
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text('[session_manager]\ndesktop_session = "plasma-mobile.desktop"\n')
        with mock.patch.object(self.control.armada_session, 'session_home', return_value=home):
            self.assertEqual(self.control.get_desktop_mode(), 'mobile')
        with mock.patch.object(self.control, 'steamosctl') as command:
            self.control.set_desktop_mode('mobile')
            command.assert_called_once_with('set-default-desktop-session', 'plasma-mobile.desktop')

    def test_swipe_setting_is_persisted_when_steam_is_not_running(self):
        path = self.directory/'swipe.conf'
        inactive = subprocess.CompletedProcess([], 3)
        with mock.patch.object(self.control, 'SWIPE_GESTURES_CONFIG', path), \
             mock.patch.object(self.control, 'session_systemctl', return_value=inactive):
            result = self.control.ACTIONS['set_swipe_gestures_enabled']({'enabled': False})
            self.assertEqual(result, {'enabled': False})
            self.assertFalse(self.control.ACTIONS['get_swipe_gestures_enabled']({})['enabled'])

    def test_calibration_reload_restores_controller_type_after_restart(self):
        with mock.patch.object(self.control, 'unit_active', return_value=True), \
             mock.patch.object(self.control, 'run') as command:
            result = self.control.ACTIONS['reload_input_ranges']({})
            self.assertEqual(result, {'ok': True})
            self.assertEqual(command.call_args_list[0].args[0], ['/usr/bin/systemctl', 'restart', 'inputplumber.service'])
            self.assertEqual(command.call_args_list[1].args[0], ['/usr/bin/systemctl', 'start', 'armada-controller-type.service'])

    def test_swipe_rpc_rejects_non_boolean_values(self):
        for name, key in [('set_swipe_gestures_enabled', 'enabled'), ('suspend_swipe_gestures', 'suspended')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.control.ACTIONS[name]({key: 'false'})
