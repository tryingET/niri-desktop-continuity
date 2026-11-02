"""Structural original-byte evidence and ONE pre-fix pending-width family, never executable."""

import re
from copy import deepcopy

from . import restore_geometry as geometry
from . import restore_state as states
from .model import digest
from .store import evidence, json_bytes, raw  # noqa: F401 - names the strict readers still use

PATTERN = [
    "prepared",
    "intent",
    "observed",
    "intent",
    "observed",
    "association",
    "intent",
    "observed",
    "intent",
]


def structural(identity, *, strict=False, limits=None, counters=None, expected=(), reader=None):
    # Compatibility entry point for history.load and retained-width readers. Routing and
    # new-family budgets are separate; no new cap applies to a legacy-only history/suffix.
    from .restore_routing import structural as routed

    return routed(
        identity, strict=strict, limits=limits, counters=counters, expected=expected, reader=reader
    )


def pending_width(payload, active, chain, seq):
    """Validate old float prediction as data WITHOUT feeding a corrected token to execution."""
    if (
        seq != 8
        or [r[0]["type"] for r in chain[:9]] != PATTERN
        or (len(chain) > 9 and chain[9][0]["type"] != "operator-disposition")
        or len(active["plan"]["entries"]) != 1
    ):
        raise ValueError("not the reviewed retained-width prefix")
    tracker = active["_launches"]
    states.fields(payload, "action details")
    details = payload["details"]
    states.fields(details, "argv before expected measured_float target")
    argv = details["argv"]
    if (
        payload["action"] != "layout"
        or not isinstance(argv, list)
        or len(argv) != 2
        or argv[0] != "set-column-width"
        or not isinstance(argv[1], str)
        or not re.fullmatch(r"[1-9][0-9]{0,9}\.0", argv[1])
        or not 0 < float(argv[1]) <= 2147483647
        or details["measured_float"] is not None
        or details["target"] is not None
        or tracker["final"] is not None
        or set(tracker["associations"]) != {0}
        or chain[6][1].get("action") != "layout"
        or chain[6][1]["details"]["argv"][0] != "move-column-to-index"
    ):
        raise ValueError("unsupported retained width family")
    before, expected = states.decode(details["before"]), states.decode(details["expected"])
    if not states.compatible(tracker["state"], before):
        raise ValueError("retained intent differs from strict prefix")
    focused = next(w for w in before[0].values() if w["is_focused"])
    cohort = next(
        g for g in geometry.groups(before[0], focused["workspace_id"]) if focused["id"] in g
    )
    if set(cohort) != tracker["owned"] or len(cohort) != 1:
        raise ValueError("unknown retained cohort")
    predicted = deepcopy(before)
    for wid in cohort:
        layout = predicted[0][wid]["layout"]
        width = float(argv[1])
        layout["tile_size"][0] = width + (layout["tile_size"][0] - layout["window_size"][0])
        layout["window_size"][0] = width
    if states.projected(predicted) != states.projected(expected):
        raise ValueError("invalid historical float prediction")
    states.protected(tracker["baseline"], before, set())
    active["retained_pending"] = chain[seq][0]["receipt"]


def manifest(chain):
    """Every original record and every semantically referenced original artifact, bounded."""
    found = {}
    for record, payload, store, pins in chain:
        for pin in pins:
            found[pin["path"]] = pin
        refs = []
        if record["type"] == "prepared":
            refs.append(("snapshots", payload["snapshot_digest"]))
        if record["type"] == "observed" and payload["evidence"].get("phase") == "process-observed":
            refs.append(("receipts", digest(payload["evidence"])))
        for kind, key in refs:
            from .restore_disposition_dependencies import file

            _, pin = file(store, store.path(kind, key))
            if pin["digest"] != key:
                raise ValueError("referenced artifact mismatch")
            found[pin["path"]] = pin
    return [found[p] for p in sorted(found)]
