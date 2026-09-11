"""One pure canonical resolution view, shared by portable and machine admission owners."""

from .model import digest
from .recovery_protocol import fields, hexkey, require
from .resolution_candidate import admission, lifetime, profile_bytes
from .resolution_candidate import validate as candidate_validate
from .resolution_evidence import fingerprint
from .resolution_evidence import validate as evidence_validate
from .resolution_graph import unchanged
from .resolution_io import Objects, raw, retained_bytes

PLAN = "desktop-continuity.resolution-plan.v1"
APPROVAL = "desktop-continuity.resolution-approval.v1"
RESOLUTION = "desktop-continuity.resolution.v1"
ACCEPTANCE = "abandon-without-retry-or-success"


def plan_validate(plan, candidate, graph, evidence, *, fresh=True):
    fields(
        plan,
        (
            "schema",
            "intent",
            "created_at",
            "expires_at",
            "candidate_digest",
            "graph_digest",
            "evidence_digest",
            "settlement_fingerprint",
            "original_status",
            "decision",
            "native_effects",
            "admission",
        ),
    )
    require(plan["schema"] == PLAN and plan["intent"] == "abandon")
    lifetime(plan, fresh=fresh)
    require(plan["candidate_digest"] == digest(candidate) and plan["graph_digest"] == digest(graph))
    require(plan["evidence_digest"] == digest(evidence))
    require(plan["settlement_fingerprint"] == fingerprint(evidence))
    require(
        plan["original_status"] == "indeterminate"
        and plan["decision"] == "abandon-settled-and-transition"
    )
    require(plan["native_effects"] == [])
    require(
        plan["admission"]
        == {
            "status": "blocked" if evidence["blockers"] else "awaiting-approval",
            "blockers": evidence["blockers"],
        }
    )
    from datetime import datetime

    require(
        datetime.fromisoformat(plan["expires_at"]) <= datetime.fromisoformat(evidence["expires_at"])
    )


def approval_validate(approval, plan, *, fresh=True):
    fields(
        approval,
        (
            "schema",
            "plan_digest",
            "confirmation",
            "candidate_digest",
            "graph_digest",
            "evidence_digest",
            "accepted",
            "approved_at",
            "expires_at",
        ),
    )
    require(approval["schema"] == APPROVAL and approval["accepted"] == ACCEPTANCE)
    require(approval["confirmation"] == approval["plan_digest"] == digest(plan))
    require(
        all(
            approval[k] == plan[k]
            for k in ("candidate_digest", "graph_digest", "evidence_digest", "expires_at")
        )
    )
    require(plan["admission"] == {"status": "awaiting-approval", "blockers": []})
    from datetime import datetime

    require(
        datetime.fromisoformat(plan["created_at"])
        <= datetime.fromisoformat(approval["approved_at"])
        < datetime.fromisoformat(approval["expires_at"])
    )
    lifetime(plan, fresh=fresh)


def chain(objects, approval_key, *, fresh=False, active="new", live=False):
    approval = objects.get(hexkey(approval_key))
    plan = objects.get(approval["plan_digest"])
    candidate = objects.get(plan["candidate_digest"])
    graph = objects.get(plan["graph_digest"])
    evidence = objects.get(plan["evidence_digest"])
    require(candidate["ledger"]["path"] == str(objects.root))
    candidate_validate(candidate, fresh=fresh, active=active, live=live)
    evidence_validate(evidence, candidate, graph, objects, fresh=fresh)
    plan_validate(plan, candidate, graph, evidence, fresh=fresh)
    approval_validate(approval, plan, fresh=fresh)
    return approval, plan, candidate, graph, evidence


