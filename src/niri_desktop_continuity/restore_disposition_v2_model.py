"""Exact exec-observed-unassociated semantics; no IO outside the supplied reader view."""

import time
from pathlib import Path

from . import restore_dimensions as dimensions
from . import restore_disposition as legacy
from . import restore_history as history
from . import restore_state as states
from .model import digest
from .restore_disposition_dependencies import Bindings, artifact, file
from .restore_disposition_evidence import TRUST
from .restore_reader import same
from .store import HEX

SCHEMA = "desktop-continuity.restore-disposition.v2"
FAMILY = "exec-observed-unassociated"
ACCEPT = legacy.ACCEPT
LIMITS = {
    **{k: v for k, v in legacy.LIMITS.items() if k != "pending_outcome"},
    "historical_association": "not-recorded",
    "historical_layout": "not-attempted",
    "outcome": "unresolved",
}
FIELDS = legacy.PLAN_FIELDS.replace(" pending", "") + " family segment"
ERROR = {"error_type": "ValueError", "error": "foreign active window"}


def process_identity(pin):
    """Identity is boot/PID/start, never mutable incidental process metadata or PID alone."""
    core = {key: pin[key] for key in ("boot_id", "pid", "start_ticks")}
    history.records.pin(core)
    return core["boot_id"], core["pid"], core["start_ticks"]


def eligible(active, chain, pending=None):
    start = active["_start"]
    segment = chain[start:]
    tracker, plan = active["_launches"], active["plan"]
    if (
        len(segment) != 5
        or any(not same(row[0]["origin"], active["origin"]) for row in segment)
        or [r[0]["type"] for r in segment]
        != ["prepared", "intent", "observed", "intent", "observed"]
        or segment[1][1]["action"] != "bootstrap"
        or segment[3][1]["action"] != "exec"
        or pending is not None
        or active.get("_pending") is not None
        or plan["mode"] != "restore"
        or len(plan["entries"]) != 1
        or not same(
            plan["initial_accounting"],
            [
                {
                    "entry": plan["entries"][0],
                    "window_id": plan["entries"][0]["window_id"],
                    "status": "unprocessed",
                }
            ],
        )
        or set(tracker["launches"]) != {0}
        or tracker["launches"][0]["phase"] != "process-observed"
        or tracker["associations"]
        or tracker["effects"]
        or tracker["final"] is not None
        or active["attempt"] in active["_prior_attempts"]
        or active["snapshot_digest"] in active["_prior_sources"]
        or any(
            process_identity(p) == process_identity(tracker["launches"][0]["process"])
            for p in active["_prior_processes"]
        )
    ):
        raise ValueError("exact fresh five-record exec-observed-unassociated segment required")
    return {
        "start": start,
        "count": 5,
        "previous": segment[0][0]["previous"],
        "exec_intent": segment[3][0]["receipt"],
        "exec_observed": segment[4][0]["receipt"],
        "process_receipt": digest(segment[4][1]["evidence"]),
        "baseline_digest": digest(plan["baseline"]),
    }


def witness(store, active, interrupted, result_path, exit_path):
    receipt, receipt_pin = artifact(store, "receipts", interrupted)
    states.fields(
        receipt, "status windows effects final_observation native_session error_type error"
    )
    entry = active["plan"]["entries"][0]
    expected_row = {
        "entry": entry,
        "window_id": entry["window_id"],
        "status": "launch-indeterminate",
        "geometry_coverage": dimensions.pending(entry, dimensions.policies(active["plan"])[0]),
        "process_receipt": active["_launches"]["launches"][0]["receipt"],
    }
    if (
        receipt["status"] != "interrupted"
        or receipt["native_session"] != "not-proved"
        or any(receipt[k] != v for k, v in ERROR.items())
        or not same(receipt["effects"], [])
        or not same(receipt["windows"], [expected_row])
    ):
        raise ValueError("exact original returned unassociated ValueError witness required")
    diagnostic = receipt["final_observation"]
    if not same(diagnostic, {"unavailable": True}):
        states.decode(diagnostic)  # Diagnostic only; NEVER used as an association or baseline.
    result_path, exit_path = Path(result_path).absolute(), Path(exit_path).absolute()
    if result_path.parent != exit_path.parent or result_path == exit_path:
        raise ValueError("original result and exit must be distinct files in one private directory")
    result, result_pin = file(store, result_path)
    exit_bytes, exit_pin = file(store, exit_path, raw=True)
    if (
        not same(
            result,
            {
                "snapshot_digest": active["snapshot_digest"],
                "receipt_digest": interrupted,
                **receipt,
            },
        )
        or exit_bytes != b"2\n"
    ):
        raise ValueError("original invocation body/exit mismatch")
    return {
        "interrupted": receipt_pin,
        "client_result": result_pin,
        "client_exit": exit_pin,
        "error_signature": ERROR,
        "trust": TRUST,
    }


