"""Explicit offline accounting lifecycle. No launch, layout, retry, pointer or session authority."""

import os
import time
from contextlib import contextmanager

from . import restore_disposition as legacy
from . import restore_disposition_v2_io as io
from . import restore_disposition_v2_model as model
from . import restore_disposition_v2_proof as proof
from . import restore_history as history
from . import restore_retained as retained
from .model import digest
from .operation_lock import operation_lock
from .restore_disposition_dependencies import Bindings
from .restore_disposition_failure import phase, publication_attempted, publication_verified, release
from .restore_reader import DependencyReader, Limits, ReaderStore, same


def projection(store, kind, key, *, expected=()):
    """Non-authoritative schema/identity route. All v2 artifact decoding is reader-mediated."""
    # Fixed one-artifact route preserves the legacy 16-MiB artifact allowance, independent
    # of complete-closure test limits. It never substitutes for a v2 authoritative pass.
    reader = DependencyReader(
        limits=Limits(files=1, raw_bytes=16 * 1024**2, file_bytes=16 * 1024**2)
    )
    primary = None
    try:
        reader.expect(expected)
        return reader.get(store, kind, key)
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [reader.close])


def source(store, identity, attempt, *, expected=()):
    legacy.directories(store)
    chain = retained.structural(identity, strict=True, expected=expected)
    if not chain:
        raise ValueError("missing original attempt")
    reader = chain[-1][2].reader
    try:
        _, active, _, _ = history.validate(identity, chain, reader=reader)
        if (
            active is None
            or active["attempt"] != attempt
            or not same(
                active["origin"],
                {"root": str(store.root), "pin": history.directory_pin(store.root)},
            )
        ):
            raise ValueError("exact unresolved original Store/attempt required")
        model.eligible(active, chain)
        return active, chain, reader
    except BaseException as primary:
        release(primary, [reader.close])
        raise


@contextmanager
def prepared(store, plan_key, approval_key=None, *, expected=()):
    # Learn identity/attempt under the held flock, then bind those FIRST raw observations into
    # the complete sequential pass. This small input pass grants nothing by itself.
    initial = DependencyReader()
    reader = None
    primary = None
    try:
        initial.expect(expected)
        plan = initial.get(store, "plans", plan_key)
        if approval_key is not None:
            approval = initial.get(store, "approvals", approval_key)
        else:
            approval = None
        model.plan_valid(plan, fresh=True)
        first = Bindings([*expected, *initial.manifest()]).manifest()
        active, chain, reader = source(store, plan["identity"], plan["attempt"], expected=first)
        view = ReaderStore(store, reader)
        plan = view.get("plans", plan_key)
        model.historical_binding(view, plan, active, chain)
        if approval_key is not None:
            approval = view.get("approvals", approval_key)
            model.approval_valid(approval, plan, plan_key)
        Bindings(reader.manifest()).require(first)
        model.plan_valid(plan, fresh=True)
        yield active, chain, reader, plan, approval
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [initial.close, *([] if reader is None else [reader.close])])


def inspect(store, identity, attempt, interrupted, client_result, client_exit):
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        from .restore_routing import classify_inspection

        ended, pins = classify_inspection(identity, attempt)
        completed, _, count, tail = (
            history.load(identity, expected=pins) if ended else ([], None, 0, None)
        )
        for item in completed:
            result = item["result"]
            if item["attempt"] != attempt or result.get("schema") != model.SCHEMA:
                continue
            plan = projection(store, "plans", result["plan"], expected=completed[-1]["_evidence"])
            from pathlib import Path

            w = plan["witness"]
            if (
                item["origin"]["root"] != str(store.root)
                or interrupted != w["interrupted"]["digest"]
                or str(Path(client_result).absolute()) != w["client_result"]["path"]
                or str(Path(client_exit).absolute()) != w["client_exit"]["path"]
            ):
                raise ValueError("inspection requires original Store/witnesses")
            return {
                "attempt": attempt,
                "history_count": count,
                "history_tail": tail,
                "canonical": "validated",
                "durability": "unestablished",
                "admission": "not-granted",
                "approval": "not-granted",
                "fresh_native_verification": False,
                "status": model.ACCEPT,
                "desktop_effects": [],
                "retry_authorized": False,
                "family": model.FAMILY,
            }
        active, chain, reader = source(store, identity, attempt, expected=pins)
        primary = None
        try:
            model.binding(
                ReaderStore(store, reader), active, chain, interrupted, client_result, client_exit
            )
            return {
                "attempt": attempt,
                "family": model.FAMILY,
                "eligible_family": True,
                "admission": "not-granted",
                "fresh_native_verification": False,
                "durability": "unestablished",
                "history_count": len(chain),
                "approval": "not-granted",
                "desktop_effects": [],
                "retry_authorized": False,
                "trust": legacy.proof.TRUST,
            }
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [reader.close])