def durable_view(profile, *, live=False):
    """Return only a transitively validated explicit edge. No writes, locks, imports of owner code.

    Raises on every partial/torn/foreign prefix. Expiry is historical, not a revocation clock.
    Machine State.legacy must use this SAME function, not cache a completed/finished flag.
    """
    objects = Objects(profile["ledger_root"])
    before = objects.markers()
    if not any(before.values()):
        return None
    finals = before["final"]
    require(len(finals) == 1)
    approval_key, marker = next(iter(finals.items()))
    fields(marker, ("resolution_digest", "approval_digest", "attempt_digest"))
    require(marker["approval_digest"] == approval_key)
    attempt = hexkey(marker["attempt_digest"])
    require(
        before
        == {kind: {attempt if kind == "pending" else approval_key: marker} for kind in before}
    )
    result = objects.get(hexkey(marker["resolution_digest"]))
    fields(
        result,
        (
            "schema",
            "plan_digest",
            "approval_digest",
            "candidate_digest",
            "graph_digest",
            "approved_evidence_digest",
            "apply_evidence_digest",
            "admission_digest",
            "applied_at",
            "disposition",
            "original_status",
            "replay_authorized",
        ),
    )
    require(result["schema"] == RESOLUTION and result["approval_digest"] == approval_key)
    approval, plan, candidate, graph, evidence = chain(objects, approval_key, live=live)
    require(digest(profile) == digest(profile_bytes(candidate["new_profile"])))
    require(
        result["plan_digest"] == digest(plan) and result["candidate_digest"] == digest(candidate)
    )
    require(result["graph_digest"] == digest(graph) and candidate["attempt_digest"] == attempt)
    require(result["approved_evidence_digest"] == digest(evidence))
    require(
        result["disposition"] == "abandoned-settled"
        and result["original_status"] == "indeterminate"
    )
    require(result["replay_authorized"] is False)
    admission(candidate, objects.get(result["admission_digest"]), fresh=False)
    applied = objects.get(result["apply_evidence_digest"])
    require(evidence_validate(applied, candidate, graph, objects, fresh=False))
    require(fingerprint(applied) == plan["settlement_fingerprint"])
    from datetime import datetime

    require(
        datetime.fromisoformat(applied["observed_at"])
        <= datetime.fromisoformat(result["applied_at"])
        < datetime.fromisoformat(approval["expires_at"])
    )
    unchanged(candidate, graph, durable=True)
    archives = [candidate[k] for k in ("old_profile", "old_config", "new_config")]
    archives += candidate["source_contract"]["original_files"] + [
        candidate["source_contract"]["review_artifact"]
    ]
    for item in archives:
        require(raw(objects.path("archives", item["sha256"])) == retained_bytes(item))
    require(objects.markers() == before)
    return {
        "attempt_digest": attempt,
        "old_profile_digest": graph["original_profile_digest"],
        "new_profile_digest": digest(profile),
        "historical_status": "indeterminate",
        "resolution_disposition": "abandoned-settled",
        "transition_state": "final",
        "resolution_digest": marker["resolution_digest"],
        "approval_digest": approval_key,
        "replay_authorized": False,
        "next_attempt_authorized": False,
    }


def admission_gate(profile):
    """Ordinary admission validates live new pins/config roots in addition to durable history."""
    return durable_view(profile, live=True)


def legacy_disposition(profile, worker_root, attempt, historical_status):
    """Machine State.legacy hook; root-bound accounting overlay, NEVER State.completed.

    Caller retains ordinary validation/counting for every other attempt. Admission
    requires owner_guard held by the standalone caller, or authenticated parent-held
    exclusion for the entire child invocation. A cooperating child must not reacquire
    its parent's mutexes. This pure read does not establish exclusion or authenticate it.
    """
    from .resolution_io import root_pin

    edge = durable_view(profile)
    if edge is None or hexkey(attempt) != edge["attempt_digest"]:
        return None
    objects = Objects(profile["ledger_root"])
    resolution = objects.get(edge["resolution_digest"])
    graph = objects.get(resolution["graph_digest"])
    require(root_pin(worker_root) == graph["worker"] and historical_status == "indeterminate")
    return {
        "historical_status": "indeterminate",
        "resolution_disposition": "abandoned-settled",
        "accounted_settled": True,
        "replay_authorized": False,
    }


def inspect(profile, key):
    hexkey(key)
    objects = Objects(profile["ledger_root"])
    result = {
        "historical_status": "indeterminate",
        "resolution_disposition": None,
        "transition_state": "none",
        "replay_authorized": False,
        "next_attempt_authorized": False,
        "native_effects": [],
        "accounting_mutations": [],
    }
    try:
        before = objects.markers()
        edge = durable_view(profile)
        if edge is not None:
            require(key in (edge["attempt_digest"], edge["approval_digest"]))
            result.update(edge)
        elif any(before.values()):
            result["transition_state"] = "blocked-prefix"
        require(objects.markers() == before)
    except (ValueError, OSError, KeyError, TypeError):
        result["transition_state"] = "blocked-or-damaged"
    return result
