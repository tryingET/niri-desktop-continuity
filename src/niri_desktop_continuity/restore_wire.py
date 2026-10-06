"""Closed, bounded one-use bootstrap frames; every byte shares one monotonic deadline."""

from __future__ import annotations

import json
import math
import os
import socket
import struct
import time

MAX_FRAME = 128 * 1024


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if not math.isfinite(value) or value <= 0 or value > 300:
        raise TimeoutError("bootstrap absolute deadline exceeded or invalid")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate bootstrap field")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("nonfinite bootstrap number")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite bootstrap number")
    return value


def closed(value: dict, fields: set[str], kind: str):
    if not isinstance(value, dict) or set(value) != fields | {"type"} or value["type"] != kind:
        raise ValueError("unexpected bootstrap frame")


def send(connection, value: dict, deadline: float, check=lambda: None):
    body = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    if len(body) > MAX_FRAME:
        raise ValueError("bootstrap frame too large")
    data = memoryview(struct.pack("!I", len(body)) + body)
    while data:
        check()
        connection.settimeout(remaining(deadline))
        size = connection.send(data)
        remaining(deadline)
        check()
        remaining(deadline)
        if size == 0:
            raise EOFError("bootstrap disconnected")
        data = data[size:]


def receive(connection, deadline: float, check=lambda: None) -> dict:
    def read(size):
        parts = bytearray()
        while len(parts) < size:
            check()
            connection.settimeout(remaining(deadline))
            block = connection.recv(size - len(parts))
            remaining(deadline)
            check()
            remaining(deadline)
            if not block:
                raise EOFError("bootstrap disconnected before complete frame")
            parts.extend(block)
        return bytes(parts)

    size = struct.unpack("!I", read(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError("bootstrap frame size refused")
    value = json.loads(
        read(size), object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_finite_float
    )
    check()
    remaining(deadline)
    if not isinstance(value, dict):
        raise ValueError("bootstrap object required")
    return value


def peer_pid(connection, expected: int | None = None) -> int:
    pid, uid, _ = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    )
    if uid != os.getuid() or pid <= 0 or (expected is not None and expected != pid):
        raise ValueError("bootstrap peer credentials refused")
    return pid
