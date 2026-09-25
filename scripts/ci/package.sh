#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
mkdir -p artifacts/release
[[ -z $(find artifacts/release -mindepth 1 -print -quit) ]] || {
    echo 'artifacts/release must be empty before packaging' >&2; exit 1;
}
for name in boot.img rootfs.img; do
    [[ -s artifacts/$name ]] || { echo "Missing artifacts/$name" >&2; exit 1; }
    zstd -T0 -10 --check -c "artifacts/$name" > "artifacts/release/$name.zst"
    zstd --test "artifacts/release/$name.zst"
    if (( $(stat -c %s "artifacts/release/$name.zst") > 1900000000 )); then
        split -b 1900000000 -d -a 3 "artifacts/release/$name.zst" "artifacts/release/$name.zst."
        rm "artifacts/release/$name.zst"
    fi
done
[[ -s artifacts/kernel-modules.tar.gz ]] || { echo "Missing artifacts/kernel-modules.tar.gz" >&2; exit 1; }
cp artifacts/kernel-modules.tar.gz artifacts/release/
(cd artifacts && sha256sum boot.img rootfs.img kernel-modules.tar.gz) > artifacts/release/RAW-SHA256SUMS
cp sources.json firmware.json artifacts/release/
cp artifacts/{kernel.release,kernel.config,arch-bootstrap.txt,firmware-input.txt} artifacts/release/
cp artifacts/{rootfs.packages,userspace-build.txt} artifacts/release/
{
    printf 'repository_commit=%s\n' "$(git rev-parse HEAD)"
    printf 'build_time_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'workflow_run=%s\n' "${GITHUB_RUN_ID:-local}"
    printf 'root_selector=PARTLABEL=rootfs\nboot_format=android-v4-direct-kernel\n'
    clang --version | head -1
} > artifacts/release/BUILD-INFO.txt
(cd artifacts/release && sha256sum ./* > SHA256SUMS)
