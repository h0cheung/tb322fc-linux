#!/usr/bin/env python3
"""Copy shared inputs and refresh the local PKGBUILD checksums."""
from pathlib import Path
import hashlib
import shutil

here = Path(__file__).resolve().parent
repo = here.parent.parent
for source, name in [('configs/freedom-compat.config', 'freedom-compat.config'),
                     ('patches/freedom/0002-ath12k-enable-range-scans-on-elden.patch', 'elden-range-scans.patch')]:
    shutil.copyfile(repo / source, here / name)
hashes = [hashlib.sha256((here / name).read_bytes()).hexdigest() for name in
          ['freedom-compat.config', 'elden-range-scans.patch', 'prepare-source.py',
           'export-kernel-input.py', 'build-native-helpers.sh']]
p = here / 'PKGBUILD'
s = p.read_text()
start = s.index("  sha256sums=('039aef84")
end = s.index('\nfi', start)
values = ['039aef84f2b0994aeda3f4fcfc3d02ec9d7a9bbb9020ea264c43f446c860f606',
          'SKIP', 'SKIP'] + hashes + [
    '4b69e6c5c8e1520bd3fcf388389cf98ac7fc77d96b0891e36187c9d29ca30ec3',
    hashlib.sha256((here / 'q6v5-attach-keep-handover-masked.patch').read_bytes()).hexdigest(),
    '30b45a34e029aee8cd57123300a83ab1dfe473cb6c88d87ad1b3cccd891e0648',
]
s = s[:start] + '  sha256sums=(' + '\n              '.join(repr(x) for x in values) + ')' + s[end:]
p.write_text(s)
