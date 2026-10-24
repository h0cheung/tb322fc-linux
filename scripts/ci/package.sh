#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
: "${RELEASE_TAG:?Set an immutable freedom-v2-YYYYmmddHHMMSS release tag}"
python3 - "$RELEASE_TAG" <<'PY'
from pathlib import Path
import importlib.util,json,subprocess,shutil,sys
root=Path.cwd();p=root/'packages/gamescope-session-steam/freedom_release.py'
spec=importlib.util.spec_from_file_location('release',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=root/'artifacts/release'
if out.exists() and any(out.iterdir()):raise SystemExit('Release output must be empty')
out.mkdir(parents=True,exist_ok=True)
packages=[]
for name in sorted(m.REQUIRED):
 candidates=[]
 for f in (root/'build/rootfs-cache/pkgs').glob(name+'-*.pkg.tar.*'):
  if f.name.endswith('.sig'):continue
  info={}
  for line in subprocess.check_output(['bsdtar','-xOf',str(f),'.PKGINFO'],text=True).splitlines():
   if ' = ' in line:
    k,v=line.split(' = ',1);info[k]=v
  if info.get('pkgname')==name:candidates.append((f,info))
 if len(candidates)!=1:raise SystemExit(f'{name}: expected one package, got {len(candidates)}')
 f,info=candidates[0]
 if info['arch'] not in ['aarch64','any']:raise SystemExit('Wrong package architecture')
 safe=f.name.replace(':','.')
 shutil.copy2(f,out/safe)
 packages.append(dict(name=name,version=info['pkgver'],file=safe,bytes=f.stat().st_size,sha256=m.sha256(f)))
data=dict(format=m.FORMAT,tag=sys.argv[1],arch='aarch64',device='lenovo,elden',repository_tag=m.REPO_TAG,
          kernel_release=(root/'artifacts/kernel.release').read_text().strip(),
          requires_initialized_boot=True,packages=packages,
          kernel_build_id=json.loads((root/'artifacts/kernel-build.json').read_text())['build_id'],
          source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          freedom=json.loads((root/'configs/freedom-sources.json').read_text())['freedom'])
m.validate_manifest(data);m.verify_downloads(data,out)
(out/'freedom-release.json').write_text(json.dumps(data,indent=2)+'\n')
assert not m.LEGACY_ASSETS & {f.name for f in out.iterdir()}
(out/'SHA256SUMS').write_text(''.join(m.sha256(f)+'  '+f.name+'\n' for f in sorted(out.iterdir()) if f.is_file()))
PY
