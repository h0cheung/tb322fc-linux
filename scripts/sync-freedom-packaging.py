#!/usr/bin/env python3
"""Refresh shared source copies and checksums for the Freedom packages."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(repo / 'packages/linux-freedom/sync-recipe.py')], check=True)
als = repo / 'packages/als-bridge-dkms'
for name in ('als-bridge.c', 'Makefile'):
    shutil.copyfile(repo / 'packages/als-bridge' / name, als / name)
p = als / 'PKGBUILD'
lines = p.read_text().splitlines()
hashes = [hashlib.sha256((als / name).read_bytes()).hexdigest() for name in
          ('als-bridge.c', 'Makefile', 'dkms.conf')]
lines = [('sha256sums=(' + ' '.join(repr(x) for x in hashes) + ')')
         if line.startswith('sha256sums=') else line for line in lines]
p.write_text('\n'.join(lines) + '\n')
kshim = repo / 'packages/kshim-freedom'
for source, name in [('initramfs/init', 'init'), ('scripts/sign-kshim-boot.py', 'sign-kshim-boot.py'),
                     ('configs/freedom-sources.json', 'freedom-sources.json'),
                     ('configs/busybox.config', 'busybox.config'),
                     ('patches/kshim/0001-neutral-linux-menu-labels.patch', 'neutral-linux-menu-labels.patch')]:
    shutil.copyfile(repo / source, kshim / name)
p = kshim / 'PKGBUILD'
s = p.read_text()
a = s.index('# Generated local hashes')
b = s.index('\n\nbuild()', a)
names = ['build-tools.py', 'libfdt-stdlib-include.patch', 'crdk-pinned-archive.patch', 'native-aarch64-toolchain.patch', 'neutral-linux-menu-labels.patch',
         'busybox.config', 'init', 'sign-kshim-boot.py', 'freedom-sources.json', 'build-kshim-arch.py',
         'arch-explicit-layout.patch', 'freedom-kernel-update.py', '95-kshim-freedom.hook', '60-kshim-freedom-backup.hook']
s = s[:a] + '# Generated local hashes are maintained by scripts/sync-freedom-packaging.py.\nsha256sums+=(\n  ' + \
    '\n  '.join(repr(hashlib.sha256((kshim / n).read_bytes()).hexdigest()) for n in names) + '\n)' + s[b:]
p.write_text(s)
