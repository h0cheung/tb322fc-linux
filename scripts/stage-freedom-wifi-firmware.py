#!/usr/bin/env python3
"""Stage the hash-pinned WCN7860 firmware required by Freedom's Wi-Fi driver."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Freedom system_files/usr/lib/firmware')
    parser.add_argument('--root', type=Path, required=True, help='Destination root or staging directory')
    parser.add_argument('--manifest', type=Path,
                        default=Path(__file__).resolve().parents[1]/'configs/freedom-wifi-firmware.json')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    for item in manifest['files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            parser.error('invalid firmware path')
        source = args.source/relative
        target = args.root/'usr/lib/firmware'/relative
        if source.stat().st_size != item['bytes'] or digest(source) != item['sha256']:
            parser.error('source firmware differs from pinned manifest: '+item['path'])
        if target.exists() and digest(target) != item['sha256']:
            parser.error('destination contains a different firmware: '+str(target))
    for item in manifest['files']:
        target = args.root/'usr/lib/firmware'/item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source/item['path'], target)
        target.chmod(0o644)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
