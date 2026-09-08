"""Closed additive saved-set contract; no invented former processes or destructive proofs."""

from .model import digest
from .recovery_protocol import ADDITIVE as SCHEMA
from .recovery_protocol import (
    COUNT,
    NATIVE,
    boolean,
    count,
    fields,
    hexkey,
    keys,
    legacy,
    require,
    sequence,
)

DIMENSIONS = ("causal_ownership", "new_images", "focus", "protected_preservation")
DISPOSITIONS = ("missing_refs", "present_refs", "unresolved_refs")


def prepare_plan(plan, saved_set):
    hexkey(saved_set)
    plan["selection"] = {
        "window_ids": [],
        "pids": [],
        "requested_window_ids": [],
        "requested_pids": [],
        "app_id": None,
        "version": None,
    }
    plan["affected"] = {
        "window_ids": [],
        "pids": [],
        "extra_window_ids": [],
        "process_pins": [],
        "ownership_unknown": False,
    }
    plan["admission"]["blockers"] = [
        value for value in plan["admission"]["blockers"] if value != "selector-matched-nothing"
    ]
    plan["fidelity"]["layout"] = "not-reconstructed; ordinary-tiling-insertion-may-change-geometry"
    require(len(plan["focus_pin"]["windows"]) == 1)


def warnings():
    return [
        "additive saved-set only; no shutdown, service actions, or existing-window movement",
        "accepted loss required: saved-conversations-v1 (memory, drafts, scrollback, shell state, hidden-tab order)",
        "all current windows protected; normal tiling insertion may change their geometry",
        "saved refs, not former live windows or inferred tabs, define selection",
        "focus restoration is non-atomic; operator must remain idle",
    ]


def selection(value):
    fields(value, DISPOSITIONS)
    for name in DISPOSITIONS:
        keys(value[name])
    all_refs = [ref for name in DISPOSITIONS for ref in value[name]]
    require(len(all_refs) <= COUNT and len(all_refs) == len(set(all_refs)))
    # Reserve one transport event for restoring the admitted focus after launches.
    require(len(value["missing_refs"]) < COUNT)
    return sorted(all_refs)


def observation(value, legacy_digest):
    fields(
        value,
        (
            "identity_digest",
            "state_fingerprint",
            "focus_digest",
            "private_ref",
            "supported",
            "processes",
            "session_refs",
            "legacy",
            "saved_set",
            "saved_selection",
            "selection_proved",
        ),
    )
    for name in (
        "identity_digest",
        "state_fingerprint",
        "focus_digest",
        "private_ref",
        "saved_set",
    ):
        hexkey(value[name])
    boolean(value["supported"])
    boolean(value["selection_proved"])
    require(value["processes"] == [])
    keys(value["session_refs"])
    require(selection(value["saved_selection"]) == value["session_refs"])
    legacy(value["legacy"], legacy_digest)
    return value


def coverage(value, omissions):
    require(omissions == [])
    selected = value["saved_selection"]
    blockers = []
    if not value["supported"]:
        blockers.append("unsupported-additive-recovery-profile")
    if not value["selection_proved"]:
        blockers.append("saved-selection-identity-absence-or-protection-unproved")
    if not value["session_refs"]:
        blockers.append("empty-saved-selection")
    if selected["unresolved_refs"]:
        blockers.append("saved-selection-unresolved")
    return (
        {
            "selected_saved_conversations": len(value["session_refs"]),
            "missing_saved_conversations": len(selected["missing_refs"]),
            "already_present_saved_conversations": len(selected["present_refs"]),
            "unresolved_saved_conversations": len(selected["unresolved_refs"]),
        },
        [],
        blockers,
    )


def proof(value, session_refs):
    fields(value, ("dimensions", "native", "interrupted", "unresolved_children"))
    fields(value["dimensions"], DIMENSIONS)
    boolean(value["interrupted"])
    count(value["unresolved_children"])
    complete = not value["interrupted"] and value["unresolved_children"] == 0
    for item in value["dimensions"].values():
        fields(item, ("status", "evidence_ref"))
        require(item["status"] in ("proved", "failed", "unknown"))
        if item["evidence_ref"] is not None:
            hexkey(item["evidence_ref"])
        require(item["status"] != "proved" or item["evidence_ref"] is not None)
        complete &= item["status"] == "proved"
    seen = []
    for item in sequence(value["native"]):
        fields(item, ("session_ref", "evidence_ref", *NATIVE))
        seen.append(hexkey(item["session_ref"]))
        hexkey(item["evidence_ref"])
        for name in NATIVE:
            boolean(item[name])
            complete &= item[name]
    require(seen == sorted(set(seen)) and set(seen) <= set(session_refs))
    return bool(complete and seen == session_refs)


def plan_fields(recovery):
    fields(
        recovery,
        (
            "schema",
            "contract",
            "profile_digest",
            "observation",
            "coverage",
            "omissions",
            "mode",
            "saved_set",
        ),
    )
    require(recovery["schema"] == SCHEMA and recovery["mode"] == "additive")
    require(hexkey(recovery["saved_set"]) == recovery["observation"]["saved_set"])


def effect(body, admitted, launched, *, focus_issued):
    """Authorize one exact missing ref, or the exact original focus; never free-form layout."""
    fields(body, ("sequence", "kind", "intent_ref", "target_ref"))
    target = hexkey(body["target_ref"])
    selected = admitted["saved_selection"]
    require(not selected["unresolved_refs"])
    if body["kind"] == "launch":
        require(not focus_issued and target in selected["missing_refs"] and target not in launched)
        launched.add(target)
        return False
    require(body["kind"] == "focus")
    require(
        not focus_issued
        and bool(selected["missing_refs"])
        and launched == set(selected["missing_refs"])
        and target == admitted["focus_digest"]
    )
    return True


def complete_effects(admitted, launched, focus_issued):
    missing = set(admitted["saved_selection"]["missing_refs"])
    require(launched == missing and focus_issued == bool(missing))


def approval_fields(plan):
    recovery = plan["recovery"]
    plan_fields(recovery)
    return {"mode": "additive", "saved_set": recovery["saved_set"]}


def payload_fields(plan):
    recovery = plan["recovery"]
    return {
        "mode": "additive",
        "saved_set": hexkey(recovery["saved_set"]),
        "saved_selection": recovery.get("observation", {}).get("saved_selection"),
    }


def receipt_fields(recovery, complete):
    value = recovery["observation"]
    return {
        "mode": "additive",
        "saved_set": recovery["saved_set"],
        "saved_conversations_restored": len(value["saved_selection"]["missing_refs"])
        if complete
        else 0,
        "saved_conversations_already_present": len(value["saved_selection"]["present_refs"]),
        "saved_conversations_unresolved": len(value["saved_selection"]["unresolved_refs"]),
        "layout": "not-reconstructed; ordinary-tiling-insertion-may-change-geometry",
        "destructive_effects": "not-authorized",
    }


def event_intent(value):
    fields(value, ("sequence", "kind", "intent_ref", "target_ref"))
    require(value["kind"] in ("launch", "focus"))
    hexkey(value["target_ref"])


def validate_event_history(plan, evidence):
    launched, focused = set(), False
    admitted = {"focus_digest": digest(plan["focus_pin"]), **payload_fields(plan)}
    for index, item in enumerate(evidence):
        intent = {k: v for k, v in item["intent"].items() if k != "receipt_digest"}
        require(type(intent["sequence"]) is int and intent["sequence"] == index)
        focused = effect(intent, admitted, launched, focus_issued=focused)
        require(item["outcome"] == "observed")
    complete_effects(admitted, launched, focused)
