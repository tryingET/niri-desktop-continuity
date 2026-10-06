"""V3 plan/approval/partial receipt semantics, with independently derived closure."""

import time

from . import restore_disposition as legacy
from . import restore_exited_history as historical
from . import restore_exited_values as v
from . import restore_history as history
from . import restore_state as states
from .model import digest
from .restore_disposition_dependencies import Bindings, artifact
from .restore_reader import same

SCHEMA, FAMILY, BRANCH, ACCEPT = v.SCHEMA, v.FAMILY, v.BRANCH, v.ACCEPT


def discriminator(value):
    if (
        value.get("schema") != SCHEMA
        or value.get("family") != FAMILY
        or value.get("branch") != BRANCH
    ):
        raise ValueError("unknown exited disposition discriminator")


def plan_valid(plan, *, fresh):
    states.fields(
        plan,
        "schema family branch intent created expires attempt identity origin history_count history_tail manifest prepared snapshot segment witness platform current limits",
    )
    discriminator(plan)
    v.identity(plan["identity"])
    states.fields(plan["origin"], "root pin")
    v.path(plan["origin"]["root"])
    v.inode(plan["origin"]["pin"])
    for name in ("attempt", "history_tail", "prepared", "snapshot"):
        v.key(plan[name])
    for name in ("created", "expires"):
        v.integer(plan[name])
    if (
        plan["intent"] != "restore-disposition"
        or not same(plan["platform"], v.PLATFORM)
        or not same(plan["limits"], v.LIMITS)
        or not 1 <= plan["expires"] - plan["created"] <= 900
        or (fresh and not plan["created"] <= time.time() < plan["expires"])
    ):
        raise ValueError("invalid or expired v3 plan")
    segment = plan["segment"]
    states.fields(
        segment,
        "start count previous " + " ".join(historical.REFS) + " process_receipt baseline_digest",
    )
    v.integer(segment["start"], 0, 4095)
    if type(segment["count"]) is not int or segment["count"] != 10:
        raise ValueError("ten records required")
    v.integer(plan["history_count"], 10, 4095)
    if plan["history_count"] != segment["start"] + 10:
        raise ValueError("incorrect global segment extent")
    if segment["start"] == 0:
        if segment["previous"] is not None:
            raise ValueError("unexpected previous prefix")
    else:
        v.key(segment["previous"])
    for name in [*historical.REFS, "process_receipt", "baseline_digest"]:
        v.key(segment[name])
    if not isinstance(plan["manifest"], list) or len(plan["manifest"]) > 32768:
        raise ValueError("invalid bounded manifest")
    Bindings(plan["manifest"]).exact(plan["manifest"])
    for pin in plan["manifest"]:
        v.filepin(pin, raw="digest" not in pin)
    witness = plan["witness"]
    states.fields(witness, "interrupted client_result client_exit error_signature trust")
    for name in ("interrupted", "client_result", "client_exit"):
        v.filepin(witness[name], raw=name == "client_exit")
    if (
        not same(witness["error_signature"], historical.ERROR)
        or witness["trust"] != historical.TRUST
    ):
        raise ValueError("unknown witness error/trust")


def historical_binding(store, plan, active, chain):
    plan_valid(plan, fresh=False)
    witness = plan["witness"]
    store.reader.expect(
        [*plan["manifest"], *(witness[k] for k in ("interrupted", "client_result", "client_exit"))]
    )
    actual = historical.binding(
        store,
        active,
        chain,
        witness["interrupted"]["digest"],
        witness["client_result"]["path"],
        witness["client_exit"]["path"],
    )
    if any(not same(plan[k], val) for k, val in actual.items()):
        raise ValueError("original closure or witness differs from approved pins")
    source = store.get("snapshots", active["snapshot_digest"])
    v.current(
        plan["current"],
        source,
        active["_launches"]["launches"][0]["process"],
        active["_launches"]["associations"][0]["id"],
    )


def approval_valid(approval, plan, plan_key):
    states.fields(
        approval,
        "schema family branch intent plan confirmation acceptance attest_client_returned platform_ack caller created expires",
    )
    discriminator(approval)
    v.integer(approval["created"])
    v.integer(approval["expires"])
    # ubs:ignore[python.ctcompare.secret_eq] -- Public platform ack, not auth.
    if (
        approval["intent"] != "restore-disposition"
        or approval["plan"] != plan_key
        or approval["confirmation"] != plan_key
        or approval["acceptance"] != ACCEPT
        or approval["attest_client_returned"] is not True
        or approval["platform_ack"] != digest(plan["platform"])
        or not plan["created"] <= approval["created"] < plan["expires"]
        or approval["expires"] != plan["expires"]
    ):
        raise ValueError("exact v3 approval and explicit platform acknowledgement required")
    stage_caller(approval["caller"], plan)


def consumption(approval_key, plan_key):
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "branch": BRANCH,
        "intent": "restore-disposition",
        "approval": approval_key,
        "plan": plan_key,
    }


def stage_caller(caller, plan):
    v.caller(caller, plan["identity"]["boot_id"], plan["current"]["absence"]["process"]["pid"])
    current = plan["current"]
    held = {p["pid"]: p for p in [*current["processes"], current["peer"]["process"]]}
    for row in caller["ancestry"]:
        pin = row["process"]
        if pin["pid"] in held and not same(pin, held[pin["pid"]]):
            raise ValueError("stage caller conflicts with approved held generation")


def receipt(plan_key, approval_key, plan, caller):
    stage_caller(caller, plan)
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "branch": BRANCH,
        "status": ACCEPT,
        "plan": plan_key,
        "approval": approval_key,
        "attempt": plan["attempt"],
        "interrupted_receipt": plan["witness"]["interrupted"]["digest"],
        "process_receipt": plan["segment"]["process_receipt"],
        "proof_method": plan["current"]["method"],
        "current_digest": digest(plan["current"]),
        "platform_ack": digest(plan["platform"]),
        "caller": caller,
        "disposition_effects": [],
        "historical_completion": "unproved",
        "historical_preservation": "unproved",
        "historical_association": "recorded",
        "historical_layout": "two-observed-actions-incomplete",
        "outcome": "unresolved",
        "native_session": "not-proved",
        "retry_authorized": False,
    }


def committed(store, payload, active, pending, chain, canonical):
    historical.eligible(active, chain, pending)
    discriminator(payload)
    expected = {
        "schema": history.SCHEMA,
        "seq": len(chain),
        "previous": digest(chain[-1][0]),
        "type": "operator-disposition",
        "attempt": active["attempt"],
        "origin": active["origin"],
        "receipt": digest(payload),
    }
    if not same(canonical[0], expected):
        raise ValueError("incorrect v3 canonical ending")
    legacy.directories(store)
    plan_key, approval_key = payload["plan"], payload["approval"]
    plan, pp = artifact(store, "plans", plan_key)
    historical_binding(store, plan, active, chain)
    approval, ap = artifact(store, "approvals", approval_key)
    approval_valid(approval, plan, plan_key)
    used, up = artifact(store, "used", approval_key)
    if not same(used, consumption(approval_key, plan_key)) or not same(
        payload, receipt(plan_key, approval_key, plan, payload["caller"])
    ):
        raise ValueError("incomplete or overclaiming v3 accounting")
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
        "historical_effects": active["_launches"]["effects"],
        "historical_rows_receipt": payload["interrupted_receipt"],
        "fresh_native_verification": False,
    }, pins.manifest()
