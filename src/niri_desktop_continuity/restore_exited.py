"""Explicit v3 lifecycle under one existing flock. Accounting only, never desktop effects."""

import os
import time
from contextlib import contextmanager

from . import restore_disposition as legacy
from . import restore_disposition_v2_io as io
from . import restore_exited_history as historical
from . import restore_exited_model as model
from . import restore_exited_proof as proof
from . import restore_exited_values as v
from . import restore_history as history
from . import restore_retained as retained
from .model import digest
from .operation_lock import operation_lock
from .restore_disposition_dependencies import Bindings
from .restore_disposition_failure import (
    guard,
    phase,
    publication_attempted,
    publication_verified,
    release,
)
from .restore_disposition_v2 import stage_valid
from .restore_reader import DependencyReader, Limits, ReaderStore, same


def historical_replay(snapshot, key):
    """Exact v3 source replay may outlive the native endpoint and its caller Store."""
    identity = snapshot.get("identity", {})
    # Only sources with the v3 historical bridge grammar can enter this new route.
    try:
        v.source_valid(snapshot, identity)
    except (ValueError, KeyError, TypeError):
        return None
    if not os.path.lexists(history.fence_path(identity)):
        return None
    with operation_lock(identity, effectful=False, existing_only=True):
        completed, _, _, _ = history.load(identity)
        matches = [
            item
            for item in completed
            if item["snapshot_digest"] == key and item["result"].get("schema") == v.SCHEMA
        ]
        if not matches:
            return None
        history.admit(identity, expected=completed[-1]["_evidence"])
        item = matches[0]
        return {
            "snapshot_digest": key,
            "receipt_digest": item["receipt_digest"],
            **item["result"],
            "historical": True,
            "fresh_native_verification": False,
        }


def route(store, kind, key):
    reader = DependencyReader(limits=Limits(files=1, raw_bytes=16 * 1024**2))
    primary = None
    try:
        return reader.get(store, kind, key), reader.manifest()
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [reader.close])


def hint(store, *, result=None, kind=None, key=None, first=()):
    reader = DependencyReader()
    primary = None
    try:
        reader.expect(first)
        if result is not None:
            body, _ = reader.evidence(v.path(str(result)))
            source = reader.get(store, "snapshots", body["snapshot_digest"])
            v.source_valid(source, source["identity"])
            identity = source["identity"]
        else:
            body = reader.get(store, kind, key)
            model.discriminator(body)
            plan = body if kind == "plans" else reader.get(store, "plans", body["plan"])
            model.plan_valid(plan, fresh=False)
            if not same(
                plan["origin"], {"root": str(store.root), "pin": history.directory_pin(store.root)}
            ):
                raise ValueError("direct disposition requires the original Store")
            identity = plan["identity"]
        return identity, body, reader.manifest()
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [reader.close])


def source(store, identity, attempt, *, expected=()):
    legacy.directories(store)
    chain = retained.structural(identity, strict=True, expected=expected)
    if not chain:
        raise ValueError("missing original history")
    reader = chain[-1][2].reader
    try:
        _, active, _, _ = history.validate(identity, chain, reader=reader)
        if active is None or active["attempt"] != attempt:
            raise ValueError("exact unresolved attempt required")
        historical.eligible(active, chain)
        return active, chain, reader
    except BaseException as primary:
        release(primary, [reader.close])
        raise


@contextmanager
def prepared(store, plan_key, approval_key=None, *, expected=()):
    initial, reader = DependencyReader(), None
    primary = None
    try:
        initial.expect(expected)
        plan = initial.get(store, "plans", plan_key)
        model.plan_valid(plan, fresh=True)
        v.live_method(plan)
        if approval_key is not None:
            initial.get(store, "approvals", approval_key)
        pins = Bindings([*expected, *initial.manifest()]).manifest()
        active, chain, reader = source(store, plan["identity"], plan["attempt"], expected=pins)
        view = ReaderStore(store, reader)
        plan = view.get("plans", plan_key)
        model.historical_binding(view, plan, active, chain)
        approval = None if approval_key is None else view.get("approvals", approval_key)
        if approval is not None:
            model.approval_valid(approval, plan, plan_key)
        Bindings(reader.manifest()).require(pins)
        model.plan_valid(plan, fresh=True)
        yield active, chain, reader, plan, approval
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [initial.close, *([] if reader is None else [reader.close])])


def native(store, reader, active, plan, *, expected=None):
    return proof.current(
        ReaderStore(store, reader).get("snapshots", active["snapshot_digest"]),
        active["_launches"]["launches"][0]["process"],
        active["_launches"]["associations"][0]["id"],
        expires=plan["expires"],
        expected=expected,
    )


