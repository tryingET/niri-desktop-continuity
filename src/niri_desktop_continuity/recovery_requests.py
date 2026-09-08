"""Closed coordinator request schemas, shared with reviewed endpoint implementations."""

from .model import digest
from .recovery_protocol import (
    CONTRACT,
    VERSION,
    VERSION2,
    fields,
    hexkey,
    keys,
    require,
    sequence,
    version,
)


def selection(value):
    fields(
        value, ("window_ids", "pids", "app_id", "version", "requested_window_ids", "requested_pids")
    )
    for name in ("window_ids", "pids", "requested_window_ids", "requested_pids"):
        values = sequence(value[name])
        require(all(type(v) is int and 0 < v < 2**63 for v in values))
        require(values == sorted(set(values)))
    for name in ("app_id", "version"):
        require(value[name] is None or (type(value[name]) is str and len(value[name]) <= 256))


def admitted(value, *, initial=False):
    fields(
        value,
        (
            "snapshot_digest",
            "identity_digest",
            "state_fingerprint",
            "focus_digest",
            "selection",
            "omission_pins",
            "private_ref",
        ),
    )
    for name in ("snapshot_digest", "identity_digest", "state_fingerprint", "focus_digest"):
        hexkey(value[name])
    selection(value["selection"])
    keys(value["omission_pins"])
    if initial:
        require(value["private_ref"] is None)
    else:
        hexkey(value["private_ref"])


def request_payload(phase, value, *, profile_digest, expires_at, schema=VERSION):
    version(schema)
    if phase in ("observe", "admit"):
        require(expires_at is None)
        admitted(value, initial=phase == "observe")
        return
    names = ("attempt_digest", "plan_digest", "admitted")
    fields(value, (*names, "approval") if phase == "execute" else names)
    hexkey(value["attempt_digest"])
    hexkey(value["plan_digest"])
    admitted(value["admitted"])
    if phase == "execute":
        approval = value["approval"]
        fields(
            approval,
            (
                "schema",
                "plan_digest",
                "expires_at",
                "scope",
                "profile_digest",
                "accepted_omissions",
            )
            + (("accepted_utility_limits",) if schema == VERSION2 else ()),
        )
        require(
            approval["schema"] == schema
            and approval["scope"] == CONTRACT
            and approval["profile_digest"] == profile_digest
            and approval["expires_at"] == expires_at
            and approval["plan_digest"] == value["plan_digest"]
            and approval["accepted_omissions"] == value["admitted"]["omission_pins"]
            and digest(approval) == value["attempt_digest"]
        )
    else:
        require(expires_at is None)
    if phase == "execute" and schema == VERSION2:
        keys(approval["accepted_utility_limits"])
