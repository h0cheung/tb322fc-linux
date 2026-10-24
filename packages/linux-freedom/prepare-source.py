#!/usr/bin/env python3
"""Apply the fixed Freedom patch series and board trees without fuzz."""
from pathlib import Path
import argparse
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('recipe', type=Path)
p.add_argument('driver_patches', type=Path, nargs='+')
a = p.parse_args()

def apply(path):
    command = ['patch', '-p1', '--batch', '--forward', '-F0', '--no-backup-if-mismatch', '-i', str(path.resolve())]
    subprocess.run(command + ['--dry-run'], cwd=a.source, check=True)
    subprocess.run(command, cwd=a.source, check=True)

kernel = a.recipe / 'packages/kernel'
for line in (kernel / 'patches/series').read_text().splitlines():
    name = line.split('#', 1)[0].strip()
    if name:
        apply(kernel / 'patches' / name)
target = a.source / 'arch/arm64/boot/dts/qcom'
for path in (kernel / 'dts').iterdir():
    if path.suffix in ('.dts', '.dtsi'):
        shutil.copyfile(path, target / path.name)
for path in sorted((kernel / 'dts').glob('*.patch')):
    apply(path)
for path in a.driver_patches:
    apply(path)