def propose(
    store, identity, attempt, interrupted, client_result, client_exit, *, ttl=300, observer
):
    if type(ttl) is not int or not 1 <= ttl <= 900:
        raise ValueError("disposition TTL must be 1..900 seconds")
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        active, chain, reader = source(store, identity, attempt)
        primary = None
        try:
            bound = model.binding(
                ReaderStore(store, reader), active, chain, interrupted, client_result, client_exit
            )
            with proof.current(active, chain, observer) as (current, validate):
                created = int(time.time())
                plan = {
                    "schema": model.SCHEMA,
                    "intent": "restore-disposition",
                    "created": created,
                    "expires": created + ttl,
                    **bound,
                    "current": current,
                    "limits": model.LIMITS,
                }
                model.plan_valid(plan, fresh=True)
                pins = reader.barriers()
                reader, chain, _ = io.fresh_chain(identity, chain, pins)
                validate()
                model.plan_valid(plan, fresh=True)
                reader.reserve_commit(
                    [(store.path("plans", digest(plan)), io.encoded(plan, kind="artifact"))],
                    history_count=len(chain),
                )
                key = io.put(store, reader, "plans", plan)
                pins = reader.barriers()
                reader, _, _ = io.fresh_chain(identity, chain, pins)
                validate()
                model.plan_valid(plan, fresh=True)
                return {
                    "plan_digest": key,
                    "approval": "not-granted",
                    "desktop_effects": [],
                    "retry_authorized": False,
                }
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [reader.close])


