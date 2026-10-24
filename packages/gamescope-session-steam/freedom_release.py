"""Shared contract for the v2 package publisher and updater."""

import hashlib
from pathlib import Path
import re

FORMAT = "tb322fc-freedom-packages-v2"
TAG_PREFIX = "freedom-v2-"
REPO_TAG = "repository-freedom-v2"
REQUIRED = {
    "linux-freedom",
    "linux-freedom-headers",
    "als-bridge-dkms",
    "kshim-freedom",
}
LEGACY_ASSETS = {"boot.img.zst", "kernel-modules.tar.gz"}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_manifest(data):
    if (
        data.get("format") != FORMAT
        or data.get("arch") != "aarch64"
        or data.get("device") != "lenovo,elden"
    ):
        raise ValueError("Unsupported release format, architecture or device")
    if not re.fullmatch(r"freedom-v2-[0-9]{14}", data.get("tag", "")):
        raise ValueError("Invalid v2 release tag")
    if data.get("repository_tag") != REPO_TAG:
        raise ValueError("Legacy and v2 package repositories must stay separate")
    if not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+-[0-9]+-freedom", data.get("kernel_release", "")
    ):
        raise ValueError("Invalid kernel release")
    if not re.fullmatch(r"[0-9a-f]{40,64}", data.get("kernel_build_id", "")):
        raise ValueError("Missing kernel build ID")
    packages = data.get("packages", [])
    if len(packages) != 4 or {p.get("name") for p in packages} != REQUIRED:
        raise ValueError(
            "A release must contain kernel, headers, ALS DKMS and kShim together"
        )
    versions = {}
    for p in packages:
        f = p.get("file", "")
        if (
            Path(f).name != f
            or "/" in f
            or not f.startswith(p["name"] + "-")
            or not f.endswith((".pkg.tar.zst", ".pkg.tar.xz"))
        ):
            raise ValueError("Invalid package filename")
        if not re.fullmatch(r"[0-9a-f]{64}", p.get("sha256", "")) or not (
            0 < p.get("bytes", 0) < 2_000_000_000
        ):
            raise ValueError("Invalid package hash/size")
        if not re.fullmatch(r"[0-9A-Za-z_.:+~-]+", p.get("version", "")):
            raise ValueError("Invalid package version")
        versions[p["name"]] = p["version"]
    if versions["linux-freedom"] != versions["linux-freedom-headers"]:
        raise ValueError("Kernel and headers versions differ")
    if data["kernel_release"] != versions["linux-freedom"].split(":")[-1] + "-freedom":
        raise ValueError("Kernel package version and release differ")
    return data


def verify_downloads(data, directory):
    validate_manifest(data)
    files = []
    for p in data["packages"]:
        f = Path(directory) / p["file"]
        if f.is_symlink() or f.stat().st_size != p["bytes"] or sha256(f) != p["sha256"]:
            raise ValueError("Package checksum/size mismatch: " + p["name"])
        files.append(f)
    return files


def verify_deployment(
    data, previous_report, current_report, boot_path, kernel_metadata
):
    import json

    if previous_report == current_report:
        raise ValueError("No fresh successful boot deployment was recorded")
    report = json.loads(current_report)
    if not report.get("deployed") or report.get("release") != data["kernel_release"]:
        raise ValueError("Matching kernel boot image was not deployed")
    if (
        report.get("kernel_build_id") != data["kernel_build_id"]
        or kernel_metadata.get("build_id") != data["kernel_build_id"]
    ):
        raise ValueError("Kernel build IDs do not match the published release")
    if report.get("sha256") != sha256(boot_path):
        raise ValueError("Deployed boot readback differs from the successful report")
