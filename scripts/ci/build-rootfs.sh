#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Run as root on a native AArch64 host after build-kernel.sh and fetch-arch.sh.
set -euo pipefail
PROJECT=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$PROJECT"
die() { echo "build-rootfs: $*" >&2; exit 1; }
[[ $EUID == 0 ]] || die 'Run this script with sudo.'
[[ $(uname -m) == aarch64 ]] || die 'A native AArch64 host is required (ubuntu-24.04-arm in CI).'
: "${ARCH_ROOTFS_ARCHIVE:?Pass the archive authenticated by fetch-arch.sh}"
: "${ARCH_ROOTFS_SHA256:?Pass the authenticated archive SHA256}"
[[ $ARCH_ROOTFS_SHA256 =~ ^[[:xdigit:]]{64}$ ]] || die 'Invalid ARCH_ROOTFS_SHA256.'
ROOTFS_SIZE=${ROOTFS_SIZE:-12G}
JOBS=${JOBS:-$(nproc)}
[[ $ROOTFS_SIZE =~ ^[1-9][0-9]*[MG]$ ]] || die 'ROOTFS_SIZE must be an integer followed by M or G, for example 12G.'
[[ $JOBS =~ ^[1-9][0-9]*$ ]] || die 'JOBS must be a positive integer.'
export ROOTFS_SIZE JOBS
for program in unshare mount umount mountpoint tar git python3 chroot mke2fs e2fsck numfmt; do
    command -v "$program" >/dev/null || die "Missing host tool: $program"
done

# All mounts, including nested chroot mounts, are private to this process tree.
# Do not rbind or recursively unmount the host /dev: that can tear down the runner.
if [[ ${TB322FC_ROOTFS_NAMESPACE:-} != 1 ]]; then
    exec unshare --mount --propagation private env TB322FC_ROOTFS_NAMESPACE=1 bash "$0"
