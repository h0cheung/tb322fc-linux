"""Exercise Steam input coordination without sending events to the real desktop."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'sources/freedom'


@unittest.skipUnless(UPSTREAM.exists(), 'Fetch the pinned Freedom source first')
class SteamPower(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        files = {
            'powerbuttond': 'system_files/usr/libexec/armada/powerbuttond',
            '50-armada-powerbutton-suspend': 'system_files/usr/lib/systemd/system-sleep/50-armada-powerbutton-suspend',
        }
        for name, source in files.items():
            shutil.copyfile(UPSTREAM / source, self.work / name)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(ROOT / 'packages/freedom-steam-power/arch-session-and-resume.patch')],
                       cwd=self.work, check=True, stdout=subprocess.DEVNULL)
        self.handler = self.work / 'powerbuttond'
        self.hook = self.work / '50-armada-powerbutton-suspend'

    def input_events(self, events, closed=False):
        output = self.work / 'steam-requests'
        script = '''source "$1"
log() { :; }
power_device() { printf '/dev/input/fake\\n'; }
armada_find_lid_dev() { return 1; }
armada_lid_closed() { return "$ARMADA_TEST_LID_OPEN"; }
steam_uri() { printf '%s\\n' "$1" >>"$ARMADA_TEST_REQUESTS"; }
powerbutton_screen_toggle() { printf 'display-toggle\\n' >>"$ARMADA_TEST_REQUESTS"; }
evtest() {
EVENTS
}
powerbutton_main
'''.replace('EVENTS', events)
        env = dict(os.environ, ARMADA_TEST_REQUESTS=str(output), ARMADA_TEST_LID_OPEN='0' if closed else '1',
                   ARMADA_POWERBUTTON_LONG_MS='30', ARMADA_POWERBUTTON_PID_FILE=str(self.work / 'pid'),
                   ARMADA_LID_CLOSE_MARKER=str(self.work / 'lid-marker'))
        result = subprocess.run(['bash', '-c', script, '_', str(self.handler)], env=env, timeout=5)
        self.assertEqual(result.returncode, 1)  # Fixture input intentionally ends.
        return output.read_text().splitlines() if output.exists() else []

    def test_short_press_toggles_display_once(self):
        requests = self.input_events("printf 'Event: (KEY_POWER), value 1\\nEvent: (KEY_POWER), value 0\\n'")
        self.assertEqual(requests, ['display-toggle'])

    def test_long_press_does_not_also_generate_short_press(self):
        requests = self.input_events("printf 'Event: (KEY_POWER), value 1\\n'; sleep .15; printf 'Event: (KEY_POWER), value 0\\n'")
        self.assertEqual(requests, ['longpowerpress'])

    def test_closed_lid_ignores_power_key(self):
        requests = self.input_events("printf 'Event: (KEY_POWER), value 1\\nEvent: (KEY_POWER), value 0\\n'", closed=True)
        self.assertEqual(requests, [])

    def hook_fixture(self, uid='1000', argv=None, pid='1234'):
        runtime = self.work / 'run'
        pidfile = runtime / '1000/armada-powerbuttond/pid'
        pidfile.parent.mkdir(parents=True)
        pidfile.write_text(pid + '\n')
        proc = self.work / 'proc/1234'
        proc.mkdir(parents=True)
        (proc / 'status').write_text('Uid:\t' + '\t'.join([uid] * 4) + '\n')
        (proc / 'cmdline').write_bytes(b'\0'.join(x.encode() for x in
            (argv or ['/bin/bash', '/usr/libexec/armada/powerbuttond'])) + b'\0')
        log = self.work / 'signals'
        bash_env = self.work / 'bash-env'
        bash_env.write_text('kill() { printf "%s\\n" "$*" >>"$ARMADA_TEST_SIGNAL_LOG"; }\n')
        self.hook_env = dict(os.environ, ARMADA_POWERBUTTON_USER_RUNTIME_ROOT=str(runtime),
                             ARMADA_POWERBUTTON_PROC_ROOT=str(proc.parent), BASH_ENV=str(bash_env),
                             ARMADA_TEST_SIGNAL_LOG=str(log))
        return log

    def run_hook(self, phase='post', mode='suspend'):
        subprocess.run(['bash', str(self.hook), phase, mode], env=self.hook_env, check=True)

    def test_listener_restart_only_runs_after_suspend(self):
        log = self.hook_fixture()
        self.run_hook('pre')
        self.run_hook(mode='hibernate')
        self.assertFalse(log.exists())
        self.run_hook()
        self.assertEqual(log.read_text().splitlines(), ['-USR1 1234'])

    def test_resume_does_not_signal_a_different_user(self):
        log = self.hook_fixture(uid='0')
        self.run_hook()
        self.assertFalse(log.exists())

    def test_resume_does_not_signal_a_different_command(self):
        log = self.hook_fixture(argv=['/bin/bash', '/tmp/other-script'])
        self.run_hook()
        self.assertFalse(log.exists())

    def test_resume_rejects_a_malformed_pid(self):
        log = self.hook_fixture(pid='1234; echo unexpected')
        self.run_hook()
        self.assertFalse(log.exists())

    def test_upstream_resume_and_process_cleanup(self):
        test = self.work / 'fixture/tests/powerbuttond-test.sh'
        test.parent.mkdir(parents=True)
        target = test.parents[1] / 'system_files/usr/libexec/armada/powerbuttond'
        target.parent.mkdir(parents=True)
        shutil.copyfile(self.handler, target)
        shutil.copyfile(UPSTREAM / 'tests/powerbuttond-test.sh', test)
        subprocess.run(['bash', str(test)], check=True, timeout=15, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
