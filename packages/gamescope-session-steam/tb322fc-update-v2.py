#!/usr/bin/env python3
"""Install one complete v2 kernel set; restore the running boot on any failure."""

import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import urllib.request
from freedom_release import (
    REQUIRED,
    REPO_TAG,
    TAG_PREFIX,
    sha256,
    validate_manifest,
    verify_downloads,
    verify_deployment,
)

API = "https://api.github.com/repos/h0cheung/tb322fc-linux/releases"
CONFIG = Path("/etc/kshim-freedom/config.json")
STATE = Path("/var/lib/tb322fc-updates")
BOOT = Path("/dev/disk/by-partlabel/boot_a")


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def fetch_json(url):
    if not url.startswith("https://"):
        raise ValueError("HTTPS is required")
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_release():
    for release in fetch_json(API):
        if release.get("draft") or not release.get("tag_name", "").startswith(
            TAG_PREFIX
        ):
            continue
        assets = {
            x["name"]: x["browser_download_url"] for x in release.get("assets", [])
        }
        if "freedom-release.json" not in assets:
            continue
        data = validate_manifest(fetch_json(assets["freedom-release.json"]))
        if data["tag"] != release["tag_name"]:
            raise ValueError("Release tag does not match manifest")
        if not all(p["file"] in assets for p in data["packages"]):
            raise ValueError("Release package asset is missing")
        return data, assets
    return None, None


def preflight():
    if not CONFIG.is_file():
        raise RuntimeError(
            "Freedom boot is not initialized; automatic migration is disabled"
        )
    config = json.loads(CONFIG.read_text())
    if b"lenovo,elden" not in Path(
        "/sys/firmware/devicetree/base/compatible"
    ).read_bytes().split(b"\0"):
        raise RuntimeError("Unsupported device")
    release = os.uname().release
    modules = Path("/usr/lib/modules") / release
    if (
        not (modules / "pkgbase").is_file()
        or (modules / "pkgbase").read_text().strip() != "linux-freedom"
    ):
        raise RuntimeError(
            "Boot the initialized packaged Freedom kernel before using this updater"
        )
    run(["pacman", "-Q", *sorted(REQUIRED)], stdout=subprocess.DEVNULL)
    installed = run(
        ["pacman", "-Q", "linux-freedom"], capture_output=True, text=True
    ).stdout.split()[1]
    if installed.split(":")[-1] + "-freedom" != release:
        raise RuntimeError("Reboot into the installed kernel before updating again")
    if not config.get("deploy_boot_a"):
        raise RuntimeError("Automatic boot_a deployment is not enabled")
    root = Path("/dev/disk/by-partuuid") / config["root_partuuid"]
    actual = run(
        ["findmnt", "-no", "SOURCE", "/"], capture_output=True, text=True
    ).stdout.strip()
    if root.resolve() != Path(actual).resolve():
        raise RuntimeError("Root PARTUUID differs from boot configuration")
    if (
        not BOOT.is_block_device()
        or int(
            run(
                ["blockdev", "--getsize64", BOOT], capture_output=True, text=True
            ).stdout
        )
        != 100663296
    ):
        raise RuntimeError("Unexpected boot_a target")
    if sha256(config["stock_boot"]) != config["stock_boot_sha256"]:
        raise RuntimeError("Stock template hash differs")
    key = Path(config["avb_key"])
    if not key.is_file() or key.stat().st_mode & 0o077:
        raise RuntimeError("AVB private key is missing or has unsafe permissions")
    for name in config["early_firmware"]:
        p = Path("/usr/lib/firmware") / name
        if not any(Path(str(p) + suffix).is_file() for suffix in ["", ".zst", ".xz"]):
            raise RuntimeError("Missing early firmware: " + name)
    return config, release