def binding(store, active, chain, interrupted, result_path, exit_path):
    segment = eligible(active, chain)
    if not same(
        active["origin"], {"root": str(store.root), "pin": history.directory_pin(store.root)}
    ):
        raise ValueError("original Store root and inode required")
    return {
        "family": FAMILY,
        "attempt": active["attempt"],
        "identity": active["identity"],
        "origin": active["origin"],
        "history_count": len(chain),
        "history_tail": digest(chain[-1][0]),
        "manifest": active["_prefix_pins"],
        "prepared": chain[segment["start"]][0]["receipt"],
        "snapshot": active["snapshot_digest"],
        "segment": segment,
        "witness": witness(store, active, interrupted, result_path, exit_path),
    }


def plan_valid(plan, *, fresh):
    states.fields(plan, FIELDS)
    if (
        plan["schema"] != SCHEMA
        or plan["family"] != FAMILY
        or plan["intent"] != "restore-disposition"
        or not same(plan["limits"], LIMITS)
        or type(plan["created"]) is not int
        or type(plan["expires"]) is not int
        or not 1 <= plan["expires"] - plan["created"] <= 900
        or (fresh and not plan["created"] <= time.time() < plan["expires"])
    ):
        raise ValueError("invalid or expired v2 disposition plan")
    states.fields(
        plan["segment"],
        "start count previous exec_intent exec_observed process_receipt baseline_digest",
    )
    for key in ("exec_intent", "exec_observed", "process_receipt", "baseline_digest"):
        value = plan["segment"][key]
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError("invalid v2 segment digest reference")
    if (
        type(plan["segment"]["start"]) is not int
        or plan["segment"]["start"] < 0
        or type(plan["segment"]["count"]) is not int
        or plan["segment"]["count"] != 5
        or type(plan["history_count"]) is not int
        or plan["history_count"] != plan["segment"]["start"] + 5
        or plan["history_count"] >= history.LIMIT
    ):
        raise ValueError("invalid v2 segment extent")
    states.fields(plan["witness"], "interrupted client_result client_exit error_signature trust")
    Bindings(plan["manifest"]).exact(plan["manifest"])
    for key in ("interrupted", "client_result", "client_exit"):
        Bindings([plan["witness"][key]])
    current = plan["current"]
    states.fields(
        current,
        "state owned_window_id protected_window_ids processes running_image argv_digest cwd controller_pids",
    )
    state = states.decode(current["state"])
    owned, controllers = current["owned_window_id"], current["controller_pids"]
    if (
        type(owned) is not int
        or owned not in state[0]
        or not same(current["protected_window_ids"], sorted(set(state[0]) - {owned}))
        or not isinstance(controllers, list)
        or not 1 <= len(controllers) <= 128
        or any(type(p) is not int or p <= 0 for p in controllers)
        or controllers != sorted(set(controllers))
    ):
        raise ValueError("invalid closed current partition/controller evidence")
    if not isinstance(current["processes"], list):
        raise ValueError("missing current process proofs")
    for pin in current["processes"]:
        history.records.pin(pin)
    if [p["pid"] for p in current["processes"]] != sorted({w["pid"] for w in state[0].values()}):
        raise ValueError("incomplete or duplicate current process proofs")


