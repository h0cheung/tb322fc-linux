#!/usr/bin/env python3
"""Export a completed ARM64 kernel build for native makepkg packaging."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'output', 'destination', 'helpers'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
src, out, dest = a.source.resolve(), a.output.resolve(), a.destination.resolve()
assert not dest.exists(), dest
release = (out / 'include/config/kernel.release').read_text().strip()
assert re.fullmatch(r'\d+\.\d+\.\d+-\d+-freedom', release), release
config = (out / '.config').read_text()
for option in ('CONFIG_SECURITY_LANDLOCK', 'CONFIG_F2FS_FS_SECURITY',
               'CONFIG_DEBUG_INFO_BTF_MODULES', 'CONFIG_LTO_CLANG_THIN'):
    assert option + '=y\n' in config, option
notes = subprocess.check_output(['readelf', '-n', str(out / 'vmlinux')], text=True)
build_id = re.search(r'Build ID: ([0-9a-f]+)', notes)[1]
image = out / 'arch/arm64/boot/Image'
assert bytes.fromhex(build_id) in image.read_bytes(), 'ELF and Image build IDs differ'
dest.mkdir(parents=True)
headers = dest / 'headers'
headers.mkdir()
for name in ('Makefile',):
    shutil.copyfile(src / name, headers / name)
for name in ('.config', 'Module.symvers', 'System.map', 'vmlinux'):
    shutil.copyfile(out / name, headers / name)
subprocess.run(['llvm-strip', '--strip-debug', str(headers / 'vmlinux')], check=True)
for name in ('include', 'scripts', 'tools'):
    shutil.copytree(src / name, headers / name, symlinks=True)
shutil.copytree(out / 'include', headers / 'include', dirs_exist_ok=True)
for name in ('arch/arm64/include',):
    shutil.copytree(src / name, headers / name, symlinks=True)
    shutil.copytree(out / name, headers / name, dirs_exist_ok=True)
for name in ('arch/arm64/Makefile', 'kernel/Makefile'):
    (headers / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / name, headers / name)
for pattern in ('drivers/md/*.h', 'net/mac80211/*.h', 'drivers/media/i2c/msp3400-driver.h',
                'drivers/media/usb/dvb-usb/*.h', 'drivers/media/dvb-frontends/*.h',
                'drivers/media/tuners/*.h', 'drivers/iio/common/hid-sensors/*.h'):
    for path in src.glob(pattern):
        relative = path.relative_to(src)
        (headers / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, headers / relative)
for path in src.rglob('Kconfig*'):
    relative = path.relative_to(src)
    if not path.is_file() or (relative.parts[0] == 'arch' and relative.parts[1] != 'arm64'):
        continue
    (headers / relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, headers / relative)
for name in ('scripts/module.lds', 'scripts/mod/elfconfig.h', 'scripts/mod/devicetable-offsets.h',
             'arch/arm64/kernel/asm-offsets.s'):
    (headers / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / name, headers / name)
for name in ('localversion.10-pkgrel', 'localversion.20-pkgname'):
    shutil.copyfile(src / name, headers / name)
(headers / 'version').write_text(release + '\n')
shutil.copyfile(image, dest / 'Image')
shutil.copyfile(out / 'arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dtb', dest / 'sm8750-lenovo-elden.dtb')
shutil.copyfile(a.helpers, dest / 'build-native-helpers.sh')
stage = dest / 'module-stage'
env = dict(os.environ, LOCALVERSION='')
subprocess.run(['make', '-C', str(src), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
                'INSTALL_MOD_PATH=' + str(stage), 'INSTALL_MOD_STRIP=1', 'DEPMOD=true', 'modules_install'],
               env=env, check=True)
modules = stage / 'lib/modules' / release
assert modules.is_dir()
for name in ('build', 'source'):
    path = modules / name
    if path.is_symlink():
        path.unlink()
shutil.move(modules, dest / 'modules')
shutil.rmtree(stage)
assert not list((dest / 'modules').rglob('als-bridge.ko*')), 'ALS must be supplied by DKMS'
paths = ['Image', 'sm8750-lenovo-elden.dtb', 'headers/.config', 'headers/Module.symvers', 'headers/vmlinux']
manifest = dict(release=release, build_id=build_id, module_count=len(list((dest / 'modules').rglob('*.ko'))),
                hashes={name: hashlib.sha256((dest / name).read_bytes()).hexdigest() for name in paths})
(dest / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
