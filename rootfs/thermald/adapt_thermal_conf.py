#!/usr/bin/env python3
"""Select the registered battery thermal sensor without changing policy."""
import argparse
import os
from pathlib import Path
import re
import tempfile
import time
import xml.etree.ElementTree as ET

BATTERY_TYPES = ("qcom-battmgr-bat", "battery")


def battery_type(thermal_root):
    present = set()
    for path in Path(thermal_root).glob("thermal_zone*/type"):
        try:
            present.add(path.read_text().strip())
        except OSError:
            continue
    return next((name for name in BATTERY_TYPES if name in present), None)


def adapt(source, thermal_root):
    text = Path(source).read_text()
    ET.fromstring(text)
    selected = battery_type(thermal_root)
    if selected:
        text = re.sub(r"(<SensorType>\s*)(?:qcom-battmgr-bat|battery)(\s*</SensorType>)",
                      lambda m: m[1] + selected + m[2], text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/etc/thermald/thermal-conf.xml")
    parser.add_argument("--output", default="/run/thermald/thermal-conf.xml")
    parser.add_argument("--thermal-root", default="/sys/class/thermal")
    parser.add_argument("--wait-seconds", type=float, default=0)
    args = parser.parse_args()
    # Freedom loads battmgr as a module. Allow bounded startup ordering without
    # adding a background watcher or changing the persisted policy template.
    deadline = time.monotonic() + max(0, args.wait_seconds)
    while not battery_type(args.thermal_root) and time.monotonic() < deadline:
        time.sleep(0.1)
    if not battery_type(args.thermal_root):
        # thermald enumerates sensors on startup. Starting without this zone
        # would silently omit the battery policy even after the module loads.
        # Let the unit's existing Restart=on-failure retry its normal startup.
        parser.exit(1, "Battery thermal zone is not registered yet\n")
    text = adapt(args.source, args.thermal_root)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as f:
        temporary = Path(f.name)
        try:
            os.fchmod(f.fileno(), 0o644)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