def partition(current, active, chain):
    """Historical verifier of the RECORDED proof; never probes historical processes."""
    tracker = active["_launches"]
    launched = tracker["launches"][0]["process"]
    bootstrap = chain[active["_start"] + 1][1]["details"]
    state, owned, pid = states.decode(current["state"]), current["owned_window_id"], launched["pid"]
    if (
        [w["id"] for w in state[0].values() if w["pid"] == pid] != [owned]
        or owned in tracker["baseline"][0]
        or any(w["pid"] == pid for w in tracker["baseline"][0].values())
        or any(
            process_identity(p) == process_identity(launched) for p in active["_prior_processes"]
        )
        or pid in current["controller_pids"]
        or not any(same(p, launched) for p in current["processes"])
        or any(p["boot_id"] != active["identity"]["boot_id"] for p in current["processes"])
        or not same(current["running_image"], bootstrap["image"])
        or current["argv_digest"] != digest(bootstrap["spec"]["argv"])
        or not same(
            current["cwd"],
            {
                "path": bootstrap["spec"]["cwd"],
                "directory": bootstrap["directory"],
                "process_directory": bootstrap["directory"],
            },
        )
    ):
        raise ValueError("current partition/pins do not prove exactly the original launched host")


def historical_binding(store, plan, active, chain):
    plan_valid(plan, fresh=False)
    reader = store.reader
    # Bind stored assertions BEFORE reading witnesses. Prefix references were already budgeted;
    # conflicts with their first observed pins still reject before any deduplication.
    reader.expect(
        [
            *plan["manifest"],
            *(plan["witness"][k] for k in ("interrupted", "client_result", "client_exit")),
        ]
    )
    w = plan["witness"]
    actual = binding(
        store,
        active,
        chain,
        w["interrupted"]["digest"],
        w["client_result"]["path"],
        w["client_exit"]["path"],
    )
    if any(not same(plan[k], v) for k, v in actual.items()):
        raise ValueError("original closure or witness differs from persisted bindings")
    partition(plan["current"], active, chain)


def approval_valid(approval, plan, plan_key):
    states.fields(
        approval,
        "schema family intent plan confirmation acceptance attest_client_returned created expires",
    )
    if (
        approval["schema"] != SCHEMA
        or approval["family"] != FAMILY
        or approval["intent"] != "restore-disposition"
        or approval["plan"] != plan_key
        or approval["confirmation"] != plan_key
        or approval["acceptance"] != ACCEPT
        or approval["attest_client_returned"] is not True
        or type(approval["created"]) is not int
        or type(approval["expires"]) is not int
        or not plan["created"] <= approval["created"] < plan["expires"]
        or approval["expires"] != plan["expires"]
    ):
        raise ValueError("exact v2 partial-accounting approval required")


def consumption(approval_key, plan_key):
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "intent": "restore-disposition",
        "approval": approval_key,
        "plan": plan_key,
    }


def receipt(plan_key, approval_key, plan, active):
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "status": ACCEPT,
        "plan": plan_key,
        "approval": approval_key,
        "attempt": plan["attempt"],
        "interrupted_receipt": plan["witness"]["interrupted"]["digest"],
        "process_receipt": active["_launches"]["launches"][0]["receipt"],
        "disposition_effects": [],
        "historical_completion": "unproved",
        "historical_association": "not-recorded",
        "historical_layout": "not-attempted",
        "outcome": LIMITS["outcome"],
        "native_session": "not-proved",
        "retry_authorized": False,
    }


def committed(store, payload, active, pending, chain, canonical):
    eligible(active, chain, pending)
    expected_ending = {
        "schema": history.SCHEMA,
        "seq": len(chain),
        "previous": digest(chain[-1][0]),
        "type": "operator-disposition",
        "attempt": active["attempt"],
        "origin": active["origin"],
        "receipt": digest(payload),
    }
    if not same(canonical[0], expected_ending):
        raise ValueError("v2 ending differs from exact typed canonical envelope")
    legacy.directories(store)
    plan_key, approval_key = payload["plan"], payload["approval"]
    plan, pp = artifact(store, "plans", plan_key)
    historical_binding(store, plan, active, chain)
    approval, ap = artifact(store, "approvals", approval_key)
    approval_valid(approval, plan, plan_key)
    used, up = artifact(store, "used", approval_key)  # pathname is approval key, NOT body digest.
    if not same(used, consumption(approval_key, plan_key)) or not same(
        payload, receipt(plan_key, approval_key, plan, active)
    ):
        raise ValueError("incomplete or overclaiming v2 accounting")
    pins = Bindings(
        [
            *plan["manifest"],
            pp,
            ap,
            up,
            *canonical[3],
            *(plan["witness"][k] for k in ("interrupted", "client_result", "client_exit")),
        ]
    )
    return {
        **payload,
        "effects": [],
        "historical_effects": [],
        "historical_rows_receipt": payload["interrupted_receipt"],
        "fresh_native_verification": False,
    }, pins.manifest()
