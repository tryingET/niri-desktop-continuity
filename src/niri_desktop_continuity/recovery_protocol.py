"""Closed, bounded saved-conversation protocol. No native payloads or free-form diagnostics."""

from __future__ import annotations

import json
import math
import re

from .model import digest

VERSION = "desktop-continuity.recovery.v1"
VERSION2 = "desktop-continuity.recovery.v2"
CONTRACT = "saved-conversations-v1"
LIMIT = 1024 * 1024
COUNT = 256
DIMENSIONS = (
    "causal_ownership",
    "new_images",
    "old_tree_exit",
    "service_contract",
    "layout",
    "focus",
    "recovery_labels",
    "temporary_holds",
    "protected_preservation",
)
NATIVE = ("file", "cwd", "runtime", "bootstrap", "surface", "causal_window")
PHASES = {"observe", "admit", "execute", "verify", "inspect"}


class RecoveryRefusal(ValueError):
    """Only static, explicitly allowlisted diagnostics may cross the CLI boundary."""


def require(condition):
    if not condition:
        raise ValueError("reconstruction protocol rejected")


def fields(value, names):
    require(type(value) is dict and set(value) == set(names))
    return value


def hexkey(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    return value


def count(value):
    require(type(value) is int and 0 <= value <= COUNT)
    return value


def sequence(value):
    require(type(value) is list and len(value) <= COUNT)
    return value


def keys(value):
    sequence(value)
    for item in value:
        hexkey(item)
    require(value == sorted(set(value)))
    return value


def boolean(value):
    require(type(value) is bool)


def decode(data):
    require(type(data) is bytes and len(data) <= LIMIT)

    def finite(text):
        value = float(text)
        require(math.isfinite(value))
        return value

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=finite,
            parse_constant=lambda _: require(False),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("reconstruction protocol rejected") from None


def decode_frame(raw):
    require(type(raw) is bytes and raw.endswith(b"\n") and len(raw) <= LIMIT + 1)
    return decode(raw[:-1])  # Exactly the framing LF is excluded from the JSON byte budget.


def encode(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(data) <= LIMIT)
    return data + b"\n"


def process_pin(value):
    fields(value, ("boot_id", "pid", "start_ticks", "exe_sha256", "exe_inode", "exe_device", "uid"))
    require(type(value["boot_id"]) is str and re.fullmatch(r"[A-Za-z0-9-]{1,64}", value["boot_id"]))
    hexkey(value["exe_sha256"])
    for key in ("pid", "start_ticks", "exe_inode", "exe_device", "uid"):
        require(type(value[key]) is int and 0 <= value[key] < 2**63)
    require(all(value[key] > 0 for key in ("pid", "start_ticks", "exe_inode")))


def legacy(value, expected):
    fields(value, ("locations_digest", "complete", "unresolved"))
    require(hexkey(value["locations_digest"]) == expected)
    boolean(value["complete"])
    count(value["unresolved"])
    return value["complete"] and value["unresolved"] == 0


def version(value):
    require(value in (VERSION, VERSION2))
    return value


def successes(schema):
    version(schema)
    return ("verified", "verified-with-accepted-omissions") + (
        ("verified-with-accepted-limitations",) if schema == VERSION2 else ()
    )


def observation(value, legacy_digest, schema=VERSION):
    version(schema)
    fields(
        value,
        (
            "identity_digest",
            "state_fingerprint",
            "focus_digest",
            "private_ref",
            "supported",
            "processes",
            "session_refs",
            "legacy",
        )
        + (("utilities",) if schema == VERSION2 else ()),
    )
    for key in ("identity_digest", "state_fingerprint", "focus_digest", "private_ref"):
        hexkey(value[key])
    boolean(value["supported"])
    keys(value["session_refs"])
    pins, associated = [], set()
    for item in sequence(value["processes"]):
        fields(item, ("pin", "owned", "identity_proved", "protected_overlap", "session_ref"))
        process_pin(item["pin"])
        pins.append(digest(item["pin"]))
        for key in ("owned", "identity_proved", "protected_overlap"):
            boolean(item[key])
        if item["session_ref"] is not None:
            associated.add(hexkey(item["session_ref"]))
    require(pins == sorted(set(pins)))
    require(associated == set(value["session_refs"]))
    if schema == VERSION2:
        from .recovery_utilities import utilities

        utilities(value)
    legacy(value["legacy"], legacy_digest)
    return value


def coverage(value, omissions, schema=VERSION):
    version(schema)
    keys(omissions)
    missing, blockers, associated = set(), [], 0
    if not value["supported"]:
        blockers.append("unsupported-recovery-profile")
    if (not value["processes"] or not value["session_refs"]) and not (
        schema == VERSION2 and value["utilities"]
    ):
        blockers.append("empty-native-selection")
    for item in value["processes"]:
        if not item["owned"] or not item["identity_proved"] or item["protected_overlap"]:
            blockers.append("mandatory-ownership-identity-or-protection-unproved")
        if item["session_ref"] is None:
            missing.add(digest(item["pin"]))
        else:
            associated += 1
    if set(omissions) - missing:
        blockers.append("omission-not-an-exact-missing-association")
    if missing - set(omissions):
        blockers.append("native-session-association-missing")
    counts = {
        "owned_native_processes": len(value["processes"]),
        "associated_processes": associated,
        "omitted_associations": len(omissions),
        "unique_saved_conversations": len(value["session_refs"]),
        "unresolved_associations": len(missing),
    }
    decisions = [
        {
            "process_pin_digest": digest(item["pin"]),
            "pin": item["pin"],
            "reason": "owned-process-native-association-unresolved",
        }
        for item in value["processes"]
        if digest(item["pin"]) in omissions
    ]
    if schema == VERSION2:
        from .recovery_utilities import utility_limits

        counts.update(
            owned_utilities=len(value["utilities"]),
            image_unobservable_utilities=len(utility_limits(value)),
        )
        for item in value["utilities"]:
            if not item["owned"] or not item["identity_proved"] or item["protected_overlap"]:
                blockers.append("mandatory-utility-ownership-identity-or-protection-unproved")
    return counts, decisions, sorted(set(blockers))


def proof(value, session_refs, schema=VERSION, utilities=()):
    version(schema)
    fields(
        value,
        ("dimensions", "native", "interrupted", "unresolved_children")
        + (("utilities",) if schema == VERSION2 else ()),
    )
    fields(value["dimensions"], DIMENSIONS)
    boolean(value["interrupted"])
    count(value["unresolved_children"])
    complete = not value["interrupted"] and value["unresolved_children"] == 0
    for item in value["dimensions"].values():
        fields(item, ("status", "evidence_ref"))
        require(item["status"] in ("proved", "failed", "unknown"))
        if item["evidence_ref"] is not None:
            hexkey(item["evidence_ref"])
        require(item["status"] != "proved" or item["evidence_ref"] is not None)
        complete &= item["status"] == "proved"
    seen = []
    for item in sequence(value["native"]):
        fields(item, ("session_ref", "evidence_ref", *NATIVE))
        seen.append(hexkey(item["session_ref"]))
        hexkey(item["evidence_ref"])
        for key in NATIVE:
            boolean(item[key])
            complete &= item[key]
    require(seen == sorted(set(seen)) and set(seen) <= set(session_refs))
    complete &= seen == session_refs
    if schema == VERSION2:
        from .recovery_utilities import utility_proof

        complete &= utility_proof(value["utilities"], utilities)
    return bool(complete)


def envelope(value, request):
    fields(value, ("protocol", "request_digest", "phase", "type", "body"))
    require(
        value["protocol"] == version(request["protocol"])
        and value["phase"] == request["phase"]
        and value["request_digest"] == digest(request)
    )
    require(value["type"] in ("result", "heartbeat", "effect", "effect-result"))
    return value["type"], value["body"]
