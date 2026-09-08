"""Existing-CLI reconstruction orchestration, distinct from exact restart or layout reconcile."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from . import recovery_additive as additive
from .model import digest, fingerprint, focus_pin, readiness
from .operation_lock import operation_lock
from .planner import build_plan
from .recovery_adapter import Adapter
from .recovery_ledger import Ledger
from .recovery_profile import identify_profile, load_profile
from .recovery_protocol import (
    ADDITIVE,
    CONTRACT,
    VERSION2,
    coverage,
    fields,
    keys,
    legacy,
    observation,
    require,
    successes,
    version,
)
from .recovery_utilities import utility_limits
from .recovery_verification import receipt


def lifetime(plan):
    created = datetime.fromisoformat(plan["created_at"])
    expires = datetime.fromisoformat(plan["expires_at"])
    require(created.tzinfo is not None and expires.tzinfo is not None)
    require(
        created <= datetime.now(timezone.utc) < expires
        and 0 < (expires - created).total_seconds() <= 900
    )


def fresh(plan, current):
    require(readiness(current)["ready"])
    require(
        current["identity"] == plan["source_identity"]
        and fingerprint(current) == plan["state_fingerprint"]
        and focus_pin(current) == plan["focus_pin"]
    )


def payload(plan):
    return {
        "snapshot_digest": plan["snapshot_digest"],
        "identity_digest": digest(plan["source_identity"]),
        "state_fingerprint": plan["state_fingerprint"],
        "focus_digest": digest(plan["focus_pin"]),
        "selection": plan["selection"],
        "omission_pins": [v["process_pin_digest"] for v in plan["recovery"]["omissions"]],
        "private_ref": plan["recovery"].get("observation", {}).get("private_ref"),
        **(additive.payload_fields(plan) if plan["recovery"]["schema"] == ADDITIVE else {}),
    }


def observe(adapter, plan, phase):
    value = observation(
        adapter.call(phase, payload(plan)),
        digest(adapter.profile["legacy_locations"]),
        adapter.profile["schema"],
    )
    require(
        value["identity_digest"] == digest(plan["source_identity"])
        and value["state_fingerprint"] == plan["state_fingerprint"]
        and value["focus_digest"] == digest(plan["focus_pin"])
    )
    require(
        all(
            item["pin"]["boot_id"] == plan["source_identity"]["boot_id"]
            and item["pin"]["uid"] == os.getuid()
            for item in value["processes"]
        )
    )
    require(len({item["pin"]["pid"] for item in value["processes"]}) == len(value["processes"]))
    if adapter.profile["schema"] == ADDITIVE:
        require(value["saved_set"] == plan["recovery"]["saved_set"])
    if adapter.profile["schema"] == VERSION2:
        for item in value["utilities"]:
            require(item["host_pin"]["boot_id"] == plan["source_identity"]["boot_id"])
            require(item["host_pin"]["uid"] == os.getuid())
            require(item["host_pin"]["pid"] in plan["selection"]["pids"])
            require(item["identity"]["pid"] not in plan["selection"]["pids"])
    return value


def propose(
    store,
    snapshot_key,
    config,
    current,
    *,
    omissions=(),
    mode="replacement",
    saved_set=None,
    **selectors,
):
    require(config is not None)
    profile = load_profile(config)
    require(mode in ("replacement", "additive"))
    require((mode == "additive") == (profile["schema"] == ADDITIVE))
    if mode == "additive":
        require(not omissions and saved_set is not None)
        require(selectors.get("app_id") is None and selectors.get("version") is None)
        require(not any(v for k, v in selectors.items() if k != "ttl_seconds"))
    else:
        require(saved_set is None)
    snapshot = store.get("snapshots", snapshot_key)
    plan = build_plan(snapshot, intent="inspect", **selectors)
    plan["intent"] = "reconstruct"
    plan["fidelity"] = {
        "layout": "reconstruction-target-not-causal-window-map",
        "native_state": "saved-conversations-only",
        "process_memory": "unsupported",
    }
    if mode == "additive":
        additive.prepare_plan(plan, saved_set)
    omission_keys = sorted(omissions)
    keys(omission_keys)
    # Only digests are sent on initial observation; full typed decisions come from fresh pins.
    plan["recovery"] = {
        "schema": profile["schema"],
        "contract": CONTRACT,
        "profile_digest": digest(profile),
        "omissions": [{"process_pin_digest": key} for key in omission_keys],
        **({"mode": "additive", "saved_set": saved_set} if mode == "additive" else {}),
    }
    fresh(plan, current)
    adapter = Adapter(profile)
    value = observe(adapter, plan, "observe")
    counts, decisions, blockers = coverage(value, omission_keys, profile["schema"])
    if not legacy(value["legacy"], digest(profile["legacy_locations"])):
        blockers.append("legacy-attempt-coverage-incomplete-or-unresolved")
    if any(
        item["status"] not in successes(profile["schema"]) for item in Ledger(profile).disposition()
    ):
        blockers.append("canonical-attempt-unresolved")
    blockers += plan["admission"]["blockers"]
    plan["recovery"].update(observation=value, coverage=counts, omissions=decisions)
    plan["admission"] = {
        "status": "blocked" if blockers else "awaiting-approval",
        "blockers": sorted(set(blockers)),
        "warnings": additive.warnings()
        if mode == "additive"
        else [
            "reconstruction-only; exact restart/migration remain blocked",
            "accepted loss required: saved-conversations-v1 (memory, drafts, scrollback, shell state, hidden-tab order)",
            "desired map is the original target topology, not predicted replacement identities",
            "non-atomic-focus-move; operator must remain idle",
            f"native coverage: owned={counts['owned_native_processes']}, associated={counts['associated_processes']}, omitted={counts['omitted_associations']}, unique={counts['unique_saved_conversations']}",
            *[f"separate association omission approval required: {key}" for key in omission_keys],
        ],
    }
    if profile["schema"] == VERSION2:
        plan["admission"]["warnings"] += [
            f"utility coverage: owned={counts['owned_utilities']}, image-unobservable={counts['image_unobservable_utilities']}",
            *[
                f"separate utility image limit approval required: {key}"
                for key in utility_limits(value)
            ],
        ]
    key = store.put("plans", plan)
    return {
        "plan_digest": key,
        "admission": plan["admission"],
        "coverage": counts,
        "omission_candidates": [
            digest(item["pin"]) for item in value["processes"] if item["session_ref"] is None
        ],
        "runtime_effects": "none",
    }


def validate(store, key, current, adapter):
    plan = store.get("plans", key)
    require(
        plan.get("intent") == "reconstruct"
        and plan["recovery"]["schema"] == adapter.profile["schema"]
        and plan["recovery"]["contract"] == CONTRACT
        and plan["recovery"]["profile_digest"] == adapter.key
        and plan["admission"]["status"] == "awaiting-approval"
        and not plan["admission"]["blockers"]
    )
    lifetime(plan)
    fresh(plan, store.get("snapshots", plan["snapshot_digest"]))
    fresh(plan, current)
    value = observe(adapter, plan, "admit")
    require(value == plan["recovery"]["observation"])
    counts, omissions, blockers = coverage(
        value,
        [v["process_pin_digest"] for v in plan["recovery"]["omissions"]],
        adapter.profile["schema"],
    )
    require(
        not blockers
        and counts == plan["recovery"]["coverage"]
        and omissions == plan["recovery"]["omissions"]
    )
    require(legacy(value["legacy"], digest(adapter.profile["legacy_locations"])))
    Ledger(adapter.profile).available()
    return plan


def approval_record(plan, key):
    if plan["recovery"]["schema"] == ADDITIVE:
        additive.plan_fields(plan["recovery"])
    else:
        fields(
            plan["recovery"],
            ("schema", "contract", "profile_digest", "observation", "coverage", "omissions"),
        )
    require(plan["recovery"]["contract"] == CONTRACT)
    schema = version(plan["recovery"]["schema"])
    observed = plan["recovery"]["observation"]
    observation(observed, observed["legacy"]["locations_digest"], schema)
    counts, decisions, blockers = coverage(
        observed, [v["process_pin_digest"] for v in plan["recovery"]["omissions"]], schema
    )
    require(
        not blockers
        and counts == plan["recovery"]["coverage"]
        and decisions == plan["recovery"]["omissions"]
    )
    return {
        "schema": schema,
        "plan_digest": key,
        "expires_at": plan["expires_at"],
        "scope": CONTRACT,
        "profile_digest": plan["recovery"]["profile_digest"],
        "accepted_omissions": [v["process_pin_digest"] for v in plan["recovery"]["omissions"]],
        **(additive.approval_fields(plan) if schema == ADDITIVE else {}),
        **(
            {"accepted_utility_limits": utility_limits(plan["recovery"]["observation"])}
            if schema == VERSION2
            else {}
        ),
    }


def approve(store, key, capture, *, confirmation, losses, omissions, utility_limits_accepted=()):
    require(confirmation == key and losses == CONTRACT)
    plan = store.get("plans", key)
    require(sorted(omissions) == [v["process_pin_digest"] for v in plan["recovery"]["omissions"]])
    keys(sorted(omissions))
    keys(sorted(utility_limits_accepted))
    require(
        sorted(utility_limits_accepted)
        == approval_record(plan, key).get("accepted_utility_limits", [])
    )
    profile = load_profile(expected=plan["recovery"]["profile_digest"])
    with operation_lock(plan["source_identity"]):
        plan = validate(store, key, capture(), Adapter(profile))
        record = approval_record(plan, key)
        approval_key = digest(record)
        require(
            not store.path("used", approval_key).exists()
            and not Ledger(profile).store.path("recovery-prepared", approval_key).exists()
        )
        return {"approval_digest": store.put("approvals", record), "runtime_effects": "none"}


def execute(store, key, capture):
    approval = store.get("approvals", key)
    plan = store.get("plans", approval["plan_digest"])
    require(approval == approval_record(plan, approval["plan_digest"]))
    profile = load_profile(expected=plan["recovery"]["profile_digest"])
    adapter, ledger = Adapter(profile), Ledger(profile)
    with operation_lock(plan["source_identity"]) as fd:
        plan = validate(store, approval["plan_digest"], capture(), adapter)
        require(
            not store.path("used", key).exists()
            and not ledger.store.path("recovery-prepared", key).exists()
        )
        # Canonical copies make inspection independent of a caller's current state root.
        ledger.store.put("plans", plan)
        ledger.store.put("approvals", approval)
        pair = ledger.prepare(store, key, approval["plan_digest"])
        try:
            evidence = adapter.call(
                "execute",
                {
                    "attempt_digest": key,
                    "approval": approval,
                    "plan_digest": approval["plan_digest"],
                    "admitted": payload(plan),
                },
                lock_fd=fd,
                expires_at=plan["expires_at"],
                journal=lambda kind, value: ledger.event(key, kind, value),
            )
            require(
                bool(adapter.events)
                or (
                    profile["schema"] == ADDITIVE
                    and not plan["recovery"]["observation"]["saved_selection"]["missing_refs"]
                )
            )
            report = receipt(plan, key, evidence, history_complete=True, events=adapter.events)
        except (ValueError, OSError, KeyError, TypeError):
            report = receipt(plan, key, None, history_complete=False, events=adapter.events)
            report["reason"] = "worker-or-proof-failed; no-retry-or-cleanup-authorized"
        receipt_key = ledger.finish(store, pair, report)
        return {"receipt_digest": receipt_key, **report}


def inspect_attempt(profile, attempt):
    from contextlib import nullcontext

    from . import recovery_diagnostics as diagnostic
    from .recovery_protocol import boolean, count, hexkey

    hexkey(attempt)
    ledger = Ledger(profile, read_only=True)
    plan = None
    try:
        approval = ledger.store.get("approvals", attempt)
        candidate = ledger.store.get("plans", approval["plan_digest"])
        require(approval == approval_record(candidate, approval["plan_digest"]))
        require(candidate["recovery"]["schema"] == ledger.historical(attempt).schema)
        require(
            candidate["recovery"]["profile_digest"] == ledger.historical(attempt).profile_digest
        )
        plan = candidate
    except diagnostic.FAULTS:
        pass
    with operation_lock(plan["source_identity"]) if plan else nullcontext():
        canonical = diagnostic.accounting(ledger, attempt)
        evidence = diagnostic.events(ledger, attempt)
        history = next(
            item["status"] for item in canonical["attempts"] if item["attempt_digest"] == attempt
        )
        value, adapter_state, adapter_complete = None, "unknown", False
        if (
            plan is not None
            and plan["recovery"]["profile_digest"] == digest(profile)
            and plan["recovery"]["schema"] == profile["schema"]
        ):
            try:
                candidate = Adapter(profile).call(
                    "inspect",
                    {
                        "attempt_digest": attempt,
                        "plan_digest": approval["plan_digest"],
                        "admitted": payload(plan),
                    },
                )
                fields(candidate, ("legacy", "interrupted", "unresolved_children"))
                legacy_complete = legacy(candidate["legacy"], digest(profile["legacy_locations"]))
                boolean(candidate["interrupted"])
                count(candidate["unresolved_children"])
                value, adapter_state = candidate, "valid"
                adapter_complete = (
                    legacy_complete
                    and not candidate["interrupted"]
                    and candidate["unresolved_children"] == 0
                )
            except diagnostic.FAULTS:
                pass
        return {
            "attempt_digest": attempt,
            "status": history
            if adapter_complete and canonical["scan"] == "bounded"
            else "indeterminate",
            "historical_status": history,
            "canonical": canonical["attempts"],
            "canonical_scan": canonical,
            "adapter": value,
            "adapter_accounting": adapter_state,
            "plan_accounting": "valid" if plan else "unknown",
            "interruption_evidence": evidence["records"],
            "event_scan": evidence,
            "fresh_native_verification": False,
            "runtime_effects": "none",
            "retry_authorized": False,
        }


def inspect_or_verify(store, attempt, *, verify=False):
    if not verify:
        # Canonical evidence is readable despite executable drift. Adapter.call still
        # independently validates the complete profile/pins before any invocation.
        return inspect_attempt(identify_profile(), attempt)
    profile = load_profile()
    ledger = Ledger(profile, read_only=True)
    approval = ledger.store.get("approvals", attempt)
    plan = ledger.store.get("plans", approval["plan_digest"])
    require(approval == approval_record(plan, approval["plan_digest"]))
    require(
        plan["recovery"]["profile_digest"] == digest(profile)
        and plan["recovery"]["schema"] == profile["schema"]
    )
    # Inspection/verification are read-only wrt physical effects, serialized against writers.
    with operation_lock(plan["source_identity"]):
        dispositions = ledger.disposition()
        history = next(item["status"] for item in dispositions if item["attempt_digest"] == attempt)
        adapter = Adapter(profile)
        value = adapter.call(
            "verify" if verify else "inspect",
            {
                "attempt_digest": attempt,
                "plan_digest": approval["plan_digest"],
                "admitted": payload(plan),
            },
        )
        report = receipt(
            plan,
            attempt,
            value,
            history_complete=history in successes(profile["schema"]),
            events=[],
        )
        report["historical_status"] = history
        report["fresh_verification"] = True
        return {"receipt_digest": store.put("receipts", report), **report}
