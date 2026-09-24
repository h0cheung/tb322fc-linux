#!/usr/bin/env python3
"""Pack/verify/unpack only the firmware named and hashed in firmware.json."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def manifest():
    return {row['path']: row for row in json.loads((ROOT / 'firmware.json').read_text())['files']}


def checked(data, row):
    if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError(f"Firmware content mismatch: {row['path']}")
    return data


def verify(directory, rows):
    for name, row in rows.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing regular firmware file: {name}')
        checked(path.read_bytes(), row)


def pack(directory, archive, rows):
    verify(directory, rows)
    if archive.exists() or archive.is_symlink():
        raise ValueError(f'Refusing to replace existing archive: {archive}')
    # Fixed metadata makes re-packaging the same verified set deterministic.
    with archive.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as out:
            for name, row in sorted(rows.items()):
                data = checked((directory / name).read_bytes(), row)
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                out.addfile(info, io.BytesIO(data))


def unpack(archive, directory, rows):
    if directory.exists() or directory.is_symlink():
        raise ValueError(f'Refusing to replace existing directory: {directory}')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='firmware-', dir=directory.parent) as temp:
        stage = Path(temp) / 'payload'
        stage.mkdir()
        seen = set()
        # Do not extract tar paths, links, owners or modes. Only exact manifest
        # names can be written, after checking declared size and actual content.
        with tarfile.open(archive, mode='r|*') as source:
            for entry in source:
                if not entry.isfile() or entry.name not in rows or entry.name in seen:
                    raise ValueError(f'Unexpected or duplicate firmware archive member: {entry.name}')
                row = rows[entry.name]
                if entry.size != row['size']:
                    raise ValueError(f'Unexpected firmware size: {entry.name}')
                stream = source.extractfile(entry)
                assert stream is not None
                data = checked(stream.read(row['size'] + 1), row)
                target = stage / entry.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                seen.add(entry.name)
        missing = rows.keys() - seen
        if missing:
            raise ValueError('Missing firmware: ' + ', '.join(sorted(missing)))
        stage.rename(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('verify')
    p.add_argument('directory', type=Path)
    p = sub.add_parser('pack')
    p.add_argument('directory', type=Path)
    p.add_argument('archive', type=Path)
    p = sub.add_parser('unpack')
    p.add_argument('archive', type=Path)
    p.add_argument('directory', type=Path)
    args = parser.parse_args()
    rows = manifest()
    if args.command == 'verify':
        verify(args.directory, rows)
    elif args.command == 'pack':
        pack(args.directory, args.archive, rows)
        print(f'{hashlib.sha256(args.archive.read_bytes()).hexdigest()}  {args.archive.name}')
    else:
        unpack(args.archive, args.directory, rows)
    print(f'Verified {len(rows)} firmware files')


if __name__ == '__main__':
    main()