def inspect(store, attempt, interrupted, client_result, client_exit):
    identity, _, first = hint(store, result=client_result)
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        from .restore_routing import classify_inspection

        ended, pins = classify_inspection(identity, attempt)
        pins = Bindings([*first, *pins]).manifest()
        if ended:
            completed, _, count, tail = history.load(identity, expected=pins)
            item = next(row for row in completed if row["attempt"] == attempt)
            model.discriminator(item["result"])
            _, plan, observed = hint(store, kind="plans", key=item["result"]["plan"])
            Bindings(completed[-1]["_evidence"]).require(observed)
            w = plan["witness"]
            if (
                plan["origin"]["root"] != str(store.root)
                or w["interrupted"]["digest"] != interrupted
                or w["client_result"]["path"] != str(client_result)
                or w["client_exit"]["path"] != str(client_exit)
            ):
                raise ValueError("exact original Store/witness required")
            return {
                "attempt": attempt,
                "family": v.FAMILY,
                "canonical": "validated",
                "status": v.ACCEPT,
                "history_count": count,
                "history_tail": tail,
                "current_proof": "not-performed",
                "admission": "not-granted",
                "approval": "not-granted",
                "durability": "unestablished",
                "desktop_effects": [],
                "retry_authorized": False,
            }
        active, chain, reader = source(store, identity, attempt, expected=pins)
        primary = None
        try:
            historical.binding(
                ReaderStore(store, reader), active, chain, interrupted, client_result, client_exit
            )
            Bindings(reader.manifest()).require(pins)
            return {
                "attempt": attempt,
                "family": v.FAMILY,
                "eligible_family": True,
                "history_count": len(chain),
                "current_proof": "not-performed",
                "admission": "not-granted",
                "approval": "not-granted",
                "durability": "unestablished",
                "desktop_effects": [],
                "retry_authorized": False,
            }
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [reader.close])


def propose(store, attempt, interrupted, client_result, client_exit, *, ttl=300):
    v.integer(ttl, 1, 900)
    identity, _, first = hint(store, result=client_result)
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        active, chain, reader = source(store, identity, attempt, expected=first)
        primary = None
        try:
            bound = historical.binding(
                ReaderStore(store, reader), active, chain, interrupted, client_result, client_exit
            )
            Bindings(reader.manifest()).require(first)
            created = int(time.time())
            with native(store, reader, active, {"expires": created + ttl}) as (current, validate):
                plan = {
                    "schema": v.SCHEMA,
                    "intent": "restore-disposition",
                    "created": created,
                    "expires": created + ttl,
                    **bound,
                    "platform": v.PLATFORM,
                    "current": current,
                    "limits": v.LIMITS,
                }
                model.historical_binding(ReaderStore(store, reader), plan, active, chain)
                pins = reader.barriers()
                reader, chain, result = io.fresh_chain(identity, chain, pins)
                model.historical_binding(ReaderStore(store, reader), plan, result[1], chain)
                reader.reserve_commit(
                    [(store.path("plans", digest(plan)), io.encoded(plan, kind="artifact"))],
                    history_count=len(chain),
                )
                validate()  # AFTER final capacity/dependency IO, immediately before persistence.
                model.plan_valid(plan, fresh=True)
                key = io.put(store, reader, "plans", plan)
                pins = reader.barriers()
                with prepared(store, key, expected=pins):
                    validate()
                    model.plan_valid(plan, fresh=True)
                return {
                    "plan_digest": key,
                    "platform": plan["platform"],
                    "platform_digest": digest(plan["platform"]),
                    "approval": "not-granted",
                    "desktop_effects": [],
                    "retry_authorized": False,
                }
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [reader.close])


def approve(
    store, plan_key, *, confirmation, acceptance, attest_client_returned, platform_ack, first=()
):
    if confirmation != plan_key or acceptance != v.ACCEPT or attest_client_returned is not True:
        raise ValueError("exact plan and original client attestation required")
    identity, _, first = hint(store, kind="plans", key=plan_key, first=first)
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        with prepared(store, plan_key, expected=first) as (active, chain, reader, plan, _):
            # ubs:ignore[python.ctcompare.secret_eq] -- Public platform ack, not auth.
            if platform_ack != digest(plan["platform"]):
                raise guard("invalid-arguments", "explicit exact platform acknowledgement required")
            with native(store, reader, active, plan, expected=plan["current"]) as (
                current,
                validate,
            ):
                approval = {
                    "schema": v.SCHEMA,
                    "family": v.FAMILY,
                    "branch": v.BRANCH,
                    "intent": "restore-disposition",
                    "plan": plan_key,
                    "confirmation": confirmation,
                    "acceptance": acceptance,
                    "attest_client_returned": True,
                    "platform_ack": platform_ack,
                    "caller": current["caller"],
                    "created": int(time.time()),
                    "expires": plan["expires"],
                }
                model.approval_valid(approval, plan, plan_key)
                pins = reader.barriers()
                with prepared(store, plan_key, expected=pins) as (_, _, fresh, _, _):
                    fresh.reserve_commit(
                        [
                            (
                                store.path("approvals", digest(approval)),
                                io.encoded(approval, kind="artifact"),
                            )
                        ],
                        history_count=len(chain),
                    )
                    validate()
                    model.plan_valid(plan, fresh=True)
                    key = io.put(store, fresh, "approvals", approval)
                    pins = fresh.barriers()
                with prepared(store, plan_key, key, expected=pins):
                    validate()
                    model.plan_valid(plan, fresh=True)
                return {"approval_digest": key, "desktop_effects": []}