def approve(store, plan_key, *, confirmation, acceptance, attest_client_returned, observer):
    if confirmation != plan_key or acceptance != model.ACCEPT or attest_client_returned is not True:
        raise ValueError(
            "exact plan, literal partial acceptance and original witness attestation required"
        )
    hint = projection(store, "plans", plan_key)
    with operation_lock(
        hint["identity"], effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        with prepared(store, plan_key) as (active, chain, reader, plan, _):
            with proof.current(
                active, chain, observer, recorded_controllers=plan["current"]["controller_pids"]
            ) as (current, validate):
                if not same(current, plan["current"]):
                    raise ValueError("current proof differs from reviewed plan")
                approval = {
                    "schema": model.SCHEMA,
                    "family": model.FAMILY,
                    "intent": "restore-disposition",
                    "plan": plan_key,
                    "confirmation": confirmation,
                    "acceptance": acceptance,
                    "attest_client_returned": True,
                    "created": int(time.time()),
                    "expires": plan["expires"],
                }
                model.approval_valid(approval, plan, plan_key)
                pins = reader.barriers()
                with prepared(store, plan_key, expected=pins) as (_, _, fresh, _, _):
                    validate()
                    model.plan_valid(plan, fresh=True)
                    fresh.reserve_commit(
                        [
                            (
                                store.path("approvals", digest(approval)),
                                io.encoded(approval, kind="artifact"),
                            )
                        ],
                        history_count=len(chain),
                    )
                    key = io.put(store, fresh, "approvals", approval)
                    pins = fresh.barriers()
                with prepared(store, plan_key, key, expected=pins):
                    validate()
                    model.plan_valid(plan, fresh=True)
                return {"approval_digest": key, "desktop_effects": []}


def apply(store, approval_key, *, observer):
    approval = projection(store, "approvals", approval_key)
    plan_key = approval["plan"]
    hint = projection(store, "plans", plan_key)
    identity = hint["identity"]
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        # Bounded, reader-mediated candidate-ending probe BEFORE choosing active strict
        # validation versus normal per-v2-prefix replay. Never eagerly parse a legacy suffix
        # merely to discover that a new active v2 proposal needs the cumulative budget.
        first = DependencyReader()
        primary = None
        try:
            actual_approval = first.get(store, "approvals", approval_key)
            actual_plan = first.get(store, "plans", plan_key)
            model.plan_valid(actual_plan, fresh=False)
            model.approval_valid(actual_approval, actual_plan, plan_key)
            ending = history.fence_path(identity) / f"{actual_plan['history_count']:08d}.json"
            replay = os.path.lexists(ending)
            if replay:
                record, _ = first.evidence(ending)
                if (
                    record.get("type") != "operator-disposition"
                    or record.get("attempt") != actual_plan["attempt"]
                    or not same(record.get("origin"), actual_plan["origin"])
                ):
                    raise ValueError("proposed segment already has another ending")
                result = first.get(store, "receipts", record["receipt"])
                if (
                    result.get("schema") != model.SCHEMA
                    or result.get("approval") != approval_key
                    or result.get("plan") != plan_key
                ):
                    raise ValueError("not the exact completed disposition")
            pins = first.manifest()
        except BaseException as failure:
            primary = failure
            raise
        finally:
            release(primary, [first.close])
        if replay:
            completed, _, _, _ = history.admit(identity, expected=pins)
            item = next(v for v in completed if v["result"].get("approval") == approval_key)
            if item["origin"]["root"] != str(store.root):
                raise ValueError("replay requires original Store")
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
            with proof.current(
                active, chain, observer, recorded_controllers=plan["current"]["controller_pids"]
            ) as (current, validate):
                if not same(current, plan["current"]):
                    raise ValueError("current proof differs from approved plan")
                pins = reader.barriers()
                with prepared(store, plan_key, approval_key, expected=pins) as (
                    _,
                    chain,
                    fresh,
                    _,
                    _,
                ):
                    return publish(
                        store, fresh, chain, active, plan, plan_key, approval_key, validate
                    )


def publish(store, reader, chain, active, plan, plan_key, approval_key, validate):
    receipt = model.receipt(plan_key, approval_key, plan, active)
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
        raise ValueError("incomplete or consumed disposition; never repair or retry")
    validate()
    model.plan_valid(plan, fresh=True)
    reader.reserve_commit(future, history_count=len(chain))
    # The EXISTING .pending staging mechanism fences even a pre-receipt crash, including
    # attempts to use a different approval. It is NOT a second authority/acknowledgement.
    history.durable_create(staged, record)
    actual, _ = reader.evidence(staged)
    if not same(actual, record):
        raise ValueError("staged ending differs")
    pins = reader.barriers()
    reader, chain, _ = io.fresh_chain(plan["identity"], chain, pins)
    primary = None
    try:
        validate()
        model.plan_valid(plan, fresh=True)
        stage_valid(path, staged, len(chain))
        # LAST complete capacity check. Stage and canonical are the SAME ending role under
        # a controlled rename across separate passes, not two simultaneously live artifacts.
        # Existing actual bytes + exact future used/receipt bytes; no expanded dependencies
        # before consume. Its internal approval read is mediated by the already bound reader.
        reader.reserve_commit(future, history_count=len(chain))
        validate()  # Capacity/dependency IO may be slow: fresh live veto immediately before consume.
        model.plan_valid(plan, fresh=True)
        io.WriterView(store, reader).consume(approval_key, used)
        reader.artifact(store, "used", approval_key)
        io.put(store, reader, "receipts", receipt)
        pins = reader.barriers()
        reader, _, _ = io.fresh_chain(plan["identity"], chain, pins, staged=(store, staged))
        validate()  # LAST live veto after ALL stage barriers; never at context exit.
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
        # Explicit stage-to-canonical path substitution ONLY; preserve every other pin field.
        pins = [{**p, "path": str(path)} if p["path"] == str(staged) else p for p in pins]
        with phase("admission"):
            history.admit(plan["identity"], expected=pins)
            publication_verified()
        return {
            **receipt,
            "receipt_digest": key,
            "effects": [],
            "historical": False,
            "durability": "established-now",
        }
    except BaseException as failure:
        primary = failure
        raise
    finally:
        release(primary, [] if reader is None else [reader.close])


def stage_valid(path, staged, count):
    expected = {f"{i:08d}.json" for i in range(count)} | {staged.name}
    if os.path.lexists(path.parent.with_suffix(".permit")):
        raise ValueError("legacy permit appeared")
    with os.scandir(path.parent) as entries:
        actual = set()
        for entry in entries:
            actual.add(entry.name)
            if len(actual) > len(expected):
                raise ValueError("history names changed while staging")
    if actual != expected:
        raise ValueError("history names changed while staging")
