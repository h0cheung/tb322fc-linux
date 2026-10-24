#!/usr/bin/env python3
"""Sign a kShim boot image with fresh hashes and stock AVB properties."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys


def image_info(avb, path):
    return subprocess.check_output(avb + ['info_image', '--image', str(path)], text=True)


def field(text, name):
    found = re.search(r'^' + re.escape(name) + r':\s+(.+)$', text, re.M)
    if not found:
        raise ValueError('Missing AVB field: '+name)
    return found[1].strip()


def properties(text):
    result = {}
    for line in text.splitlines():
        if line.lstrip().startswith('Prop:'):
            found = re.fullmatch(r"\s*Prop: (\S+) -> '(.*)'", line)
            if not found:
                raise ValueError('Unsupported stock property encoding')
            result[found[1]] = found[2]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['image', 'stock-boot', 'key', 'out', 'avbtool']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--header-template', type=Path,
                        help='Optional tested Android v4 header metadata, independent of stock AVB properties')
    args = parser.parse_args()
    if args.out.name != 'boot.img' or args.out.resolve() == args.image.resolve():
        parser.error('Use a distinct output directory with filename boot.img for avbtool descriptor resolution')
    avb = [sys.executable, str(args.avbtool.resolve())]
    subprocess.run(avb+['verify_image','--image',str(args.stock_boot)],check=True)
    stock_info = image_info(avb, args.stock_boot)
    props = properties(stock_info)
    if field(stock_info, 'Algorithm') != 'SHA256_RSA4096':
        parser.error('Unexpected stock signature algorithm')
    partition_size = args.stock_boot.stat().st_size
    stock = args.stock_boot.read_bytes()
    original = args.image.read_bytes()
    if original[:8] != b'ANDROID!' or struct.unpack_from('<I', original, 40)[0] != 4:
        parser.error('Input must be an Android v4 boot image')
    header_template = args.header_template.read_bytes() if args.header_template else None
    if header_template is not None:
        if header_template[:8] != b'ANDROID!' or struct.unpack_from('<I',header_template,40)[0] != 4:
            parser.error('Header template must be Android v4')
        if original[16:20] != header_template[16:20]:
            parser.error('Input OS header metadata differs from selected header template')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.image, args.out)
    subprocess.run(avb+['erase_footer','--image',str(args.out)],check=True)
    command = avb+['add_hash_footer','--image',str(args.out),'--partition_size',str(partition_size),
                   '--partition_name','boot','--algorithm','SHA256_RSA4096','--key',str(args.key),
                   '--rollback_index',field(stock_info,'Rollback Index'),
                   '--rollback_index_location',field(stock_info,'Rollback Index Location'),
                   '--flags',field(stock_info,'Flags')]
    for name,value in props.items():
        command += ['--prop',name+':'+value]
    subprocess.run(command,check=True)
    subprocess.run(avb+['verify_image','--image',str(args.out),'--key',str(args.key)],check=True)
    signed_info = image_info(avb,args.out)
    if properties(signed_info) != props:
        raise ValueError('Signed properties differ from stock')
    signed = args.out.read_bytes()
    kernel_size = struct.unpack_from('<I',original,8)[0]
    if len(signed) != partition_size or signed[:4096+kernel_size] != original[:4096+kernel_size]:
        raise ValueError('Signing changed boot payload or partition size')
    record = dict(stock_sha256=hashlib.sha256(stock).hexdigest(),properties=props,
                  rollback_index=int(field(stock_info,'Rollback Index')),
                  stock_public_key=field(stock_info,'Public key (sha1)'),
                  signed_public_key=field(signed_info,'Public key (sha1)'),
                  uses_supplied_project_key=True,boot_sha256=hashlib.sha256(signed).hexdigest(),
                  header_template_sha256=hashlib.sha256(header_template).hexdigest() if header_template is not None else None,
                  header_os_version=struct.unpack_from('<I',signed,16)[0],
                  payload_unchanged=True,flashed=False)
    (args.out.parent/'signing.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