def apply(store, approval_key, *, first=()):
    identity, approval, first = hint(store, kind="approvals", key=approval_key, first=first)
    plan_key = approval["plan"]
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        reader = DependencyReader()
        primary = None
        try:
            reader.expect(first)
            approval = reader.get(store, "approvals", approval_key)
            plan = reader.get(store, "plans", plan_key)
            model.plan_valid(plan, fresh=False)
            model.approval_valid(approval, plan, plan_key)
            path = history.fence_path(identity) / f"{plan['history_count']:08d}.json"
            replay = os.path.lexists(path)
            if replay:
                record, _ = reader.evidence(path)
                if (
                    record.get("type") != "operator-disposition"
                    or record.get("attempt") != plan["attempt"]
                    or not same(record.get("origin"), plan["origin"])
                ):
                    raise ValueError("another ending already exists")
                result = reader.get(store, "receipts", record["receipt"])
                model.discriminator(result)
                if result.get("approval") != approval_key or result.get("plan") != plan_key:
                    raise ValueError("not exact completed replay")
            pins = reader.manifest()
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [reader.close])
        if replay:
            completed, _, _, _ = history.admit(identity, expected=pins)
            item = next(row for row in completed if row["result"].get("approval") == approval_key)
            if item["origin"]["root"] != str(store.root):
                raise ValueError("direct replay requires original Store")
            return {
                **item["result"],
                "receipt_digest": item["receipt_digest"],
                "historical": True,
                "durability": "established-now",
            }
        with prepared(store, plan_key, approval_key, expected=pins) as (
            active,
            chain,
            reader,
            plan,
            _,
        ):
            with native(store, reader, active, plan, expected=plan["current"]) as (
                current,
                validate,
            ):
                return publish(
                    store,
                    reader,
                    chain,
                    active,
                    plan,
                    plan_key,
                    approval_key,
                    current["caller"],
                    validate,
                )


def publish(store, reader, chain, active, plan, plan_key, approval_key, caller, validate):
    receipt = model.receipt(plan_key, approval_key, plan, caller)
    key = digest(receipt)
    record = {
        "schema": history.SCHEMA,
        "seq": len(chain),
        "previous": plan["history_tail"],
        "type": "operator-disposition",
        "attempt": plan["attempt"],
        "receipt": key,
        "origin": plan["origin"],
    }
    path = history.fence_path(plan["identity"]) / f"{len(chain):08d}.json"
    staged = path.with_suffix(".pending")
    used = model.consumption(approval_key, plan_key)
    future = [
        (store.path("used", approval_key), io.encoded(used, kind="used")),
        (store.path("receipts", key), io.encoded(receipt, kind="artifact")),
        (staged, io.encoded(record, kind="canonical")),
    ]
    if any(os.path.lexists(p) for p, _ in future) or os.path.lexists(path):
        raise ValueError("staged/consumed attempt cannot be retried")
    reader.reserve_commit(future, history_count=len(chain))
    validate()
    model.plan_valid(plan, fresh=True)
    history.durable_create(staged, record)  # O_EXCL + file AND directory fsync BEFORE consume.
    actual, _ = reader.evidence(staged)
    if not same(actual, record):
        raise ValueError("staged record differs")
    pins = reader.barriers()
    reader, chain, result = io.fresh_chain(plan["identity"], chain, pins)
    primary = None
    try:
        model.historical_binding(ReaderStore(store, reader), plan, result[1], chain)
        model.approval_valid(reader.get(store, "approvals", approval_key), plan, plan_key)
        stage_valid(path, staged, len(chain))
        reader.reserve_commit(future, history_count=len(chain))  # LAST dependency/capacity work.
        validate()
        model.plan_valid(plan, fresh=True)
        io.WriterView(store, reader).consume(approval_key, used)
        reader.artifact(store, "used", approval_key)
        io.put(store, reader, "receipts", receipt)
        pins = reader.barriers()
        reader, _, _ = io.fresh_chain(plan["identity"], chain, pins, staged=(store, staged))
        validate()
        model.plan_valid(plan, fresh=True)
        stage_valid(path, staged, len(chain))
        pins = reader.manifest()
        held, reader = reader, None
        release(None, [held.close])
        with phase("publish"):
            publication_attempted()
            os.rename(staged, path)
        with phase("canonical-directory-sync"):
            history.sync_directory(path.parent)
        pins = [{**p, "path": str(path)} if p["path"] == str(staged) else p for p in pins]
        with phase("admission"):
            history.admit(plan["identity"], expected=pins)
            publication_verified()  # Admission checked the carried staged inode at its new name.
        return {
            **receipt,
            "receipt_digest": key,
            "effects": [],
            "historical": False,
            "historical_effects": active["_launches"]["effects"],
            "historical_rows_receipt": receipt["interrupted_receipt"],
            "fresh_native_verification": False,
            "durability": "established-now",
        }
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [] if reader is None else [reader.close])
