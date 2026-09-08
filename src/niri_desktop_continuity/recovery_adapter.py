"""Pinned internal subprocess transport; broken IPC cancels authority, never kills or retries."""

from __future__ import annotations

import socket
import subprocess
from datetime import datetime, timezone

from .model import digest
from .recovery_profile import load_profile
from .recovery_protocol import (
    COUNT,
    LIMIT,
    PHASES,
    decode_frame,
    encode,
    envelope,
    fields,
    hexkey,
    require,
)
from .recovery_requests import request_payload

# This is a protocol liveness lease, not a subprocess execution timeout.
LIVENESS_SECONDS = 5


def unexpired(expires_at):
    expires = datetime.fromisoformat(expires_at)
    require(expires.tzinfo is not None and datetime.now(timezone.utc) < expires)


class Adapter:
    def __init__(self, profile):
        self.profile = profile
        self.key = digest(profile)
        self.events = []

    def call(self, phase, payload, *, lock_fd=None, expires_at=None, journal=None):
        require(phase in PHASES)
        require((phase == "execute") == (lock_fd is not None))
        require(lock_fd is None or (type(lock_fd) is int and lock_fd >= 0))
        require(phase != "execute" or (expires_at is not None and journal is not None))
        request_payload(
            phase,
            payload,
            profile_digest=self.key,
            expires_at=expires_at,
            schema=self.profile["schema"],
        )
        # Independently validate every file before *every* phase, not endpoint self-report.
        load_profile(expected=self.key)
        if expires_at is not None:
            unexpired(expires_at)
        parent, child = socket.socketpair()
        parent.settimeout(LIVENESS_SECONDS)
        request = {
            "protocol": self.profile["schema"],
            "phase": phase,
            "profile_digest": self.key,
            "payload": payload,
            "expires_at": expires_at,
            "lock_fd": lock_fd,
            "liveness_seconds": LIVENESS_SECONDS,
        }
        process = None
        self.events = []
        try:
            process = subprocess.Popen(
                [self.profile["interpreter"]["path"], "-I", "-S", self.profile["endpoint"]["path"]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={"NDC_RECOVERY_FD": str(child.fileno())},
                pass_fds=(child.fileno(),) if lock_fd is None else (child.fileno(), lock_fd),
                close_fds=True,
                start_new_session=True,
            )
            child.close()
            parent.sendall(encode(request))
            with parent.makefile("rb") as reader:
                pending = None
                while True:
                    raw = reader.readline(LIMIT + 2)
                    kind, body = envelope(decode_frame(raw), request)
                    reply = {
                        "protocol": self.profile["schema"],
                        "request_digest": digest(request),
                        "phase": phase,
                        "type": "continue",
                        "body": {},
                    }
                    if kind == "result":
                        require(pending is None)
                        # Exactly one final frame; no trailing messages, with bounded EOF wait.
                        require(reader.read(1) == b"")
                        break
                    if kind == "heartbeat":
                        require(pending is None)
                        fields(body, ())
                    elif kind == "effect":
                        require(phase == "execute" and pending is None)
                        fields(body, ("sequence", "kind", "intent_ref"))
                        require(
                            type(body["sequence"]) is int
                            and body["sequence"] == len(self.events)
                            and body["sequence"] < COUNT
                        )
                        require(body["kind"] in ("shutdown", "service", "launch", "layout"))
                        hexkey(body["intent_ref"])
                        unexpired(expires_at)
                        pending = body
                        journal("intent", body)  # fsync before issuing one bounded effect permit
                        reply["type"] = "permit"
                        reply["body"] = {**body, "expires_at": expires_at}
                    elif kind == "effect-result":
                        require(phase == "execute" and pending is not None)
                        fields(body, ("sequence", "intent_ref", "outcome", "evidence_ref"))
                        require(
                            type(body["sequence"]) is int
                            and body["sequence"] == pending["sequence"]
                            and body["intent_ref"] == pending["intent_ref"]
                        )
                        require(body["outcome"] in ("observed", "indeterminate"))
                        hexkey(body["evidence_ref"])
                        journal("result", body)
                        self.events.append(body)
                        pending = None
                        require(body["outcome"] == "observed")
                    if expires_at is not None:
                        unexpired(expires_at)
                    parent.sendall(encode(reply))
            require(process.wait() == 0)
            return body
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            raise ValueError("reconstruction adapter failed; no retry authorized") from None
        finally:
            # Closing is cancellation. A reviewed worker stops new effects on EOF/lease loss.
            # Do NOT use Popen as a context manager, run(timeout), terminate, kill or cleanup.
            parent.close()
            child.close()
            if process is not None:
                # Retain caller's lock until the worker exits; it retains its own inherited
                # copy on coordinator death. A defective worker can block: no forced repair.
                process.wait()
