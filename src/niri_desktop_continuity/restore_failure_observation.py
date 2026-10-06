"""Interrupted-only protected-size evidence. Never an executable state or admission input."""

import json
import math
import time

from .restore_state import fields

SCHEMA = "restore-protected-dimensions.v1"
PHASES = {"proofs", "fresh", "postcondition", "association", "association-baseline"}
QUERIES = ("windows", "workspaces", "outputs")
SIZES = ("tile_size", "window_size")
MAX_INT = 2**63 - 1
MAX_SIZE = 1_000_000_000
MAX_BYTES = 512 * 1024
UNAVAILABLE = '{"schema":"restore-protected-dimensions.v1","unavailable":true}'


def integer(value):
    return type(value) is int and 0 <= value <= MAX_INT


def clock():
    # Normal reads can admit effects: cancellation/faults must propagate.
    value = time.monotonic_ns()
    return value if integer(value) else None


def refusal_clock():
    # Only after the protected-dimension veto: preserve refusal, never admit effects.
    try:
        return clock()
    except BaseException:  # noqa: BLE001
        return None


def pair(value, *, delta=False):
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid diagnostic dimension")
    for n in value:
        if (
            type(n) not in (int, float)
            or not -MAX_SIZE <= n <= MAX_SIZE
            or not math.isfinite(n)
            or (not delta and n <= 0)
        ):
            raise ValueError("diagnostic dimension outside bound")


def difference(before, rejected):
    return None if before is None or rejected is None else [b - a for a, b in zip(before, rejected)]


def validate(value):
    """Closed diagnostic decoder; not a restore-state/history/disposition decoder."""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("unknown protected-size diagnostic")
    if "unavailable" in value:
        fields(value, "schema unavailable")
        if value["unavailable"] is not True:
            raise ValueError("invalid diagnostic availability")
        return
    fields(value, "schema phase refusal_check_ns queries_ns sample changes unobserved")
    if (
        not isinstance(value["phase"], str)
        or value["phase"] not in PHASES
        or value["unobserved"] != ["fullscreen", "work_area", "layers"]
    ):
        raise ValueError("invalid diagnostic phase or coverage")
    checked = value["refusal_check_ns"]
    if checked is not None and not integer(checked):
        raise ValueError("invalid diagnostic clock")
    fields(value["queries_ns"], "windows workspaces outputs")
    previous = 0
    for name in QUERIES:
        interval = value["queries_ns"][name]
        if interval is None:
            continue
        if (
            not isinstance(interval, list)
            or len(interval) != 2
            or not all(integer(n) for n in interval)
            or not previous <= interval[0] <= interval[1]
            or (checked is not None and interval[1] > checked)
        ):
            raise ValueError("invalid diagnostic query interval")
        previous = interval[1]
    sample = value["sample"]
    if not isinstance(sample, list) or not 1 <= len(sample) <= 512:
        raise ValueError("invalid diagnostic sample bound")
    windows = {}
    for row in sample:
        fields(row, "id protected tile_size window_size")
        if not integer(row["id"]) or row["id"] in windows or type(row["protected"]) is not bool:
            raise ValueError("invalid diagnostic window")
        for field in SIZES:
            pair(row[field])
        windows[row["id"]] = row
    changes = value["changes"]
    if not isinstance(changes, list) or not 1 <= len(changes) <= 1024:
        raise ValueError("invalid diagnostic changes bound")
    seen = set()
    for change in changes:
        fields(change, "id field before rejected delta")
        wid, field = change["id"], change["field"]
        if not integer(wid) or field not in SIZES or (wid, field) in seen:
            raise ValueError("invalid diagnostic change")
        seen.add((wid, field))
        row = windows.get(wid)
        if row is None or not row["protected"] or row[field] != change["rejected"]:
            raise ValueError("unbound diagnostic change")
        pair(change["before"])
        pair(change["rejected"])
        pair(change["delta"], delta=True)
        if change["before"] == change["rejected"] or change["delta"] != difference(
            change["before"], change["rejected"]
        ):
            raise ValueError("invalid diagnostic difference")


def project(state, protected, phase, queries, checked):
    if len(state[0]) > 512 or len(protected) > 512:
        raise ValueError("diagnostic window bound")
    sample, changes = [], []
    for wid, window in sorted(state[0].items()):
        sizes = {field: window.get("layout", {}).get(field) for field in SIZES}
        sample.append({"id": wid, "protected": wid in protected, **sizes})
        if wid not in protected:
            continue
        for field in SIZES:
            before = protected[wid].get("layout", {}).get(field)
            rejected = sizes[field]
            # Check ranges before doing arithmetic, including enormous integers.
            pair(before)
            pair(rejected)
            if before != rejected:
                changes.append(
                    {
                        "id": wid,
                        "field": field,
                        "before": before,
                        "rejected": rejected,
                        "delta": difference(before, rejected),
                    }
                )
    value = {
        "schema": SCHEMA,
        "phase": phase,
        "refusal_check_ns": checked,
        "queries_ns": queries,
        "sample": sample,
        "changes": changes,
        "unobserved": ["fullscreen", "work_area", "layers"],
    }
    validate(value)
    encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    if len(encoded) > MAX_BYTES:  # ASCII-only closed projection
        raise ValueError("diagnostic byte bound")
    return encoded


class FailureObservation:
    def __init__(self):
        self.first = None  # immutable serialized projection; never a reference to live state
        self.start_sample()

    def start_sample(self):
        self.state = None
        self.queries = dict.fromkeys(QUERIES)

    def query(self, name, method, *args, **kwargs):
        start = clock()
        try:
            value = method(*args, **kwargs)
        except BaseException:
            # Already unwinding: secondary timing must not replace the callback error.
            try:
                self.end_query(name, start)
            except BaseException:  # noqa: BLE001
                pass
            raise
        self.end_query(name, start)  # successful callback: timing faults still veto effects
        return value

    def end_query(self, name, start):
        end = clock()
        self.queries[name] = (
            [start, end] if start is not None and end is not None and start <= end else None
        )

    def bind(self, state):
        self.state = state
        return state

    def reject(self, state, protected, phase):
        if self.first is not None:
            return
        self.first = UNAVAILABLE  # latch even if projection fails; never retry using fallback
        try:
            checked = refusal_clock()
            queries = self.queries if state is self.state else dict.fromkeys(QUERIES)
            self.first = project(state, protected, phase, queries, checked)
        except BaseException:  # noqa: BLE001 - diagnostic failure cannot replace refusal
            pass

    def export(self):
        if self.first is None:
            return None
        try:
            if len(self.first) > MAX_BYTES:
                raise ValueError("diagnostic byte bound")
            value = json.loads(self.first)
            validate(value)
            return value
        except BaseException:  # noqa: BLE001 - retain the original exception/accounting
            return {"schema": SCHEMA, "unavailable": True}