def backup(directory, release):
    image = directory / "boot_a-before.img"
    with BOOT.open("rb") as src, image.open("xb") as dst:
        shutil.copyfileobj(src, dst)
        dst.flush()
        os.fsync(dst.fileno())
    if sha256(image) != sha256(BOOT):
        raise RuntimeError("Boot backup verification failed")
    archive = directory / "modules-before.tar.zst"
    run(
        [
            "tar",
            "--zstd",
            "--exclude=" + release + "/build",
            "-cf",
            archive,
            "-C",
            "/usr/lib/modules",
            release,
        ]
    )
    result = {
        "release": release,
        "boot_sha256": sha256(image),
        "modules_sha256": sha256(archive),
    }
    (directory / "backup.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def restore(directory, record):
    image = directory / "boot_a-before.img"
    archive = directory / "modules-before.tar.zst"
    if (
        sha256(image) != record["boot_sha256"]
        or sha256(archive) != record["modules_sha256"]
    ):
        raise RuntimeError("Rollback archive is corrupt")
    # Restore the old module directory even if pacman has committed a new package.
    run(["tar", "--zstd", "-xf", archive, "-C", "/usr/lib/modules"])
    run(["depmod", "-a", record["release"]])
    parent = (
        Path("/dev")
        / run(
            ["lsblk", "-ndo", "PKNAME", BOOT.resolve()], capture_output=True, text=True
        ).stdout.strip()
    )
    if not parent.is_block_device():
        raise RuntimeError("Missing boot partition parent")
    devices = [parent, BOOT]
    readonly = {
        str(p): int(
            run(["blockdev", "--getro", p], capture_output=True, text=True).stdout
        )
        for p in devices
    }
    try:
        for p in devices:
            run(["blockdev", "--setrw", p])
        with image.open("rb") as src, BOOT.open("r+b", buffering=0) as dst:
            while chunk := src.read(4 * 1024 * 1024):
                if dst.write(chunk) != len(chunk):
                    raise OSError("Short rollback write")
            os.fsync(dst.fileno())
        if sha256(BOOT) != record["boot_sha256"]:
            raise RuntimeError("Boot rollback readback failed")
    finally:
        for p in reversed(devices):
            run(["blockdev", "--setro" if readonly[str(p)] else "--setrw", p])


def package_info(path):
    info = {}
    for line in run(
        ["bsdtar", "-xOf", path, ".PKGINFO"], capture_output=True, text=True
    ).stdout.splitlines():
        if " = " in line:
            k, v = line.split(" = ", 1)
            info[k] = v
    return info


def transaction_config(directory):
    text = Path("/etc/pacman.conf").read_text()
    text = text.replace(
        "https://github.com/h0cheung/tb322fc-linux/releases/download/repository\n",
        "https://github.com/h0cheung/tb322fc-linux/releases/download/"
        + REPO_TAG
        + "\n",
    )
    block = (
        "\n[tb322fc-kernel-set]\nSigLevel = Optional TrustAll\nServer = file://"
        + str(directory)
        + "\n\n"
    )
    lines = text.splitlines(True)
    for i, line in enumerate(lines):
        if line.startswith("[") and line.strip() != "[options]":
            lines.insert(i, block)
            break
    else:
        lines.append(block)
    path = directory / "pacman.conf"
    path.write_text("".join(lines))
    return path


def apply(data, assets):
    config, release = preflight()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = STATE / datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    directory.mkdir(mode=0o700)
    # Package downloads are public and must be readable by pacman's downloader.
    downloads = Path("/var/cache/pacman/pkg") / data["tag"]
    downloads.mkdir(mode=0o755, exist_ok=True)
    for p in data["packages"]:
        url = assets[p["file"]]
        if not url.startswith("https://"):
            raise ValueError("Package download requires HTTPS")
        target = downloads / p["file"]
        with urllib.request.urlopen(url, timeout=60) as src, target.open("wb") as dst:
            remaining = p["bytes"]
            while chunk := src.read(min(1024 * 1024, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError("Package exceeds its declared size")
                dst.write(chunk)
        target.chmod(0o644)
    paths = verify_downloads(data, downloads)
    for p, path in zip(data["packages"], paths):
        info = package_info(path)
        if (info.get("pkgname"), info.get("pkgver")) != (
            p["name"],
            p["version"],
        ) or info.get("arch") not in ["aarch64", "any"]:
            raise ValueError("Downloaded package metadata differs from manifest")
    # Nothing above this point changes installed packages or boot bytes.
    record = backup(directory, release)
    report_path = Path("/var/lib/kshim-freedom/latest.json")
    previous_report = report_path.read_bytes() if report_path.exists() else b""
    run(["repo-add", downloads / "tb322fc-kernel-set.db.tar.gz", *paths])
    conf = transaction_config(downloads)
    try:
        print("45%", flush=True)
        run(
            [
                "pacman",
                "--config",
                conf,
                "-Syu",
                "--noconfirm",
                *["tb322fc-kernel-set/" + n for n in sorted(REQUIRED)],
            ]
        )
        metadata = json.loads(
            (
                Path("/usr/lib/modules")
                / data["kernel_release"]
                / "build-manifest.json"
            ).read_text()
        )
        verify_deployment(
            data, previous_report, report_path.read_bytes(), BOOT, metadata
        )
        for p in data["packages"]:
            version = run(
                ["pacman", "-Q", p["name"]], capture_output=True, text=True
            ).stdout.split()[1]
            if version != p["version"]:
                raise RuntimeError("Installed package differs from release")
    except BaseException:
        restore(directory, record)
        (directory / "failed-restored").touch()
        print(
            "Update failed; previous boot and modules restored. Package metadata may require repair.",
            file=sys.stderr,
        )
        raise
    # Persist the separate repository only after successful coordinated deployment.
    p = Path("/etc/pacman.conf")
    text = p.read_text()
    text = text.replace(
        "releases/download/repository\n", "releases/download/" + REPO_TAG + "\n"
    )
    p.write_text(text)
    (STATE / "installed-release").write_text(data["tag"] + "\n")
    (directory / "release.json").write_text(json.dumps(data, indent=2) + "\n")
    print("100%", flush=True)


def main():
    if "--supports-duplicate-detection" in sys.argv:
        return 0

    def interrupted(signum, frame):
        raise InterruptedError("Update interrupted by signal " + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    if os.geteuid() != 0:
        raise RuntimeError("Run through the privileged steamos-update wrapper")
    Path("/run/lock").mkdir(exist_ok=True)
    with Path("/run/lock/tb322fc-update.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Reject uninitialized/legacy layouts before querying packages or writing boot.
        preflight()
        data, assets = latest_release()
        if data is None:
            return 7
        installed = (
            (STATE / "installed-release").read_text().strip()
            if (STATE / "installed-release").exists()
            else ""
        )
        if installed == data["tag"]:
            return 7 if "check" in sys.argv else 0
        if "check" in sys.argv:
            print(data["tag"])
            return 0
        print("0%", flush=True)
        apply(data, assets)
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("tb322fc-update: " + str(error), file=sys.stderr)
        sys.exit(7)
