"""Explicit disposition-only authority for one reviewed retained ordinary-restore family."""

import os
import time

from . import restore_disposition_evidence as proof
from . import restore_history as history
from . import restore_retained as retained
from . import restore_state as states
from .model import digest
from .operation_lock import operation_lock
from .restore_disposition_failure import phase, publication_attempted
from .store import private_directory, sync_artifact

SCHEMA = "desktop-continuity.restore-disposition.v1"
ACCEPT = "operator-accepted-partial"
LIMITS = {
    "historical_completion": "unproved",
    "pending_outcome": "unresolved",
    "native_session": "not-proved",
    "retry_authorized": False,
    "desktop_effects": [],
    "historical_preservation": "unproved",
    "acceptance": ACCEPT,
    "coverage": "reviewed-prefix-original-witness-current-host-and-topology-only",
}
PLAN_FIELDS = "schema intent created expires attempt identity origin history_count history_tail manifest prepared snapshot pending witness current limits"


def directories(store):
    for kind in ("plans", "approvals", "used", "receipts", "snapshots"):
        private_directory(store.root / kind, create=False)


def source(store, identity, attempt):
    directories(store)
    completed, active, count, tail = history.load(identity)
    chain = retained.structural(identity)
    if (
        completed
        or count != 9
        or active is None
        or active["attempt"] != attempt
        or not active.get("retained_pending")
        or active["origin"] != {"root": str(store.root), "pin": history.directory_pin(store.root)}
    ):
        raise ValueError("exact unresolved reviewed attempt in original Store required")
    return active, chain, count, tail


def binding(store, active, chain, count, tail, interrupted, result_path, exit_path):
    return {
        "attempt": active["attempt"],
        "identity": active["identity"],
        "origin": active["origin"],
        "history_count": count,
        "history_tail": tail,
        "manifest": retained.manifest(chain),
        "prepared": chain[0][0]["receipt"],
        "snapshot": active["snapshot_digest"],
        "pending": active["retained_pending"],
        "witness": proof.witness(store, active, interrupted, result_path, exit_path),
    }


def plan_valid(plan, *, fresh):
    states.fields(plan, PLAN_FIELDS)
    if (
        plan["schema"] != SCHEMA
        or plan["intent"] != "restore-disposition"
        or plan["limits"] != LIMITS
        or type(plan["created"]) is not int
        or type(plan["expires"]) is not int
        or not 1 <= plan["expires"] - plan["created"] <= 900
        or (fresh and not plan["created"] <= time.time() < plan["expires"])
    ):
        raise ValueError("invalid or expired disposition plan")
    value = plan["current"]
    states.fields(
        value, "state owned_window_id protected_window_ids processes running_image argv_digest cwd"
    )
    state = states.decode(value["state"])
    owned = value["owned_window_id"]
    if (
        type(owned) is not int
        or owned not in state[0]
        or value["protected_window_ids"] != sorted(set(state[0]) - {owned})
    ):
        raise ValueError("invalid current ownership partition")
    for pin in value["processes"]:
        history.records.pin(pin)
    if [p["pid"] for p in value["processes"]] != sorted({w["pid"] for w in state[0].values()}):
        raise ValueError("incomplete current process baseline")


def historical_binding(store, plan, active, chain):
    plan_valid(plan, fresh=False)
    witness = plan["witness"]
    actual = binding(
        store,
        active,
        chain,
        len(chain),
        digest(chain[-1][0]),
        witness["interrupted"]["digest"],
        witness["client_result"]["path"],
        witness["client_exit"]["path"],
    )
    if any(plan[k] != v for k, v in actual.items()):
        raise ValueError("original history, artifact bytes or witness drifted")
    bootstrap = chain[1][1]["details"]
    launched = active["_launches"]["launches"][0]["process"]
    current = plan["current"]
    owned_windows = [w["id"] for w in current["state"]["windows"] if w["pid"] == launched["pid"]]
    if (
        current["owned_window_id"] != active["_launches"]["associations"][0]["id"]
        or owned_windows != [current["owned_window_id"]]
        or any(p["boot_id"] != active["identity"]["boot_id"] for p in current["processes"])
        or launched not in current["processes"]
        or current["running_image"] != bootstrap["image"]
        or current["argv_digest"] != digest(bootstrap["spec"]["argv"])
        or current["cwd"]
        != {
            "path": bootstrap["spec"]["cwd"],
            "directory": bootstrap["directory"],
            "process_directory": bootstrap["directory"],
        }
    ):
        raise ValueError("current proof is not bound to launched host")


