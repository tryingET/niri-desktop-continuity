"""Observe-only isolated socket transport. No permits, inherited locks, kill, or retry."""

import socket
import subprocess
import time

from .model import digest
from .recovery_adapter import unexpired
from .recovery_protocol import LIMIT, decode_frame, encode, fields, require
from .resolution_candidate import admitted
from .resolution_evidence import PROTOCOL
from .resolution_lock import serialized

LEASE = 5


@serialized
def observe(candidate_key, graph_key):
    candidate, _ = admitted(candidate_key)
    observer = candidate["observer"]
    request = {
        "protocol": PROTOCOL,
        "candidate_digest": candidate_key,
        "graph_digest": graph_key,
        "phase": "observe-settlement",
        "expires_at": candidate["expires_at"],
    }
    parent, child = socket.socketpair()
    parent.settimeout(LEASE)
    process = None
    try:
        process = subprocess.Popen(
            [observer["interpreter"]["path"], "-I", "-S", observer["endpoint"]["path"]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"NDC_RESOLUTION_FD": str(child.fileno())},
            pass_fds=(child.fileno(),),
            close_fds=True,
            start_new_session=True,
        )
        child.close()
        parent.sendall(encode(request))
        last = time.monotonic()
        with parent.makefile("rb") as reader:
            while True:
                frame = decode_frame(reader.readline(LIMIT + 2))
                require(time.monotonic() - last < LEASE)
                unexpired(request["expires_at"])
                fields(frame, ("protocol", "request_digest", "type", "body"))
                require(
                    frame["protocol"] == PROTOCOL and frame["request_digest"] == digest(request)
                )
                require(frame["type"] in ("heartbeat", "result"))
                if frame["type"] == "result":
                    require(reader.read(1) == b"")
                    break
                fields(frame["body"], ())
                parent.sendall(
                    encode(
                        {
                            "protocol": PROTOCOL,
                            "request_digest": digest(request),
                            "type": "continue",
                            "body": {},
                        }
                    )
                )
                require(time.monotonic() - last < LEASE)
                last = time.monotonic()
        require(process.wait() == 0)
        admitted(candidate_key)
        unexpired(request["expires_at"])
        return frame["body"]
    finally:
        parent.close()
        child.close()
        if process is not None:
            process.wait()  # Intentionally unbounded after authority closes; never kill a worker.
