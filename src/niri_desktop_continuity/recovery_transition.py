"""Explicit append-only abandonment accounting and owner-profile CAS. No native effects."""

import os
from contextlib import ExitStack, contextmanager
from datetime import datetime

from . import recovery_profile as profiles
from .model import digest
from .operation_lock import operation_lock
from .recovery_protocol import hexkey, require
from .recovery_resolution import (
    ACCEPTANCE,
    APPROVAL,
    PLAN,
    RESOLUTION,
    approval_validate,
    chain,
    durable_view,
    plan_validate,
)
from .resolution_candidate import admitted, lifetime, now, times, validate
from .resolution_evidence import fingerprint, persist_packet
from .resolution_evidence import validate as evidence_validate
from .resolution_graph import initial, unchanged
from .resolution_io import Objects, raw, retained_bytes
from .resolution_lock import serialized
from .resolution_observer import observe
from .store import Store, sync_directory


def objects_current():
    return Objects(profiles.identify_profile()["ledger_root"])


@contextmanager
def compositor_guards(identity, candidate):
    from .resolution_graph import historical

    _, old_plan, _ = historical(candidate)
    identities = [identity]
    if old_plan["source_identity"]["boot_id"] == identity["boot_id"]:
        identities.append(old_plan["source_identity"])
    pins = {
        digest({k: v[k] for k in ("boot_id", "socket_device", "socket_inode")}): v
        for v in identities
    }
    with ExitStack() as stack:
        for key in sorted(pins):
            stack.enter_context(operation_lock(pins[key]))
        yield


@serialized
def plan(candidate_key, attempt, ttl=300):
    candidate, admission = admitted(hexkey(candidate_key))
    require(candidate["attempt_digest"] == hexkey(attempt))
    objects = objects_current()
    graph = initial(candidate)
    objects.put(candidate)
    objects.put(admission)
    graph_key = objects.put(graph)
    packet = observe(candidate_key, graph_key)
    # The first read discovers current compositor identity, without observation-store writes.
    with compositor_guards(packet["evidence"]["current_identity"], candidate):
        admitted(candidate_key)
        unchanged(candidate, graph)
        evidence_key = persist_packet(packet, candidate, graph, objects)
        evidence = objects.get(evidence_key)
        window = times(ttl)
        window["expires_at"] = min(window["expires_at"], evidence["expires_at"])
        value = {
            "schema": PLAN,
            "intent": "abandon",
            **window,
            "candidate_digest": candidate_key,
            "graph_digest": graph_key,
            "evidence_digest": evidence_key,
            "settlement_fingerprint": fingerprint(evidence),
            "original_status": "indeterminate",
            "decision": "abandon-settled-and-transition",
            "native_effects": [],
            "admission": {
                "status": "blocked" if evidence["blockers"] else "awaiting-approval",
                "blockers": evidence["blockers"],
            },
        }
        plan_validate(value, candidate, graph, evidence)
        return {
            "plan_digest": objects.put(value),
            "admission": value["admission"],
            "native_effects": [],
            "accounting_mutations": ["graph", "observation-objects", "resolution-plan"],
        }


@serialized
def approve(key, confirmation, acceptance):
    require(hexkey(key) == confirmation and acceptance == ACCEPTANCE)
    objects = objects_current()
    value = objects.get(key)
    candidate, _ = admitted(value["candidate_digest"], live=False)
    graph, evidence = objects.get(value["graph_digest"]), objects.get(value["evidence_digest"])
    initial(candidate)
    unchanged(candidate, graph)
    require(evidence_validate(evidence, candidate, graph, objects))
    plan_validate(value, candidate, graph, evidence)
    approval = {
        "schema": APPROVAL,
        "plan_digest": key,
        "confirmation": confirmation,
        **{
            k: value[k]
            for k in ("candidate_digest", "graph_digest", "evidence_digest", "expires_at")
        },
        "accepted": ACCEPTANCE,
        "approved_at": now().isoformat(),
    }
    approval_validate(approval, value)
    return {
        "approval_digest": objects.put(approval),
        "native_effects": [],
        "accounting_mutations": ["exact-resolution-approval"],
        "profile_mutations": [],
    }


@serialized
def apply(key):
    objects = objects_current()
    approval, value, candidate, graph, _ = chain(
        objects, hexkey(key), fresh=True, active="old", live=True
    )
    _, admission = admitted(value["candidate_digest"])
    initial(candidate)  # One attempt and NO transaction prefix; never repair a previous apply.
    unchanged(candidate, graph)
    approved = objects.get(value["evidence_digest"])
    with compositor_guards(approved["current_identity"], candidate):
        packet = observe(value["candidate_digest"], value["graph_digest"])
        evidence_key = persist_packet(packet, candidate, graph, objects)
        evidence = objects.get(evidence_key)
        require(
            evidence["verdict"] == "settled"
            and fingerprint(evidence) == value["settlement_fingerprint"]
        )
        admitted(value["candidate_digest"])
        unchanged(candidate, graph)
        lifetime(value)
        require(now() < datetime.fromisoformat(evidence["expires_at"]))
        result = {
            "schema": RESOLUTION,
            "plan_digest": digest(value),
            "approval_digest": key,
            "candidate_digest": digest(candidate),
            "graph_digest": digest(graph),
            "approved_evidence_digest": value["evidence_digest"],
            "apply_evidence_digest": evidence_key,
            "admission_digest": objects.put(admission),
            "applied_at": now().isoformat(),
            "disposition": "abandoned-settled",
            "original_status": "indeterminate",
            "replay_authorized": False,
        }
        resolution_key = objects.put(result)
        archives = [candidate[k] for k in ("old_profile", "old_config", "new_config")]
        archives += candidate["source_contract"]["original_files"] + [
            candidate["source_contract"]["review_artifact"]
        ]
        for item in archives:
            objects.archive(retained_bytes(item))
        active = profiles.profile_path()
        # Exclusive staging: a previous uncertainty is retained, not silently overwritten.
        staged = active.parent / f".recovery-profile-{key}.stage"
        Store._create(objects, staged, retained_bytes(candidate["new_profile"]))
        marker = {
            "resolution_digest": resolution_key,
            "approval_digest": key,
            "attempt_digest": candidate["attempt_digest"],
        }
        for kind in ("prepared", "used", "ready", "pending"):
            objects.marker(kind, candidate["attempt_digest"] if kind == "pending" else key, marker)
        require(
            objects.markers()
            == {
                kind: (
                    {candidate["attempt_digest"] if kind == "pending" else key: marker}
                    if kind != "final"
                    else {}
                )
                for kind in ("prepared", "used", "ready", "pending", "final")
            }
        )
        admitted(value["candidate_digest"])
        unchanged(candidate, graph)
        lifetime(value)
        require(now() < datetime.fromisoformat(evidence["expires_at"]))
        validate(candidate, live=True)
        require(raw(staged) == retained_bytes(candidate["new_profile"]))
        # Atomic replacement only under the shared owner mutex; not a sandbox against same-UID edits.
        os.replace(staged, active)
        sync_directory(active.parent)
        objects.marker("final", key, marker)
        edge = durable_view(profiles.identify_profile(), live=True)
        return {
            **edge,
            "native_effects": [],
            "accounting_mutations": ["prepare", "use", "ready", "pending", "final"],
            "profile_mutations": ["archive-old-profile", "activate-approved-candidate"],
        }
