"""Check first-publication behavior with real Arch database tooling."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"tb322fc.db", "tb322fc.db.tar.gz", "tb322fc.files", "tb322fc.files.tar.gz"}


@unittest.skipUnless(shutil.which("repo-add"), "Arch repo-add is required")
class RepositoryInitialization(unittest.TestCase):
    def invoke(self, mode, tag="repository-freedom-v2"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "bin").mkdir()
        (root / "assets").mkdir()
        (root / "release.json").write_text(json.dumps({
            "isDraft": False,
            "assets": [{"name": name} for name in sorted(ASSETS)],
        }))
        gh = root / "bin/gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
root = pathlib.Path(os.environ['MOCK_REPO'])
args = sys.argv[1:]
with (root / 'calls').open('a') as f: f.write(json.dumps(args) + '\\n')
if args[:2] == ['release', 'view']:
    mode = os.environ['MOCK_MODE']
    if mode == 'absent':
        print('release not found', file=sys.stderr); sys.exit(1)
    if mode == 'unauthorized':
        print('HTTP 401: Bad credentials', file=sys.stderr); sys.exit(1)
    release = json.loads((root / 'release.json').read_text())
    if mode == 'incomplete': release['assets'] = []
    print(json.dumps(release))
elif args[:2] == ['release', 'create']:
    for arg in args:
        path = pathlib.Path(arg)
        if path.is_file() and path.name.startswith('tb322fc.'):
            shutil.copyfile(path, root / 'assets' / path.name)
elif args[:2] != ['release', 'edit']:
    raise SystemExit('Unexpected mutation: ' + repr(args))
""")
        gh.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "scripts/ci/init-repo.sh")],
                                env=dict(os.environ, PATH=str(root / "bin") + ":" + os.environ["PATH"],
                                         MOCK_REPO=str(root), MOCK_MODE=mode, REPO_TAG=tag),
                                text=True, capture_output=True)
        calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()] if (root / "calls").exists() else []
        return root, result, calls

    def test_first_release_contains_four_valid_empty_databases(self):
        root, result, calls = self.invoke("absent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name for p in (root / "assets").iterdir()}, ASSETS)
        for name in ASSETS:
            with tarfile.open(root / "assets" / name) as archive:
                self.assertEqual(archive.getnames(), [])
        self.assertEqual((root / "assets/tb322fc.db").read_bytes(), (root / "assets/tb322fc.db.tar.gz").read_bytes())
        if shutil.which("pacman"):
            database = root / "database"
            (database / "sync").mkdir(parents=True)
            shutil.copyfile(root / "assets/tb322fc.db", database / "sync/tb322fc.db")
            config = root / "pacman.conf"
            config.write_text("[options]\nArchitecture = aarch64\n[tb322fc]\nSigLevel = Optional TrustAll\nServer = https://example.invalid\n")
            query = subprocess.run(["pacman", "--config", str(config), "--dbpath", str(database),
                                    "-Sl", "tb322fc"], text=True, capture_output=True)
            self.assertEqual(query.returncode, 0, query.stderr)
            self.assertEqual(query.stdout, "")
        self.assertIn("--draft", calls[1])
        self.assertEqual(calls[-1][:2], ["release", "edit"])
        self.assertIn("--draft=false", calls[-1])

    def test_existing_repository_is_never_reinitialized(self):
        _, result, calls = self.invoke("existing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)

    def test_incomplete_release_or_auth_failure_is_not_overwritten(self):
        for mode in ["incomplete", "unauthorized"]:
            with self.subTest(mode=mode):
                _, result, calls = self.invoke(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 1)

    def test_legacy_repository_is_rejected_without_remote_calls(self):
        _, result, calls = self.invoke("absent", tag="repository")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
