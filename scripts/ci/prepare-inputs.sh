#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
: "${FIRMWARE_URL:?Set the FIRMWARE_URL Actions secret or firmware_url input; see docs/ci.md}"
: "${FIRMWARE_SHA256:?Set FIRMWARE_SHA256 to the SHA256 of the firmware bundle}"
[[ "$FIRMWARE_URL" == https://* ]] || { echo 'Firmware URL must use HTTPS' >&2; exit 1; }
[[ "$FIRMWARE_SHA256" =~ ^[[:xdigit:]]{64}$ ]] || { echo 'Invalid firmware SHA256' >&2; exit 1; }
mkdir -p build artifacts inputs
curl --fail --location --retry 5 --proto '=https' --proto-redir '=https' \
    --output build/firmware.tar.gz.part "$FIRMWARE_URL"
printf '%s  %s\n' "$FIRMWARE_SHA256" build/firmware.tar.gz.part | sha256sum --check -
mv build/firmware.tar.gz.part build/firmware.tar.gz
python3 scripts/ci/firmware-bundle.py unpack build/firmware.tar.gz inputs/firmware
# Do not publish the input URL: it can contain temporary download credentials.
printf 'firmware_bundle_sha256=%s\n' "$FIRMWARE_SHA256" > artifacts/firmware-input.txt
