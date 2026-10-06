#!/usr/bin/python3
"""Resolve the human ("session") user for the privileged Armada services.

The daemon and the boot-time scripts need the account that owns the graphical
session: to run session commands as that user, and to locate its home for
per-user state. Upstream ArmadaOS is a single-user image with a fixed account
("armada"); this port runs on a normal Arch Linux Ports install, so the account
is discovered instead of assumed. $ARMADA_SESSION_USER overrides the lookup.
"""
import os
import pwd
import subprocess
from pathlib import Path

LOGINCTL = "/usr/bin/loginctl"


def _logind_user():
    # The owner of the active graphical session.
    try:
        listing = subprocess.run(
            [LOGINCTL, "list-sessions", "--no-legend"],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in listing.splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            props = subprocess.run(
                [LOGINCTL, "show-session", fields[0],
                 "-p", "Name", "-p", "Type", "-p", "Class", "-p", "Active"],
                check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        values = dict(part.split("=", 1) for part in props.splitlines() if "=" in part)
        if (values.get("Class") == "user" and values.get("Active") == "yes"
                and values.get("Type") in ("wayland", "x11") and values.get("Name")):
            return values["Name"]
    return ""


def _human_user():
    # Early boot has no session yet; accept the sole human account, and only
    # then: with several candidates we cannot tell which one owns the session.
    candidates = [
        entry.pw_name
        for entry in pwd.getpwall()
        if entry.pw_uid >= 1000 and entry.pw_uid != 65534
        and not entry.pw_shell.endswith(("nologin", "false"))
        and entry.pw_dir not in ("", "/", "/nonexistent")
    ]
    return candidates[0] if len(candidates) == 1 else ""


def session_user():
    for candidate in (os.environ.get("ARMADA_SESSION_USER"), _logind_user(), _human_user()):
        if candidate:
            return candidate
    return ""


def session_home():
    user = session_user()
    if not user:
        return None
    try:
        return Path(pwd.getpwnam(user).pw_dir)
    except KeyError:
        return None


if __name__ == "__main__":
    print(session_user())