def approval_valid(approval, plan, plan_key):
    states.fields(
        approval,
        "schema intent plan confirmation acceptance attest_client_returned created expires",
    )
    if (
        approval["schema"] != SCHEMA
        or approval["intent"] != "restore-disposition"
        or approval["plan"] != plan_key
        or approval["confirmation"] != plan_key
        or approval["acceptance"] != ACCEPT
        or approval["attest_client_returned"] is not True
        or type(approval["created"]) is not int
        or not plan["created"] <= approval["created"] < plan["expires"]
        or approval["expires"] != plan["expires"]
    ):
        raise ValueError("not exact disposition-only approval")


def consumption(approval_key, plan_key):
    return {
        "schema": SCHEMA,
        "intent": "restore-disposition",
        "approval": approval_key,
        "plan": plan_key,
    }


def receipt_for(plan_key, approval_key, plan):
    return {
        "schema": SCHEMA,
        "status": ACCEPT,
        "plan": plan_key,
        "approval": approval_key,
        "attempt": plan["attempt"],
        "interrupted_receipt": plan["witness"]["interrupted"]["digest"],
        "pending_intent": plan["pending"],
        "disposition_effects": [],
        "historical_completion": "unproved",
        "pending_outcome": "unresolved",
        "native_session": "not-proved",
        "retry_authorized": False,
    }


def artifact(store, kind, key):
    from .restore_disposition_dependencies import artifact as read_artifact

    return read_artifact(store, kind, key)


def durable_dependencies(store, references):
    pins = []
    for kind, key, expected in references:
        value, pin = artifact(store, kind, key)
        if value != expected:
            raise ValueError("disposition dependency changed")
        pins.append(pin)
    for pin in pins:
        sync_artifact(pin)


def committed(store, receipt, active, pending, chain, canonical):
    """Full closed special flow, used by ALL writer admission, without new native claims."""
    if pending is None or active.get("retained_pending") != pending[0] or len(chain) != 9:
        raise ValueError("operator disposition cannot terminate another history shape")
    directories(store)
    plan_key, approval_key = receipt["plan"], receipt["approval"]
    plan, plan_pin = artifact(store, "plans", plan_key)
    historical_binding(store, plan, active, chain)
    approval, approval_pin = artifact(store, "approvals", approval_key)
    approval_valid(approval, plan, plan_key)
    used, used_pin = artifact(store, "used", approval_key)
    if used != consumption(approval_key, plan_key) or receipt != receipt_for(
        plan_key, approval_key, plan
    ):
        raise ValueError("incomplete disposition accounting")
    interrupted = store.get("receipts", receipt["interrupted_receipt"])
    pins = [
        *plan["manifest"],
        *(plan["witness"][key] for key in ("interrupted", "client_result", "client_exit")),
        plan_pin,
        approval_pin,
        used_pin,
        *reversed(canonical[3]),
    ]
    return {
        **receipt,
        "effects": [],
        "historical_effects": interrupted["effects"],
        "historical_rows_receipt": receipt["interrupted_receipt"],
        "fresh_native_verification": False,
    }, pins


