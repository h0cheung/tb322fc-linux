#!/usr/bin/env python3
"""Copy shared inputs and refresh the local PKGBUILD checksums."""
from pathlib import Path
import hashlib
import shutil

here = Path(__file__).resolve().parent
repo = here.parent.parent
inputs = [
    ('configs/freedom-compat.config', 'freedom-compat.config'),
    ('patches/freedom/0002-ath12k-enable-range-scans-on-elden.patch', 'elden-range-scans.patch'),
    ('patches/freedom/0003-usb-dwc3-enable-elden-power-lost.patch', 'elden-host-power-lost.patch'),
    ('patches/freedom/0004-usb-elden-suspend-order-and-eusb2.patch', 'elden-usb-suspend.patch'),
    ('patches/freedom/0005-drm-msm-elden-atomic-state-and-refresh.patch', 'elden-display-state.patch'),
    ('patches/freedom/0006-pci-qcom-elden-fixed-slot.patch', 'elden-pcie-fixed-slot.patch'),
    ('patches/freedom/0007-ath12k-elden-panic-wake.patch', 'elden-panic-wake.patch'),
    ('patches/freedom/0008-bluetooth-elden-configured-address.patch', 'elden-bt-address.patch'),
    ('patches/freedom/0009-arm64-elden-ufs-mcq.patch', 'elden-ufs-mcq.patch'),
    ('patches/freedom/0010-ufs-qcom-restore-esi-after-reset.patch', 'ufs-restore-esi.patch'),
    ('patches/freedom/0011-ath12k-drain-cancelled-scan-cleanup.patch', 'ath12k-scan-cancel.patch'),
]
for source, name in inputs:
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
    hashlib.sha256((here / 'elden-host-power-lost.patch').read_bytes()).hexdigest(),
] + [hashlib.sha256((here / name).read_bytes()).hexdigest()
     for _, name in inputs[3:]] + [
    'fd6069f5ac61c642bd7d1b402a88d74cb00aab7f353802d22b953dc9a8aee8ee',  # Upstream UFS internal-command error-recovery fix.
]
s = s[:start] + '  sha256sums=(' + '\n              '.join(repr(x) for x in values) + ')' + s[end:]
p.write_text(s)
