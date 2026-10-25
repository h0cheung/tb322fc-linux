#!/usr/bin/env python3
"""Validate an Android boot base, stage a kShim image, then commit the new base."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile

STATE = Path('/var/lib/kshim-freedom')
LIB = Path('/usr/lib/kshim-freedom')
UPDATER = Path('/usr/bin/freedom-kernel-update')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_copy(source, target):
    """Publish a complete root-only file and persist the directory entry."""
    fd, name = tempfile.mkstemp(prefix='.' + target.name + '-', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output, 4 * 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    fd, name = tempfile.mkstemp(prefix='.json-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        atomic_copy(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_image(path, partition_size, avbtool):
    """Check the format actually accepted by the pinned builder and signer."""
    if not path.is_file() or path.stat().st_size != partition_size:
        raise ValueError(f'Expected a regular boot image of {partition_size} bytes')
    with path.open('rb') as stream:
        header = stream.read(4096)
        if len(header) != 4096 or header[:8] != b'ANDROID!':
            raise ValueError('Input is not an Android boot image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', header, 8)
        if (struct.unpack_from('<I', header, 40)[0] != 4 or
                struct.unpack_from('<I', header, 20)[0] != 1584):
            raise ValueError('The current kShim builder requires an Android boot v4 header')
        if ramdisk_size or struct.unpack_from('<I', header, 1580)[0]:
            raise ValueError('The current builder requires zero boot ramdisk/signature size; init_boot is separate')
        if kernel_size < 64 or 4096 + kernel_size > partition_size - 64:
            raise ValueError('Kernel size is outside the boot image')
        kernel = stream.read(64)
        if kernel[56:60] != b'ARM\x64':
            raise ValueError('The current builder requires an uncompressed ARM64 Image inside boot.img')
        stream.seek(-64, os.SEEK_END)
        magic, major, minor, original, offset, size, reserved = struct.unpack('>4sIIQQQ28s', stream.read(64))
        if magic != b'AVBf' or major != 1 or minor != 0 or any(reserved):
            raise ValueError('Missing or unsupported AVB footer')
        if not (4096 + kernel_size <= original <= offset and size > 0 and
                offset + size <= partition_size - 64):
            raise ValueError('AVB footer points outside the boot image or overlaps the kernel')
    avb = [sys.executable, str(avbtool)]
    subprocess.run(avb + ['verify_image', '--image', str(path)], check=True)
    info = subprocess.check_output(avb + ['info_image', '--image', str(path)], text=True)
    if not re.search(r'^Algorithm:\s+SHA256_RSA4096\s*$', info, re.M):
        raise ValueError('The current signer requires a SHA256_RSA4096 AVB template')
    if not re.search(r'^\s*Partition Name:\s+boot\s*$', info, re.M):
        raise ValueError('Expected an AVB hash descriptor for the boot partition')
    return dict(sha256=digest(path), bytes=partition_size, kernel_bytes=kernel_size)


def build_candidate(config, kernel, lock_fd):
    # Reuse the updater's lock across exec rather than racing a pacman hook.
    command = [str(UPDATER), '--config', str(config), '--kernel', kernel,
               '--stage-only', '--lock-fd', str(lock_fd)]
    with subprocess.Popen(command, pass_fds=(lock_fd,)) as process:
        try:
            status = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
        if status:
            raise subprocess.CalledProcessError(status, command)


def replace_base(source, config_path, kernel, check_only=False, state=STATE, lib=LIB):
    if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', kernel):
        raise ValueError('Invalid kernel release')
    if not source.is_file():
        raise ValueError('Input must be a regular Android boot image file')
    config_path = config_path.resolve(strict=True)
    config = json.loads(config_path.read_text())
    stock = Path(config['stock_boot']).resolve(strict=True)
    if not stock.is_file() or digest(stock) != config['stock_boot_sha256']:
        raise ValueError('Existing Android base differs from its configured hash; restore it first')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / 'update.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Read again under the same lock used by kernel updates.
        original_config = config_path.read_bytes()
        if json.loads(original_config) != config or digest(stock) != config['stock_boot_sha256']:
            raise RuntimeError('Configuration or Android base changed while waiting for the update lock')
        directory = Path(tempfile.mkdtemp(prefix='base-', dir=state))
        (directory / 'input').mkdir(mode=0o700)
        incoming = directory / 'input/boot.img'
        atomic_copy(source, incoming)
        try:
            image = validate_image(incoming, stock.stat().st_size, lib / 'avbtool.py')
        except BaseException:
            shutil.rmtree(directory)
            raise
        if check_only:
            shutil.rmtree(directory)
            return dict(status='validated', **image, changed=False, deployed=False)
        record = dict(status='prepared', started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      source=str(source.resolve()), config=str(config_path), stock_boot=str(stock),
                      old_sha256=config['stock_boot_sha256'], new_sha256=image['sha256'],
                      kernel=kernel, backup=str(directory), deployed=False)
        old_stock = directory / 'previous-boot.img'
        old_config = directory / 'previous-config.json'
        old_latest = directory / 'previous-latest.json'
        latest = state / 'latest.json'
        atomic_copy(stock, old_stock)
        atomic_copy(config_path, old_config)
        if digest(old_stock) != config['stock_boot_sha256']:
            raise RuntimeError('Android base backup verification failed')
        had_latest = latest.exists()
        if had_latest:
            atomic_copy(latest, old_latest)
        candidate_config = dict(config, stock_boot=str(incoming), stock_boot_sha256=image['sha256'])
        write_json(directory / 'candidate-config.json', candidate_config)
        write_json(directory / 'result.json', record)
        commit_started = False
        try:
            build_candidate(directory / 'candidate-config.json', kernel, lock.fileno())
            if not latest.exists() or (had_latest and latest.read_bytes() == old_latest.read_bytes()):
                raise RuntimeError('The updater did not produce a new candidate for this kernel')
            candidate = json.loads(latest.read_text())
            packed = Path(candidate['image'])
            if (candidate['release'] != kernel or candidate['deployed'] or
                    packed.stat().st_size != image['bytes'] or digest(packed) != candidate['sha256']):
                raise RuntimeError('Generated candidate metadata does not match the request')
            record['candidate'] = candidate
            record['status'] = 'built'
            write_json(directory / 'result.json', record)
            committed_config = dict(config, stock_boot_sha256=image['sha256'])
            write_json(directory / 'new-config.json', committed_config)
            commit_started = True
            atomic_copy(incoming, stock)
            atomic_copy(directory / 'new-config.json', config_path)
            if digest(stock) != image['sha256'] or json.loads(config_path.read_text()) != committed_config:
                raise RuntimeError('Committed Android base/config verification failed')
            record['status'] = 'completed'
            write_json(directory / 'result.json', record)
            return record
        except BaseException:
            if commit_started:
                atomic_copy(old_stock, stock)
                atomic_copy(old_config, config_path)
            if had_latest:
                atomic_copy(old_latest, latest)
            else:
                latest.unlink(missing_ok=True)
            record['status'] = 'failed_original_restored'
            write_json(directory / 'result.json', record)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, help='Compatible Android boot.img; never a block device')
    parser.add_argument('--kernel', default=os.uname().release, help='Linux release to package (default: running kernel)')
    parser.add_argument('--config', type=Path, default=Path('/etc/kshim-freedom/config.json'))
    parser.add_argument('--check-only', action='store_true', help='Validate without replacing files or building')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    os.umask(0o077)

    def interrupted(signum, frame):
        raise InterruptedError('Interrupted by signal ' + str(signum))

    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        result = replace_base(args.image, args.config, args.kernel, args.check_only)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, 'Android base replacement failed: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
