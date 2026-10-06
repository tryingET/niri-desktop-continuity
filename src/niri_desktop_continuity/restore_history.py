"""Closed append-only restore history. Missing original evidence never grants effects."""

from __future__ import annotations

import json
import os

from . import restore_records as records
from .model import digest
from .store import check_file, private_directory, sync_directory

SCHEMA = "desktop-continuity.restore-history.v3"
LIMIT = 4096
TYPES = {
    "prepared",
    "intent",
    "observed",
    "association",
    "final-observed",
    "terminal",
    "operator-disposition",
}
ACTIONS = {"bootstrap", "exec", "layout"}
ACCOUNTED = {"placed", "already-open", "unsupported"}


def fence_path(identity):
    from .operation_lock import runtime_root

    pin = {k: identity.get(k) for k in ("boot_id", "socket_device", "socket_inode")}
    return runtime_root() / "niri-desktop-continuity-locks" / f"{digest(pin)}.restore"


def directory_pin(path):
    private_directory(path, create=False)
    info = path.stat()
    return {"device": info.st_dev, "inode": info.st_ino}


def durable_create(path, record):
    data = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("restore history exceeds bound")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def read(path):
    from .restore_wire import _finite_float, _nonfinite, _pairs

    check_file(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        value = json.load(
            stream, object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_finite_float
        )
    # digest rejects overflow floats too.
    digest(value)
    return value


def terminal_valid(receipt, plan):
    if set(receipt) != {"status", "windows", "effects", "final_observation", "native_session"}:
        raise ValueError("unknown terminal receipt fields")
    rows = receipt["windows"]
    if not isinstance(rows, list) or len(rows) != len(plan["entries"]):
        raise ValueError("incomplete terminal accounting")
    for row, entry in zip(rows, plan["entries"], strict=True):
        if row.get("entry") != entry or row.get("status") not in ACCOUNTED:
            raise ValueError("unaccounted terminal entry")
    expected = "reopened" if all(r["status"] != "unsupported" for r in rows) else "partial"
    if receipt["status"] != expected or receipt["native_session"] != "not-proved":
        raise ValueError("invalid terminal outcome")
    if not isinstance(receipt["final_observation"], dict):
        raise ValueError("missing final observation")


def validate(identity, chain, *, reader=None, expected=()):
    readers = {getattr(row[2], "reader", None) for row in chain} - {None}
    if reader is not None:
        readers.add(reader)
    try:
        return _validate(identity, chain, reader=reader, expected=expected)
    except BaseException:
        for value in readers:
            value.close()
        raise


def _validate(identity, chain, *, reader=None, expected=()):
    """Sequential semantic pass over an already structurally validated chain; NEVER load recursively."""
    from .restore_disposition_dependencies import Bindings, artifact
    from .restore_retained import pending_width

    completed, active, pending, previous = [], None, None, None
    closure = Bindings()
    for seq, (record, payload, store, record_pins) in enumerate(chain):
        if active is not None:
            active["_prefix_pins"] = closure.manifest()
        origin = record["origin"]
        if record["type"] == "prepared":
            if active is not None or set(payload) != {"identity", "snapshot_digest", "plan"}:
                raise ValueError("overlapping or invalid preparation")
            if payload["identity"] != identity or not isinstance(payload["plan"]["entries"], list):
                raise ValueError("foreign history")
            snapshot, source_pin = artifact(store, "snapshots", payload["snapshot_digest"])
            closure.add(source_pin)
            active = {
                **payload,
                "attempt": record["attempt"],
                "origin": origin,
                "_launches": records.prepared(payload["plan"], snapshot, identity),
                "_start": seq,
                "_prior_sources": [v["snapshot_digest"] for v in completed],
                "_prior_attempts": [v["attempt"] for v in completed],
                "_prior_processes": [
                    p["process"] for v in completed for p in v["_launches"]["launches"].values()
                ],
            }
        else:
            if (
                active is None
                or record["attempt"] != active["attempt"]
                or origin != active["origin"]
            ):
                raise ValueError("orphan history record")
            if record["type"] == "intent":
                if (
                    pending is not None
                    or set(payload) != {"action", "details"}
                    or payload["action"] not in ACTIONS
                ):
                    raise ValueError("overlapping or unknown effect intent")
                try:
                    records.intent(payload, active["plan"], active["_launches"])
                except ValueError as strict_error:
                    try:
                        pending_width(payload, active, chain, seq)
                    except (ValueError, KeyError, TypeError, StopIteration):
                        raise strict_error from None
                pending = (record["receipt"], payload)
            elif record["type"] == "operator-disposition":
                if payload.get("schema") == "desktop-continuity.restore-disposition.v3":
                    from .restore_exited_model import committed
                elif payload.get("schema") == "desktop-continuity.restore-disposition.v2":
                    from .restore_disposition_v2_model import committed
                elif payload.get("schema") == "desktop-continuity.restore-disposition.v1":
                    from .restore_disposition import committed
                else:
                    raise ValueError("unknown disposition schema")

                result, barriers = committed(
                    store, payload, active, pending, chain[:seq], chain[seq]
                )
                completed.append(
                    {
                        **active,
                        "receipt_digest": record["receipt"],
                        "result": result,
                        "_durability": barriers,
                    }
                )
                closure.extend(barriers)
                active, pending = None, None
            elif record["type"] == "observed":
                if active.get("retained_pending") is not None:
                    raise ValueError("retained invalid action cannot gain an observation")
                if (
                    set(payload) != {"intent", "evidence"}
                    or pending is None
                    or payload["intent"] != pending[0]
                ):
                    raise ValueError("orphan effect observation")
                records.observed(payload, pending[1], active["_launches"])
                if pending[1]["action"] == "exec":
                    evidence = payload["evidence"]
                    process, process_pin = artifact(store, "receipts", digest(evidence))
                    closure.add(process_pin)
                    if process != evidence:
                        raise ValueError("missing or inconsistent process receipt")
                pending = None
            elif record["type"] == "association":
                if pending is not None:
                    raise ValueError("association while effect remains unobserved")
                records.association(payload, active["plan"], active["_launches"])
            elif record["type"] == "final-observed":
                if pending is not None:
                    raise ValueError("final observation with outstanding effect")
                records.final_observed(payload, active["plan"], active["_launches"])
            else:
                if pending is not None:
                    raise ValueError("terminal with outstanding effect")
                terminal_valid(payload, active["plan"])
                records.terminal(payload, active["plan"], active["_launches"])
                completed.append({**active, "receipt_digest": record["receipt"], "result": payload})
                active = None
        closure.extend(record_pins)
        if record["type"] in {"terminal", "operator-disposition"}:
            completed[-1]["_evidence"] = closure.manifest()
        previous = digest(record)
    if active is not None:
        active["_prefix_pins"] = closure.manifest()
        active["_pending"] = pending[0] if pending else None
    closure.require(expected)
    if reader is not None:
        closure.exact(reader.manifest())
    return completed, active, len(chain), previous


def load(identity, *, strict=False, reader=None, expected=()):
    """Pure validation under flock, NOT durability or writer admission; see admit()."""
    from .restore_retained import structural

    try:
        chain = structural(identity, strict=strict, reader=reader, expected=expected)
        return validate(identity, chain, expected=expected)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        StopIteration,
    ) as exc:
        raise ValueError("unresolved restore history is damaged or incomplete") from exc


def admit(identity, *, expected=()):
    """Under the SAME exclusive flock: validate, establish barriers, verify unchanged evidence.

    Re-establishing durability of an already approved/consumed exact record is historical
    accounting recovery, never a new disposition or a claim the original apply succeeded.
    """
    from .store import sync_artifact

    validated = load(identity, expected=expected)
    if validated[1] is not None:
        raise ValueError("unresolved restore attempt fences this compositor; no action taken")
    pins = [pin for item in validated[0] for pin in item.get("_durability", [])]
    if pins:
        try:
            for pin in pins:
                sync_artifact(pin)
            all_pins = validated[0][-1]["_evidence"] if validated[0] else []
            if load(identity, expected=all_pins) != validated:
                raise ValueError("disposition evidence changed across durability barriers")
        except (OSError, ValueError) as exc:
            raise ValueError("unresolved restore durability or evidence; no admission") from exc
    return validated


def require_clear(identity):
    admit(identity)
