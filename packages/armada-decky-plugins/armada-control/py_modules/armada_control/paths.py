import os
import pwd
from pathlib import Path


def user_name():
    # Decky exports the host (Steam) account to every plugin backend, including
    # root-flagged ones, so this is the user whose Steam library we should read.
    return os.environ.get("DECKY_USER") or ""


def user_home():
    # A root-flagged plugin runs with HOME=/root, so Path.home() points at root's
    # home rather than the Steam user's. DECKY_USER_HOME is the host user's home
    # regardless of the flag; fall back to the account lookup, then to $HOME.
    env = os.environ.get("DECKY_USER_HOME")
    if env:
        return Path(env)
    name = user_name()
    if name:
        try:
            return Path(pwd.getpwnam(name).pw_dir)
        except KeyError:
            pass
    return Path.home()
