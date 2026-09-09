"""Frozen pre-projection field oracles and non-initial projection drift transport tests."""

import json
from copy import deepcopy

import pytest
from test_recovery_orchestration import approve, execute
from test_recovery_review_regressions import repin
from test_saved_reopen import effects, plan
from test_saved_reopen import saved_fixture as saved_fixture
from test_saved_reopen_projections import projected

from niri_desktop_continuity import recovery
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.store import Store


def test_literal_preprojection_receipt_schema_remains_canonically_readable(saved):
    data = saved()
    key = plan(data)
    approval = approve(data, key)
    report, code = execute(data, approval)
    assert code == 0
    ledger = Ledger(data["profile"])
    # Frozen pre-projection field oracle: do not derive this list from receipt helpers.
    names = (
        "schema",
        "kind",
        "attempt_digest",
        "status",
        "proof",
        "events",
        "coverage",
        "overall_native_coverage_complete",
        "accepted_omissions",
        "mode",
        "saved_set",
        "saved_conversations_restored",
        "saved_conversations_already_present",
        "saved_conversations_unresolved",
        "layout",
        "destructive_effects",
        "process_memory",
        "provider_usability",
        "human_acceptance",
    )
    historical = {name: report[name] for name in names}
    historical_key = ledger.store.put("receipts", historical)
    marker_path = ledger.store.path("recovery-terminal", approval)
    marker = json.loads(marker_path.read_text())
    marker["receipt_digest"] = historical_key
    # Replace only this fabricated canonical marker to point at the frozen-schema artifact.
    marker_path.write_text(json.dumps(marker))
    assert ledger.attempt_status(approval) == "verified"
    stored_approval = ledger.store.get("approvals", approval)
    assert set(stored_approval) == {
        "schema",
        "plan_digest",
        "expires_at",
        "scope",
        "profile_digest",
        "accepted_omissions",
        "mode",
        "saved_set",
    }
    assert ledger.store.get("receipts", historical_key) == historical
    assert len(effects(data)) == 2


@pytest.mark.parametrize("phase", ["admit", "execute", "verify", "inspect"])
@pytest.mark.parametrize(
    "damage", ["unchanged", "omitted-grouping", "changed-grouping", "changed-diagnostic"]
)
def test_every_noninitial_phase_reaches_owner_with_exact_admitted_projections(saved, phase, damage):
    data = saved()
    repin(data, projected(data))
    key = plan(data)
    approval = approve(data, key)
    stored = Store(data["root"] / "state").get("plans", key)
    admitted = deepcopy(recovery.payload(stored))
    if damage == "omitted-grouping":
        del admitted["grouping"]
    elif damage == "changed-grouping":
        admitted["grouping"]["groups"][0]["session_refs"].reverse()
    elif damage == "changed-diagnostic":
        admitted["diagnostics"]["capacity"] = "unproved"
    payload = (
        admitted
        if phase == "admit"
        else {
            "attempt_digest": approval,
            "plan_digest": key,
            "admitted": admitted,
        }
    )
    kwargs = {}
    with (data["root"] / "fabricated-inherited-lock").open("w") as lock:
        if phase == "execute":
            cli_store = Store(data["root"] / "state")
            record = cli_store.get("approvals", approval)
            ledger = Ledger(data["profile"])
            ledger.store.put("plans", stored)
            ledger.store.put("approvals", record)
            ledger.prepare(cli_store, approval, key)
            payload["approval"] = record
            kwargs = {
                "lock_fd": lock.fileno(),
                "expires_at": record["expires_at"],
                "journal": lambda kind, value: ledger.event(approval, kind, value),
            }
        # The handwritten endpoint compares against its separately retained projection.
        # This does not substitute for production machine-manifest/native qualification.
        if damage == "unchanged":
            assert Adapter(data["profile"]).call(phase, payload, **kwargs)
        else:
            with pytest.raises(ValueError):
                Adapter(data["profile"]).call(phase, payload, **kwargs)
    assert [row["kind"] for row in effects(data)] == (
        ["launch", "launch", "launch", "focus"]
        if damage == "unchanged" and phase == "execute"
        else []
    )
