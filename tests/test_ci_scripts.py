"""Check build-script sequencing that cannot be exercised on the host."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConfigureRootfsTests(unittest.TestCase):
    def test_local_repository_is_configured_after_pacman_transactions(self):
        script = (ROOT / 'scripts/ci/configure-rootfs.sh').read_text()
        self.assertGreater(
            script.index('[tb322fc]'),
            script.rindex('pacman -Scc --noconfirm'),
        )


if __name__ == '__main__':
    unittest.main()
