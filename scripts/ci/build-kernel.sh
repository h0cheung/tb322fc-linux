#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run inside the authenticated Arch bootstrap, on a native ARM64 runner.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 && -f /etc/arch-release ]] || {
    echo 'Build the Freedom packages natively inside the Arch AArch64 staging root.' >&2; exit 1;
}
: "${CACHE:?Set the shared makepkg cache}"
JOBS=${JOBS:-$(nproc)}
[[ $JOBS =~ ^[1-9][0-9]*$ ]] || exit 2
export MAKEFLAGS="-j$JOBS"
# Headers are installed before DKMS source; kShim has no boot configuration in CI.
for name in linux-freedom als-bridge-dkms kshim-freedom; do
    work=$(mktemp -d -p /home/alarm "native-$name.XXXXXX")
    cp -a "packages/$name/." "$work/"
    chown -R alarm:alarm "$work"
    mapfile -t deps < <(bash -c 'source "$1/PKGBUILD"; printf "%s\n" "${makedepends[@]}" "${depends[@]}"' _ "$work")
    pacman -S --needed --noconfirm "${deps[@]}"
    # Source tarballs have fixed SHA256s; Git sources have exact commits.
    # The minimal bootstrap has no maintainer signing keys for kernel.org.
    sudo -u alarm env JOBS="$JOBS" MAKEFLAGS="$MAKEFLAGS" \
        bash -c 'cd "$1" && makepkg -f --skippgpcheck' _ "$work"
    mapfile -t built < <(sudo -u alarm bash -c 'cd "$1" && makepkg --packagelist' _ "$work")
    (( ${#built[@]} )) || exit 1
    pacman -U --noconfirm --ask 6 "${built[@]}"
    cp "$work/PKGBUILD" "$CACHE/$name.PKGBUILD"
    rm -rf -- "$work"
done
mapfile -t kernels < <(find /usr/lib/modules -mindepth 2 -maxdepth 2 -name pkgbase -exec sh -c \
    'test "$(cat "$1")" = linux-freedom && dirname "$1"' _ {} \;)
(( ${#kernels[@]} == 1 )) || { echo 'Expected exactly one packaged Freedom kernel' >&2; exit 1; }
release=${kernels[0]##*/}
modinfo -k "$release" als_bridge >/dev/null
printf '%s\n' "$release" > /usr/share/tb322fc/kernel.release
cp "${kernels[0]}/config" /usr/share/tb322fc/kernel.config
cp "${kernels[0]}/build-manifest.json" /usr/share/tb322fc/kernel-build.json
