"""Thin client for the y700-charged control socket."""

import json
import socket

SOCKET_PATH = "/run/y700-charge.sock"
TIMEOUT = 5.0


def _call(request):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        sock.close()
    response = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    if "error" in response:
        raise RuntimeError(response["error"])
    return response


def get_state():
    return _call({"op": "get"})


def set_state(bypass=None, protection=None, threshold=None):
    request = {"op": "set"}
    if bypass is not None:
        request["bypass"] = bool(bypass)
    if protection is not None:
        request["protection"] = bool(protection)
    if threshold is not None:
        request["threshold"] = int(threshold)
    return _call(request)