def inspect(store, identity, attempt, interrupted, client_result, client_exit, *, family=None):
    from . import restore_exited as exited

    if family == exited.v.FAMILY:
        return exited.inspect(store, attempt, interrupted, client_result, client_exit)
    if family is not None:
        from . import restore_disposition_v2 as v2

        if family != v2.model.FAMILY:
            raise ValueError("unknown disposition family")
        return v2.inspect(store, identity, attempt, interrupted, client_result, client_exit)
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        completed, _, count, tail = history.load(identity)
        for item in completed:
            if (
                item["attempt"] != attempt
                or item["result"].get("status") != ACCEPT
                or item["result"].get("schema") != SCHEMA
            ):
                continue
            plan = store.get("plans", item["result"]["plan"])
            witness = plan["witness"]
            from pathlib import Path

            if (
                item["origin"]["root"] != str(store.root)
                or interrupted != witness["interrupted"]["digest"]
                or str(Path(client_result).absolute()) != witness["client_result"]["path"]
                or str(Path(client_exit).absolute()) != witness["client_exit"]["path"]
            ):
                raise ValueError("inspection requires exact original Store and witnesses")
            return {
                "attempt": attempt,
                "history_count": count,
                "history_tail": tail,
                "canonical": "validated",
                "durability": "unestablished",
                "admission": "not-granted",
                "approval": "not-granted",
                "desktop_effects": [],
                "retry_authorized": False,
            }
        active, chain, count, tail = source(store, identity, attempt)
        value = binding(store, active, chain, count, tail, interrupted, client_result, client_exit)
        return {
            "attempt": attempt,
            "history_count": count,
            "history_tail": tail,
            "pending_intent": value["pending"],
            "interrupted_receipt": interrupted,
            "approval": "not-granted",
            "desktop_effects": [],
            "retry_authorized": False,
            "trust": proof.TRUST,
        }


def propose(
    store,
    identity,
    attempt,
    interrupted,
    client_result,
    client_exit,
    *,
    ttl=300,
    observer=proof.observe,
    family=None,
):
    from . import restore_exited as exited

    if family == exited.v.FAMILY:
        return exited.propose(store, attempt, interrupted, client_result, client_exit, ttl=ttl)
    if family is not None:
        from . import restore_disposition_v2 as v2

        if family != v2.model.FAMILY:
            raise ValueError("unknown disposition family")
        return v2.propose(
            store,
            identity,
            attempt,
            interrupted,
            client_result,
            client_exit,
            ttl=ttl,
            observer=observer,
        )
    if type(ttl) is not int or not 1 <= ttl <= 900:
        raise ValueError("disposition TTL must be 1..900 seconds")
    with operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        active, chain, count, tail = source(store, identity, attempt)
        bound = binding(store, active, chain, count, tail, interrupted, client_result, client_exit)
        with proof.current(active, chain, observer) as (current, validate):
            created = int(time.time())
            plan = {
                "schema": SCHEMA,
                "intent": "restore-disposition",
                "created": created,
                "expires": created + ttl,
                **bound,
                "current": current,
                "limits": LIMITS,
            }
            plan_valid(plan, fresh=True)
            validate()
            # No receipt, approval, fence, pointer or desktop write.
            return {
                "plan_digest": store.put("plans", plan),
                "approval": "not-granted",
                "desktop_effects": [],
                "retry_authorized": False,
            }


def fresh(store, plan):
    plan_valid(plan, fresh=True)
    active, chain, _, _ = source(store, plan["identity"], plan["attempt"])
    historical_binding(store, plan, active, chain)
    plan_valid(plan, fresh=True)  # Recheck expiry after potentially slow original-byte validation.
    return active, chain