fi
printf '%s  %s\n' "$ARCH_ROOTFS_SHA256" "$ARCH_ROOTFS_ARCHIVE" | sha256sum --check --status - || die 'Arch archive checksum mismatch.'
[[ -s artifacts/kernel-modules.tar.gz && -s artifacts/kernel.release ]] || die 'Build the kernel and modules first.'
[[ ! -e artifacts/rootfs.img && ! -L artifacts/rootfs.img ]] || die 'artifacts/rootfs.img already exists; preserve or remove it explicitly.'
mkdir -p build artifacts
ROOTFS=$(mktemp -d "$PROJECT/build/rootfs.XXXXXXXX")
export PROJECT ROOTFS
mounts=()
cleanup() {
    local status=$? target
    trap - EXIT
    chroot "$ROOTFS" /usr/bin/gpgconf --homedir /etc/pacman.d/gnupg --kill all 2>/dev/null || true
    for (( index=${#mounts[@]}-1; index>=0; index-- )); do
        target=${mounts[index]}
        if ! umount "$target" 2>/dev/null && ! umount -l "$target" 2>/dev/null; then
            echo "Cannot unmount $target; retaining staging tree." >&2
            status=1
        fi
    done
    if (( status != 0 )); then
        echo "Rootfs build failed; staging tree retained at $ROOTFS" >&2
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

tar --numeric-owner --xattrs --acls -xpf "$ARCH_ROOTFS_ARCHIVE" -C "$ROOTFS"
chmod 755 "$ROOTFS"
[[ -x $ROOTFS/usr/bin/bash && -x $ROOTFS/usr/bin/pacman ]] || die 'Archive is not an Arch Linux ARM root filesystem.'
STAGE="$ROOTFS/root/tb322fc-build"
mkdir -p "$STAGE/sources" "$ROOTFS/usr/share/tb322fc"

# Only tracked, pinned source files are copied, never local build products.
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

project, rootfs = Path(os.environ['PROJECT']), Path(os.environ['ROOTFS'])
manifest = json.loads((project / 'sources.json').read_text())
for name in ('hexagonrpc', 'libssc', 'iio-sensor-proxy', 'libcamera'):
    source = project / 'sources' / name
    command = ['git', '-c', f'safe.directory={source}', '-C', str(source)]
    actual = subprocess.check_output(command + ['write-tree'], text=True).strip()
    if actual != manifest[name]['tree']:
        raise SystemExit(f'{name}: source index does not match sources.json; fetch pinned sources again')
    subprocess.run(command + ['diff', '--exit-code'], check=True)
for item in json.loads((project / 'firmware.json').read_text())['files']:
    source = project / 'inputs/firmware' / item['path']
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f'Missing firmware: {source}; run prepare-inputs.sh')
    data = source.read_bytes()
    if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
        raise SystemExit(f'Firmware mismatch: {source}')
    target = rootfs / 'root/tb322fc-build/firmware' / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)
PY
for component in hexagonrpc libssc iio-sensor-proxy libcamera; do
    mkdir -p "$STAGE/sources/$component"
    git -c "safe.directory=$PROJECT/sources/$component" -C "sources/$component" ls-files -z |
        tar -C "sources/$component" --null -T - -cf - |
        tar -C "$STAGE/sources/$component" -xf -
done
cp -a rootfs "$STAGE/overlay"
cp scripts/ci/configure-rootfs.sh "$STAGE/configure-rootfs.sh"
cp sources.json firmware.json artifacts/kernel.release "$ROOTFS/usr/share/tb322fc/"
cp artifacts/kernel-modules.tar.gz "$STAGE/kernel-modules.tar.gz"
cp docs/rootfs.md "$ROOTFS/usr/share/tb322fc/rootfs.md"

# /etc/resolv.conf may point into the not-yet-running systemd-resolved directory.
rm -f "$ROOTFS/etc/resolv.conf"
cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
mkdir -p "$ROOTFS"/{dev,proc,sys,run}
mount -t tmpfs -o mode=0755,nosuid tmpfs "$ROOTFS/dev"
mounts+=("$ROOTFS/dev")
for device in 'null 1 3' 'zero 1 5' 'full 1 7' 'random 1 8' 'urandom 1 9' 'tty 5 0'; do
    read -r name major minor <<< "$device"
    mknod -m 666 "$ROOTFS/dev/$name" c "$major" "$minor"
done
mkdir -p "$ROOTFS/dev/pts" "$ROOTFS/dev/shm"
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620,gid=5 devpts "$ROOTFS/dev/pts"
mounts+=("$ROOTFS/dev/pts")
ln -s pts/ptmx "$ROOTFS/dev/ptmx"
ln -s /proc/self/fd "$ROOTFS/dev/fd"
ln -s /proc/self/fd/0 "$ROOTFS/dev/stdin"
ln -s /proc/self/fd/1 "$ROOTFS/dev/stdout"
ln -s /proc/self/fd/2 "$ROOTFS/dev/stderr"
mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs "$ROOTFS/dev/shm"
mounts+=("$ROOTFS/dev/shm")
mount -t proc -o nosuid,nodev,noexec proc "$ROOTFS/proc"
mounts+=("$ROOTFS/proc")
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$ROOTFS/sys"
mounts+=("$ROOTFS/sys")
mount -t tmpfs -o mode=0755,nosuid,nodev tmpfs "$ROOTFS/run"
mounts+=("$ROOTFS/run")
chroot "$ROOTFS" /usr/bin/env -i PATH=/usr/bin:/usr/sbin HOME=/root \
    LC_ALL=C.UTF-8 JOBS="$JOBS" /bin/bash /root/tb322fc-build/configure-rootfs.sh
cp "$ROOTFS/usr/share/tb322fc/rootfs.packages" artifacts/rootfs.packages
cp "$ROOTFS/usr/share/tb322fc/userspace-build.txt" artifacts/userspace-build.txt

# Stop the keyring daemon before unmounting; pacman-key may leave it running.
chroot "$ROOTFS" /usr/bin/gpgconf --homedir /etc/pacman.d/gnupg --kill all
for (( index=${#mounts[@]}-1; index>=0; index-- )); do
    umount "${mounts[index]}"
    unset 'mounts[index]'
done
rm -rf "$STAGE"
rm -f "$ROOTFS/etc/resolv.conf"
ln -s /run/NetworkManager/resolv.conf "$ROOTFS/etc/resolv.conf"

image_bytes=$(numfmt --from=iec "$ROOTFS_SIZE")
used_bytes=$(du -sx --block-size=1 "$ROOTFS" | cut -f1)
(( used_bytes * 110 / 100 < image_bytes )) || die "ROOTFS_SIZE=$ROOTFS_SIZE is too small for $used_bytes bytes plus filesystem headroom."
truncate -s "$image_bytes" artifacts/rootfs.img.part
mke2fs -q -t ext4 -F -L rootfs -m 1 -d "$ROOTFS" artifacts/rootfs.img.part
e2fsck -fn artifacts/rootfs.img.part
mv artifacts/rootfs.img.part artifacts/rootfs.img
rm -rf "$ROOTFS"
echo 'Built artifacts/rootfs.img (raw ext4; the target partition must already be prepared).'
