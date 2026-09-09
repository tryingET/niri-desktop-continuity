"""Pinned internal subprocess transport; broken IPC cancels authority, never kills or retries."""

from __future__ import annotations

import socket
import subprocess
import time
from datetime import datetime, timezone

from . import recovery_additive as additive
from .model import digest
from .recovery_profile import load_profile
from .recovery_protocol import (
    ADDITIVE,
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


def heartbeat_reply(body, pending):
    """A correlated keepalive retains one pending permit; it grants no further effect."""
    if pending is None:
        fields(body, ())
        return {}
    fields(body, ("sequence", "intent_ref"))
    require(type(body["sequence"]) is int and body["sequence"] == pending["sequence"])
    require(hexkey(body["intent_ref"]) == pending["intent_ref"])
    return body


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
            last_reply = time.monotonic()
            with parent.makefile("rb") as reader:
                pending = None
                launched, focus_issued = set(), False
                while True:
                    raw = reader.readline(LIMIT + 2)
                    kind, body = envelope(decode_frame(raw), request)
                    # Socket timeouts alone can be extended by partial-frame trickles.
                    # A late complete heartbeat/result never resurrects an expired lease.
                    require(time.monotonic() - last_reply < LIVENESS_SECONDS)
                    if expires_at is not None and (
                        kind != "result" or self.profile["schema"] == ADDITIVE
                    ):
                        # Frozen replacement V/V2 may finish final observation after expiry,
                        # provided all effects already ended. Additive keeps its explicit gate.
                        unexpired(expires_at)
                    reply = {
                        "protocol": self.profile["schema"],
                        "request_digest": digest(request),
                        "phase": phase,
                        "type": "continue",
                        "body": {},
                    }
                    if kind == "result":
                        require(pending is None)
                        if phase == "execute" and self.profile["schema"] == ADDITIVE:
                            additive.complete_effects(payload["admitted"], launched, focus_issued)
                        # Exactly one final frame; no trailing messages, with bounded EOF wait.
                        require(reader.read(1) == b"")
                        break
                    if kind == "heartbeat":
                        # Replacement v1/v2 wire behavior remains frozen.
                        require(pending is None or self.profile["schema"] == ADDITIVE)
                        reply["body"] = heartbeat_reply(body, pending)
                    elif kind == "effect":
                        require(phase == "execute" and pending is None)
                        if self.profile["schema"] == ADDITIVE:
                            focus_issued = additive.effect(
                                body, payload["admitted"], launched, focus_issued=focus_issued
                            )
                        else:
                            fields(body, ("sequence", "kind", "intent_ref"))
                        require(
                            type(body["sequence"]) is int
                            and body["sequence"] == len(self.events)
                            and body["sequence"] < COUNT
                        )
                        if self.profile["schema"] != ADDITIVE:
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
                    packet = encode(reply)
                    remaining = LIVENESS_SECONDS - (time.monotonic() - last_reply)
                    if expires_at is not None:
                        remaining = min(
                            remaining,
                            (
                                datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)
                            ).total_seconds(),
                        )
                    require(remaining > 0)  # Journaling/fsync may have consumed the whole lease.
                    parent.settimeout(remaining)
                    parent.sendall(packet)
                    replied_at = time.monotonic()
                    require(replied_at - last_reply < LIVENESS_SECONDS)
                    if expires_at is not None:
                        unexpired(expires_at)
                    last_reply = replied_at
                    parent.settimeout(LIVENESS_SECONDS)
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
