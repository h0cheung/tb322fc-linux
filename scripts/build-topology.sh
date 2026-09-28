#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile the tracked AudioReach topology source into the firmware tree.
# Used by the CI build (a dedicated step) and local builds so they cannot drift.
set -euo pipefail
PROJECT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT"
command -v alsatplg >/dev/null || { echo 'Missing host tool: alsatplg (alsa-utils)' >&2; exit 1; }
out=inputs/firmware/qcom/sm8750/Lenovo-Y700-Gen4-tplg.bin
mkdir -p "$(dirname -- "$out")"
# Regenerate inputs/audio/Lenovo-Y700-Gen4.conf with m4 + sources/audioreach-topology
# only when changing the graph; alsatplg alone suffices for a normal build.
alsatplg -c inputs/audio/Lenovo-Y700-Gen4.conf -o "$out"
