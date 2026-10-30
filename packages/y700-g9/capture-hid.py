#!/usr/bin/env python3
"""Read-only capture of the G9 2026 0.14 native HID report and evdev ranges."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import select
import struct
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--log', type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error('--seconds must be in 0..3600')
    matches = []
    for item in Path('/sys/class/hidraw').glob('hidraw*'):
        dev = item / 'device'
        if ('HID_ID=0003:00003537:00001136' in (dev / 'uevent').read_text()
                and (dev / 'report_descriptor').read_bytes().startswith(bytes.fromhex('05010905'))):
            matches.append(item)
    if len(matches) != 1:
        raise RuntimeError(f'Expected one G9 native HID gamepad: {matches}')
    descriptor = (matches[0] / 'device/report_descriptor').read_bytes()
    if bytes.fromhex('26ffff75109504') not in descriptor:
        raise RuntimeError('G9 still has its stock 8-bit HID descriptor')
    ranges = {}
    for node in Path('/sys/class/input').glob('event*'):
        if (node / 'device/name').read_text().strip() != 'GameSir Legion Gaming Controller G9 2026':
            continue
        event_fd = os.open('/dev/input/' + node.name, os.O_RDONLY)
        try:
            for axis in (0, 1, 2, 5, 9, 10):
                ranges[str(axis)] = struct.unpack('6i', fcntl.ioctl(event_fd, 0x80184540 + axis, bytes(24)))
        finally:
            os.close(event_fd)
    print(json.dumps({'device': matches[0].name, 'descriptor': descriptor.hex(), 'absinfo': ranges}), flush=True)
    logfile = args.log.open('w') if args.log else None
    fd = os.open('/dev/' + matches[0].name, os.O_RDONLY | os.O_NONBLOCK)
    started, seen, last_keys = time.monotonic(), 0, None
    values = [set() for _ in range(4)]
    try:
        while time.monotonic() - started < args.seconds:
            if not select.select([fd], [], [], 0.2)[0]:
                continue
            data = os.read(fd, 64)
            if len(data) < 15 or data[0] != 1:
                continue
            seen += 1
            axes = struct.unpack_from('<4H', data, 1)
            for s, x in zip(values, axes):
                s.add(x)
            buttons = int.from_bytes(data[10:13], 'little')
            state = {'seconds': round(time.monotonic() - started, 3), 'axes': axes,
                     'buttons': buttons, 'home': bool(buttons & 4096),
                     'extras': [i + 1 for i in range(5) if buttons & (1 << (16 + i))],
                     'hat': data[9], 'triggers': list(data[13:15]), 'raw': data.hex()}
            if logfile:
                logfile.write(json.dumps(state) + '\n')
            keys = (buttons, data[9])
            if keys != last_keys:
                print(json.dumps(state), flush=True)
                last_keys = keys
    finally:
        os.close(fd)
        if logfile:
            logfile.close()
    stats = []
    for s in values:
        ordered = sorted(s)
        stats.append({'levels': len(s), 'min': min(s) if s else None,
                      'max': max(s) if s else None,
                      'observed_step_gcd': math.gcd(*(b - a for a, b in zip(ordered, ordered[1:])))})
    print(json.dumps({'reports': seen, 'axes': stats}), flush=True)


if __name__ == '__main__':
    main()
