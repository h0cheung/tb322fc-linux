import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release", ROOT / "packages/gamescope-session-steam/freedom_release.py"
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def manifest():
    return dict(
        format=r.FORMAT,
        tag="freedom-v2-20261024000000",
        arch="aarch64",
        device="lenovo,elden",
        kernel_release="7.2.6-1-freedom",
        kernel_build_id="a" * 40,
        repository_tag=r.REPO_TAG,
        packages=[
            dict(
                name=n,
                version="7.2.6-1" if n.startswith("linux-freedom") else "20261024-1",
                file=n + "-test-aarch64.pkg.tar.zst",
                bytes=1,
                sha256=hashlib.sha256(b"x").hexdigest(),
            )
            for n in sorted(r.REQUIRED)
        ],
    )


class ReleaseContract(unittest.TestCase):
    def test_complete_matching_kernel_set_is_accepted(self):
        r.validate_manifest(manifest())

    def test_missing_boot_companion_is_rejected(self):
        for name in r.REQUIRED:
            d = manifest()
            d["packages"] = [p for p in d["packages"] if p["name"] != name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                r.validate_manifest(d)

    def test_wrong_headers_and_legacy_repository_are_rejected(self):
        d = manifest()
        next(p for p in d["packages"] if p["name"] == "linux-freedom-headers")[
            "version"
        ] = "7.2.7-1"
        with self.assertRaises(ValueError):
            r.validate_manifest(d)
        d = manifest()
        d["repository_tag"] = "repository"
        with self.assertRaises(ValueError):
            r.validate_manifest(d)

    def test_corrupt_download_is_rejected_before_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = manifest()
            for p in d["packages"]:
                (Path(tmp) / p["file"]).write_bytes(b"x")
            r.verify_downloads(d, tmp)
            (Path(tmp) / d["packages"][0]["file"]).write_bytes(b"y")
            with self.assertRaises(ValueError):
                r.verify_downloads(d, tmp)

    def test_path_traversal_package_is_rejected(self):
        d = manifest()
        d["packages"][0]["file"] = "../boot_a"
        with self.assertRaises(ValueError):
            r.validate_manifest(d)

    def test_old_success_report_cannot_mask_failed_same_version_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "boot"
            p.write_bytes(b"old boot")
            d = manifest()
            report = json.dumps(
                dict(
                    deployed=True,
                    release=d["kernel_release"],
                    kernel_build_id=d["kernel_build_id"],
                    sha256=r.sha256(p),
                    image="old",
                )
            ).encode()
            with self.assertRaises(ValueError):
                r.verify_deployment(
                    d, report, report, p, {"build_id": d["kernel_build_id"]}
                )
            fresh = json.dumps(
                dict(
                    deployed=True,
                    release=d["kernel_release"],
                    kernel_build_id=d["kernel_build_id"],
                    sha256=r.sha256(p),
                    image="new candidate",
                )
            ).encode()
            r.verify_deployment(d, report, fresh, p, {"build_id": d["kernel_build_id"]})
            with self.assertRaises(ValueError):
                r.verify_deployment(d, report, fresh, p, {"build_id": "b" * 40})

    @unittest.skipUnless(
        os.geteuid() == 0 and shutil.which("jq"),
        "Legacy shell fixture requires root and jq",
    )
    def test_real_legacy_updater_does_not_flash_new_releases(self):
        for tag in ["freedom-v2-20261024000000", "v20261024000000"]:
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                bin = t / "bin"
                bin.mkdir()
                calls = t / "calls"
                data = [
                    dict(
                        tag_name=tag,
                        assets=[
                            dict(
                                name="freedom-release.json",
                                browser_download_url="https://example.invalid/manifest",
                            ),
                            dict(
                                name="kshim-freedom-test.pkg.tar.zst",
                                browser_download_url="https://example.invalid/kshim",
                            ),
                        ],
                    )
                ]
                (t / "response").write_text(json.dumps(data))
                (bin / "curl").write_text('#!/bin/sh\ncat "$MOCK_RESPONSE"\n')
                (bin / "pacman").write_text(
                    '#!/bin/sh\necho "pacman $*" >> "$MOCK_CALLS"\nexit 0\n'
                )
                for tool in ["dd", "tar", "zstd", "depmod"]:
                    (bin / tool).write_text(
                        '#!/bin/sh\necho "UNSAFE '
                        + tool
                        + ' $*" >> "$MOCK_CALLS"\nexit 99\n'
                    )
                for p in bin.iterdir():
                    p.chmod(0o755)
                script = (ROOT / "tests/fixtures/legacy-tb322fc-update").read_text()
                script = script.replace(
                    "/run/lock/tb322fc-update.lock", str(t / "lock")
                ).replace("/var/lib/tb322fc", str(t / "state"))
                fixture = t / "legacy"
                fixture.write_text(script)
                env = dict(
                    os.environ,
                    PATH=str(bin) + ":" + os.environ["PATH"],
                    MOCK_RESPONSE=str(t / "response"),
                    MOCK_CALLS=str(calls),
                )
                result = subprocess.run(
                    ["bash", str(fixture)], env=env, text=True, capture_output=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("already up to date", result.stderr)
                log = calls.read_text() if calls.exists() else ""
                self.assertNotIn("UNSAFE", log)
                self.assertNotIn("pacman -Syu", log)

    def test_publisher_refuses_the_legacy_repository(self):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/ci/publish-repo.sh")],
            env=dict(os.environ, REPO_TAG="repository"),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to replace the legacy", result.stderr)


if __name__ == "__main__":
    unittest.main()
