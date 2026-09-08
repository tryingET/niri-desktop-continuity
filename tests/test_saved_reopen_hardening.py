"""Adversarial saved-set accounting/authority tests, with no native application effects."""

from copy import deepcopy

import pytest
from test_recovery_orchestration import approve, command, execute
from test_recovery_review_regressions import repin
from test_saved_reopen import effects, plan, settings
from test_saved_reopen import saved_fixture as saved_fixture
from test_saved_reopen_backend import REF

from niri_desktop_continuity import recovery, recovery_adapter, recovery_additive
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_protocol import ADDITIVE, observation, proof
from niri_desktop_continuity.recovery_requests import admitted
from niri_desktop_continuity.store import Store


def test_mixed_present_missing_set_launches_only_missing_once(saved):
    data = saved()
    value = settings(data)
    refs = ["a" * 64, REF, "f" * 64]
    value["observation"].update(
        session_refs=refs,
        saved_selection={"missing_refs": refs[:2], "present_refs": refs[2:], "unresolved_refs": []},
    )
    native = value["proof"]["native"][0]
    value["proof"]["native"] = [{**native, "session_ref": ref} for ref in refs]
    repin(data, value)
    approval = approve(data, plan(data))
    report, code = execute(data, approval)
    assert code == 0 and report["status"] == "verified"
    assert [item["target_ref"] for item in effects(data) if item["kind"] == "launch"] == refs[:2]
    assert report["saved_conversations_restored"] == 2
    assert report["saved_conversations_already_present"] == 1
    assert Ledger(data["profile"]).disposition()[0]["status"] == "verified"


@pytest.mark.parametrize("field", ["app_id", "version"])
def test_empty_string_is_not_null_empty_live_selection(saved, field):
    data = saved()
    key = plan(data)
    stored = Store(data["root"] / "state").get("plans", key)
    payload = recovery.payload(stored)
    payload["selection"][field] = ""
    with pytest.raises(ValueError):
        admitted(payload, schema=ADDITIVE)


def test_expiry_between_launch_and_focus_never_authorizes_cleanup(saved, monkeypatch):
    data = saved()
    approval = approve(data, plan(data))
    original = recovery_adapter.unexpired

    def deadline(value):
        if effects(data):
            raise ValueError("fabricated expiry")
        original(value)

    monkeypatch.setattr(recovery_adapter, "unexpired", deadline)
    report, code = execute(data, approval)
    assert code == 2 and report["status"] == "indeterminate"
    assert [item["kind"] for item in effects(data)] == ["launch"]
    assert Ledger(data["profile"]).disposition()[0]["status"] == "indeterminate"


@pytest.mark.parametrize("damage", ["gap", "duplicate-target", "missing-focus", "wrong-target"])
def test_canonical_event_history_revalidates_exact_set_and_order(saved, damage):
    data = saved()
    key = plan(data)
    approval = approve(data, key)
    execute(data, approval)
    ledger = Ledger(data["profile"])
    evidence = ledger.events(approval)
    stored = Store(data["root"] / "state").get("plans", key)
    if damage == "gap":
        evidence[0]["intent"]["sequence"] = 1
    elif damage == "duplicate-target":
        evidence[1]["intent"].update(kind="launch", target_ref=REF)
    elif damage == "missing-focus":
        evidence.pop()
    else:
        evidence[0]["intent"]["target_ref"] = "0" * 64
    with pytest.raises(ValueError):
        recovery_additive.validate_event_history(stored, evidence)


@pytest.mark.parametrize("damage", ["duplicate", "extra", "destructive-dimension"])
def test_native_proof_cannot_change_selected_identity_or_claim_old_tree(saved, damage):
    data = saved()
    value = settings(data)["proof"]
    if damage == "destructive-dimension":
        value["dimensions"]["old_tree_exit"] = {"status": "proved", "evidence_ref": "1" * 64}
    else:
        item = deepcopy(value["native"][0])
        if damage == "extra":
            item["session_ref"] = "f" * 64
        value["native"].append(item)
    with pytest.raises(ValueError):
        proof(value, [REF], ADDITIVE)


def test_missing_focus_or_saved_set_never_reaches_endpoint(saved):
    data = saved()
    with pytest.raises(ValueError):
        command(
            data,
            "plan",
            data["snapshot_digest"],
            "--intent",
            "reconstruct",
            "--mode",
            "additive",
            "--adapter-config",
            str(data["root"] / "config.json"),
        )
    assert not (data["root"] / "phases.jsonl").exists()


def test_additive_count_bound_reserves_one_focus_event(saved):
    data = saved()
    value = settings(data)["observation"]
    refs = [f"{index:064x}" for index in range(256)]
    value.update(
        session_refs=refs,
        saved_selection={"missing_refs": refs, "present_refs": [], "unresolved_refs": []},
    )
    with pytest.raises(ValueError):
        observation(value, digest([]), ADDITIVE)
