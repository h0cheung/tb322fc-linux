#!/usr/bin/env python3
"""G9 DS 模式的双击 Home：保留原输入，只额外发送 QuickAccess。"""

import logging
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import time


BUS = "org.shadowblip.InputPlumber"
INTERFACE = "org.shadowblip.Input.CompositeDevice"
NAME = "Sony Interactive Entertainment Legion Gaming Controller G9 2026"
DOUBLE_SECONDS = 0.45
SHORT_SECONDS = 0.35
running = True


def stop(*_args):
    global running
    running = False


def busctl(*args):
    return subprocess.check_output(
        ["busctl", "--system", *args], text=True, stderr=subprocess.PIPE, timeout=2
    ).strip()


def quick_access(device):
    # 重新按 source 查找 composite，编号可在热插拔后复用或变化。
    for path in busctl("--list", "tree", BUS).splitlines():
        if not path.startswith("/org/shadowblip/InputPlumber/CompositeDevice"):
            continue
        source = shlex.split(busctl("get-property", BUS, path, INTERFACE, "SourceDevicePaths"))
        if str(device) not in source[2:]:
            continue
        busctl("call", BUS, path, INTERFACE, "SendButtonChord", "as", "1",
               "Gamepad:Button:QuickAccess")
        logging.info("G9 DS double Home -> QuickAccess")
        return


def find_device():
    for entry in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        try:
            properties = dict(
                line.split("=", 1)
                for line in (entry / "device/uevent").read_text().splitlines()
                if "=" in line
            )
            if (properties.get("HID_NAME") == NAME
                    and properties.get("HID_ID") == "0003:0000054C:00000CE6"):
                return Path("/dev") / entry.name
        except OSError:
            continue
    return None


def follow(device):
    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    down_at = None
    previous_release = None
    home_before = None
    pending = None
    try:
        while running:
            now = time.monotonic()
            if pending is not None and now >= pending:
                pending = None
                try:
                    quick_access(device)
                except (subprocess.SubprocessError, OSError) as error:
                    logging.warning("QuickAccess delivery failed: %s", error)
            if not select.select([fd], [], [], 0.02)[0]:
                continue
            try:
                report = os.read(fd, 512)
            except BlockingIOError:
                continue
            if not report:
                return
            if len(report) != 64 or report[0] != 1:
                continue
            # 内核 hid-playstation 的 USB DualSense 按钮布局；不采集或记录轴/IMU。
            buttons = report[8:12]
            home = bool(buttons[2] & 1)
            other = (buttons[0] != 8 or buttons[1] != 0
                     or buttons[2] & ~1 or buttons[3] != 0)
            now = time.monotonic()
            if other:
                previous_release = down_at = pending = None
                home_before = home
                continue
            if home_before is None:
                home_before = home
                continue
            if home == home_before:
                continue
            home_before = home
            if home:
                down_at = now
                continue
            if down_at is None or now - down_at > SHORT_SECONDS:
                previous_release = down_at = None
                continue
            down_at = None
            if previous_release is not None and now - previous_release <= DOUBLE_SECONDS:
                # 等正常的第二次 Guide 释放先到 Steam，再发独立的 QAM 按钮脉冲。
                pending = now + 0.08
                previous_release = None
            else:
                previous_release = now
    finally:
        os.close(fd)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        device = find_device()
        if device is not None:
            try:
                follow(device)
            except (OSError, ValueError):
                # 拔出时 fd 失效；下一轮重新按身份查找，不固定 hidraw 编号。
                pass
        if running:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
