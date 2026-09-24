#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
mkdir -p build artifacts
url=${ARCH_ROOTFS_URL:-https://os.archlinuxarm.org/os/ArchLinuxARM-aarch64-latest.tar.gz}
archive=build/ArchLinuxARM-aarch64.tar.gz
[[ "$url" == https://* ]] || { echo 'ARCH_ROOTFS_URL must use HTTPS' >&2; exit 1; }
curl --fail --location --retry 5 --proto '=https' --proto-redir '=https' \
    --output "$archive.part" "$url"
mv "$archive.part" "$archive"
if [[ -n ${ARCH_ROOTFS_SHA256:-} ]]; then
    [[ "$ARCH_ROOTFS_SHA256" =~ ^[[:xdigit:]]{64}$ ]] || exit 1
    printf '%s  %s\n' "$ARCH_ROOTFS_SHA256" "$archive" | sha256sum --check -
    printf 'verification=explicit-sha256\n' > artifacts/arch-bootstrap.txt
else
    # Fingerprint published at https://archlinuxarm.org/about/downloads.
    fingerprint=68B3537F39A313B3E574D06777193F152BDBE6A6
    gnupg_home=$(mktemp -d)
    trap 'rm -rf "$gnupg_home"' EXIT
    chmod 700 "$gnupg_home"
    curl --fail --location --retry 5 --proto '=https' --proto-redir '=https' \
        --output "$archive.sig" "$url.sig"
    curl --fail --location --retry 5 --proto '=https' --proto-redir '=https' \
        --output "$gnupg_home/signer.asc" \
        "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$fingerprint"
    gpg --homedir "$gnupg_home" --batch --import "$gnupg_home/signer.asc"
    gpg --homedir "$gnupg_home" --batch --status-fd 1 --verify "$archive.sig" "$archive" \
        > "$gnupg_home/status"
    # Accept the documented primary key, including a signing subkey it certifies.
    awk -v f="$fingerprint" '$2 == "VALIDSIG" && ($3 == f || $NF == f) { ok=1 } END { exit !ok }' \
        "$gnupg_home/status"
    printf 'verification=openpgp\nsigner=%s\n' "$fingerprint" > artifacts/arch-bootstrap.txt
fi
sha256sum "$archive" > build/ArchLinuxARM-aarch64.sha256
cut -d ' ' -f 1 build/ArchLinuxARM-aarch64.sha256 | sed 's/^/sha256=/' >> artifacts/arch-bootstrap.txt
