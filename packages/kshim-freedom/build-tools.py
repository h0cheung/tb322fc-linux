#!/usr/bin/env python3
"""Build native ARM64 kShim binaries from pinned upstream sources, never flash."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--source", type=Path, required=True)
p.add_argument("--crdk-archive", type=Path, required=True)
p.add_argument("--jobs", type=int, default=4)
a = p.parse_args()
if platform.machine() != "aarch64" or a.jobs < 1:
    p.error("A native AArch64 host and a positive job count are required")
s = a.source.resolve()
f = s / "armadaos-freedom"
w = s / "native-tools"
if w.exists():
    shutil.rmtree(w)
w.mkdir()
k = w / "kshim"
shutil.copytree(
    f / "devices/lenovo-tb323fu/boot/kshim-success-source", k, symlinks=True
)
for name, target, sub in [
    ("CrDK", "lib/CrDK", ""),
    ("picolibc", "lib/picolibc", ""),
    ("lvgl", "third_party/lvgl", ""),
    ("libfdt", "lib/libfdt", "lib/libfdt"),
]:
    dst = k / target
    if dst.exists():
        shutil.rmtree(dst)
    source = s / name / sub
    if name == "CrDK":
        dst.mkdir(parents=True)
        continue
    shutil.copytree(source, dst, symlinks=True, ignore=shutil.ignore_patterns(".git"))
for patch in [
    "neutral-linux-menu-labels.patch",
    "native-aarch64-toolchain.patch",
    "crdk-pinned-archive.patch",
    "libfdt-stdlib-include.patch",
]:
    subprocess.run(
        ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(s / patch)], cwd=k, check=True
    )
b = w / "runtime"
b.mkdir()
shutil.copyfile(k / "configs/tb322fc_android_defconfig", b / ".config")
freestanding_env = dict(os.environ)
for variable in ("CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS"):
    freestanding_env.pop(variable, None)
subprocess.run(
    [
        "cmake",
        "-S",
        str(k),
        "-B",
        str(b),
        "-G",
        "Ninja",
        "-DKSHIM_STANDALONE=OFF",
        "-DKSHIM_RUNTIME_SLOT_SIZE=0x400000",
        "-DKSHIM_UEFI_PAYLOAD=",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_FLAGS=-fno-stack-protector",
        "-DKSHIM_CRDK_SOURCE_ARCHIVE=" + str(a.crdk_archive.resolve()),
    ],
    env=freestanding_env,
    check=True,
)
subprocess.run(["cmake", "--build", str(b), "--parallel", str(a.jobs)], check=True)
assert (b / "kShimC.bin").stat().st_size == 0x400000
assert not subprocess.check_output(["nm", "-u", str(b / "kShimC.elf")]).strip()
pb = w / "packer"
subprocess.run(
    [
        "cmake",
        "-S",
        str(f / "packages/kshim-tools/vendor/packer"),
        "-B",
        str(pb),
        "-DBUILD_SHIMS=OFF",
        "-DCMAKE_BUILD_TYPE=Release",
    ],
    check=True,
)
subprocess.run(["cmake", "--build", str(pb), "--parallel", str(a.jobs)], check=True)
bb = w / "busybox"
bb.mkdir()
shutil.copyfile(s / "busybox.config", bb / ".config")
cmd = ["make", "-C", str(s / "busybox-1.36.1"), "O=" + str(bb), "ARCH=arm64"]
subprocess.run(cmd + ["oldconfig"], stdin=subprocess.DEVNULL, check=True)
subprocess.run(cmd + ["-j" + str(a.jobs), "busybox"], check=True)
out = s / "kshim-tools"
if out.exists():
    shutil.rmtree(out)
out.mkdir()
for src, name in [
    (b / "kShimC.bin", "kShimC.bin"),
    (pb / "MultiBootKernelPatcher", "MultiBootKernelPatcher"),
    (pb / "UnpackTool", "UnpackTool"),
    (bb / "busybox", "busybox"),
    (f / "packages/kshim-tools/vendor/repack_boot_v4.py", "repack_boot_v4.py"),
    (f / "packages/kshim-tools/vendor/avbtool.py", "avbtool.py"),
]:
    shutil.copy2(src, out / name)
    if name in ["MultiBootKernelPatcher", "UnpackTool", "busybox"]:
        machine = subprocess.check_output(["readelf", "-h", str(out / name)], text=True)
        assert "AArch64" in machine, name
for test in ["payload_from", "payload_from_nonbase", "dtb_alignment"]:
    subprocess.run(
        [
            "python",
            str(f / "packages/kshim-tools/vendor/packer/tests" / f"{test}.py"),
            "--packer",
            str(out / "MultiBootKernelPatcher"),
            "--unpacker",
            str(out / "UnpackTool"),
            "--out",
            str(w / "tests" / test),
        ],
        check=True,
    )
(out / "bundle-manifest.json").write_text(
    json.dumps(
        {
            "native_aarch64": True,
            "hashes": {
                x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                for x in out.iterdir()
                if x.is_file()
            },
        },
        indent=2,
    )
    + "\n"
)