def approve(
    store,
    plan_key,
    *,
    confirmation,
    acceptance,
    attest_client_returned,
    observer=proof.observe,
    platform_ack=None,
):
    if confirmation != plan_key or acceptance != ACCEPT or attest_client_returned is not True:
        raise ValueError(
            "exact digest, literal partial acceptance and original-client attestation required"
        )
    from . import restore_disposition_v2 as v2
    from . import restore_exited as exited

    routed, first = exited.route(store, "plans", plan_key)
    if routed.get("schema") == exited.v.SCHEMA:
        return exited.approve(
            store,
            plan_key,
            confirmation=confirmation,
            acceptance=acceptance,
            attest_client_returned=attest_client_returned,
            platform_ack=platform_ack,
            first=first,
        )
    if platform_ack is not None or routed.get("schema") not in (SCHEMA, v2.model.SCHEMA):
        raise ValueError("unknown disposition schema or foreign platform acknowledgement")
    if routed.get("schema") == v2.model.SCHEMA:
        return v2.approve(
            store,
            plan_key,
            confirmation=confirmation,
            acceptance=acceptance,
            attest_client_returned=attest_client_returned,
            observer=observer,
        )
    directories(store)
    plan = store.get("plans", plan_key)
    with operation_lock(
        plan["identity"], effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        active, chain = fresh(store, plan)
        with proof.current(active, chain, observer) as (current, validate):
            if current != plan["current"]:
                raise ValueError("current baseline differs from reviewed plan")
            approval = {
                "schema": SCHEMA,
                "intent": "restore-disposition",
                "plan": plan_key,
                "confirmation": confirmation,
                "acceptance": acceptance,
                "attest_client_returned": True,
                "created": int(time.time()),
                "expires": plan["expires"],
            }
            approval_valid(approval, plan, plan_key)
            fresh(store, plan)
            durable_dependencies(store, [("plans", plan_key, plan)])
            validate()
            plan_valid(plan, fresh=True)
            return {"approval_digest": store.put("approvals", approval), "desktop_effects": []}


def commit(identity, record, before_publish):
    # A complete-but-unfsynced canonical filename must not grant writer admission. Until
    # the durable staged record is renamed, its unrecognized name keeps every writer fenced.
    # A visible rename is NOT proof of directory durability. Every accepting path must
    # independently validate and establish fresh barriers through history.admit().
    path = history.fence_path(identity) / "00000009.json"
    staged = path.with_suffix(".pending")
    history.durable_create(staged, record)
    if os.path.lexists(path):
        raise ValueError("canonical disposition already exists")
    before_publish()  # Last live veto AFTER staged file/directory persistence, before publication.
    with phase("publish"):
        publication_attempted()
        os.rename(staged, path)
    with phase("canonical-directory-sync"):
        history.sync_directory(path.parent)


def apply(store, approval_key, *, observer=proof.observe):
    from . import restore_disposition_v2 as v2
    from . import restore_exited as exited

    routed, first = exited.route(store, "approvals", approval_key)
    if routed.get("schema") == exited.v.SCHEMA:
        return exited.apply(store, approval_key, first=first)
    if routed.get("schema") == v2.model.SCHEMA:
        return v2.apply(store, approval_key, observer=observer)
    directories(store)
    approval = store.get("approvals", approval_key)
    plan_key = approval["plan"]
    plan = store.get("plans", plan_key)
    with operation_lock(
        plan["identity"], effectful=False, existing_only=True, _preserve_disposition_failures=True
    ):
        completed, _, _, _ = history.load(plan["identity"])
        if routed.get("schema") != SCHEMA:
            raise ValueError("unknown disposition schema")
        for item in completed:
            result = item["result"]
            if result.get("approval") == approval_key:
                if item["origin"]["root"] != str(store.root):
                    raise ValueError("disposition replay requires original Store")
                history.admit(plan["identity"])
                return {
                    **result,
                    "receipt_digest": item["receipt_digest"],
                    "historical": True,
                    "durability": "established-now",
                }
        active, chain = fresh(store, plan)
        approval_valid(approval, plan, plan_key)
        with proof.current(active, chain, observer) as (current, validate):
            if current != plan["current"]:
                raise ValueError("current baseline differs from approved plan")
            fresh(store, plan)
            durable_dependencies(
                store, [("plans", plan_key, plan), ("approvals", approval_key, approval)]
            )

            def last_live_check():
                validate()
                plan_valid(plan, fresh=True)

            last_live_check()
            # One flock: consume fsync -> receipt fsync -> exactly one canonical record fsync.
            store.consume(approval_key, consumption(approval_key, plan_key))
            receipt = receipt_for(plan_key, approval_key, plan)
            key = store.put("receipts", receipt)
            fresh(store, plan)
            durable_dependencies(
                store,
                [
                    ("plans", plan_key, plan),
                    ("approvals", approval_key, approval),
                    ("used", approval_key, consumption(approval_key, plan_key)),
                    ("receipts", key, receipt),
                ],
            )
            commit(
                plan["identity"],
                {
                    "schema": history.SCHEMA,
                    "seq": 9,
                    "previous": plan["history_tail"],
                    "type": "operator-disposition",
                    "attempt": plan["attempt"],
                    "receipt": key,
                    "origin": plan["origin"],
                },
                last_live_check,
            )
            history.admit(plan["identity"])
            return {
                **receipt,
                "receipt_digest": key,
                "effects": [],
                "historical": False,
                "durability": "established-now",
            }
