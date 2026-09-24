#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build a direct Android boot image and matching Arch Linux ARM modules.
set -euo pipefail
PROJECT=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$PROJECT"

for program in make depmod tar gzip sha256sum llvm-strip; do
    command -v "$program" >/dev/null || { echo "Missing host tool: $program" >&2; exit 1; }
done
[[ -f sources/kernel/Makefile ]] || {
    echo "Fetch the pinned kernel with scripts/fetch-sources.py first." >&2
    exit 1
}

export JOBS=${JOBS:-$(nproc)}
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "JOBS must be a positive integer." >&2; exit 2; }
# Use the upstream commit date for repeatable archives and compiler metadata.
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C sources/kernel show -s --format=%ct HEAD)}
export KBUILD_BUILD_TIMESTAMP=${KBUILD_BUILD_TIMESTAMP:-$(date -u -d "@$SOURCE_DATE_EPOCH" '+%Y-%m-%d %H:%M:%S UTC')}
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-builder}
export KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-tb322fc-ci}
export KBUILD_BUILD_VERSION=1

# These directories contain only generated output. A clean object tree avoids
# stale modules or configuration surviving a rerun with a different source pin.
rm -rf -- build/kernel build/busybox build/kernel-modules
mkdir -p artifacts
rm -f -- artifacts/boot.img artifacts/Image artifacts/sm8750-lenovo-elden.dtb \
    artifacts/kernel.config artifacts/kernel.release artifacts/kernel-modules.tar.gz \
    artifacts/kernel-modules.tar.gz.part artifacts/SHA256SUMS

# Keep the original firmware checks, config, embedded DTB/initramfs and v4
# Android image layout. This works on native arm64 and cross-build hosts.
bash scripts/build-boot.sh

# Inspect the real generated container before publishing it. Header v4 uses
# fixed 4096-byte pages; its kernel payload must be our uncompressed ARM64 Image.
python3 - <<'PY'
import hashlib
from pathlib import Path
import struct

image = Path('artifacts/Image')
with image.open('rb') as stream:
    if stream.read(64)[56:60] != b'ARM\x64':
        raise SystemExit('Image lacks the ARM64 Linux image magic')
    stream.seek(0)
    expected = hashlib.file_digest(stream, 'sha256').digest()
with Path('artifacts/boot.img').open('rb') as stream:
    header = stream.read(1584)
    if len(header) != 1584 or header[:8] != b'ANDROID!':
        raise SystemExit('boot.img has an invalid Android header')
    kernel_size, ramdisk_size = struct.unpack_from('<II', header, 8)
    header_size = struct.unpack_from('<I', header, 20)[0]
    version = struct.unpack_from('<I', header, 40)[0]
    if version != 4 or header_size != 1584 or ramdisk_size != 0:
        raise SystemExit('boot.img must use Android v4 with an empty external ramdisk')
    if kernel_size != image.stat().st_size:
        raise SystemExit('boot.img kernel size differs from Image')
    stream.seek(4096)
    digest = hashlib.sha256()
    remaining = kernel_size
    while remaining:
        chunk = stream.read(min(remaining, 1024 * 1024))
        if not chunk:
            raise SystemExit('boot.img kernel payload is truncated')
        digest.update(chunk)
        remaining -= len(chunk)
    if digest.digest() != expected:
        raise SystemExit('boot.img kernel payload differs from Image')
print('Verified Android v4 boot.img, empty external ramdisk and ARM64 Image payload.')
PY

kernel_make=(make -C sources/kernel O="$PROJECT/build/kernel" ARCH=arm64 LLVM=1)
"${kernel_make[@]}" -j"$JOBS" modules
release=$("${kernel_make[@]}" --no-print-directory -s kernelrelease)
[[ "$release" =~ ^[A-Za-z0-9._+-]+$ ]] || { echo "Invalid kernel release: $release" >&2; exit 1; }
printf '%s\n' "$release" > artifacts/kernel.release

stage="$PROJECT/build/kernel-modules"
mkdir -p "$stage"
trap 'rm -rf -- "$stage"' EXIT
# Strip debug data from installed modules, but retain the tested kernel config.
# Run depmod ourselves before converting the conventional /lib to Arch's /usr/lib.
"${kernel_make[@]}" INSTALL_MOD_PATH="$stage" INSTALL_MOD_STRIP=1 \
    DEPMOD=true modules_install
for link in build source; do
    path="$stage/lib/modules/$release/$link"
    [[ ! -L "$path" ]] || rm -- "$path"
done
depmod -b "$stage" "$release"
mkdir -p "$stage/usr"
mv "$stage/lib" "$stage/usr/lib"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
    -C "$stage" -cf - usr | gzip -n > artifacts/kernel-modules.tar.gz.part
mv artifacts/kernel-modules.tar.gz.part artifacts/kernel-modules.tar.gz

(
    cd artifacts
    sha256sum boot.img Image sm8750-lenovo-elden.dtb kernel.config \
        kernel.release kernel-modules.tar.gz > SHA256SUMS
)
echo "Built boot.img and matching kernel $release modules."
echo "Kernel object trees under build/kernel and build/busybox may now be removed."
