"""Handwritten v2 utility admission/proof and cross-version refusal oracles; no native effects."""

import json
from copy import deepcopy

import pytest
from test_recovery_backend import private_json
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture

from niri_desktop_continuity import recovery, recovery_profile
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_protocol import (
    VERSION,
    VERSION2,
    coverage,
    envelope,
    observation,
    proof,
)
from niri_desktop_continuity.recovery_requests import request_payload
from niri_desktop_continuity.store import Store


def settings(data):
    return json.loads((data["root"] / "settings.json").read_text())


def ref(data):
    return settings(data)["observation"]["utilities"][0]["utility_ref"]


def readdress(item):
    item["utility_ref"] = digest({k: item[k] for k in ("kind", "host_pin", "identity")})


@pytest.mark.parametrize("branch", ["observed-image", "capability-btop"])
@pytest.mark.parametrize("utility_only", [False, True])
def test_v2_handwritten_success(fixture, branch, utility_only):
    data = fixture(utility=branch, utility_only=utility_only)
    key = plan(data)
    accepted = ["--accept-utility-limit", ref(data)] if branch == "capability-btop" else []
    approval = approve(data, key, *accepted)
    assert approval == approve(data, key, *accepted)
    assert not (data["root"] / "effects.jsonl").exists()
    report, code = execute(data, approval)
    limited = branch == "capability-btop"
    expected = "verified-with-accepted-limitations" if limited else "verified"
    assert code == 0 and report["status"] == expected
    assert report["schema"] == VERSION2
    assert report["coverage"] == {
        "owned_native_processes": 0 if utility_only else 1,
        "associated_processes": 0 if utility_only else 1,
        "omitted_associations": 0,
        "unique_saved_conversations": 0 if utility_only else 1,
        "unresolved_associations": 0,
        "owned_utilities": 1,
        "image_unobservable_utilities": 1 if limited else 0,
    }
    assert report["saved_conversations_recovered"] == (0 if utility_only else 1)
    assert report["overall_image_coverage_complete"] is not limited
    assert report["overall_native_coverage_complete"] is not limited
    assert report["accepted_utility_limits"] == ([ref(data)] if limited else [])
    if utility_only:
        assert report["proof"]["native"] == []
    terminal = data["root"] / "ledger/recovery-terminal" / (approval + ".json")
    before = terminal.read_bytes()
    fresh, code = command(data, "verify", approval, "--kind", "reconstruction")
    assert code == 0 and fresh["status"] == fresh["historical_status"] == expected
    assert terminal.read_bytes() == before
    inspected, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 0 and inspected["status"] == expected
    with pytest.raises(ValueError):
        execute(data, approval)


def test_limits_and_omissions_are_independent(fixture):
    data = fixture(utility="capability-btop", missing=True)
    key = plan(data, "--omit-association", data["omission"])
    for args in (
        [],
        ["--accept-omission", data["omission"]],
        ["--accept-utility-limit", ref(data)],
        ["--accept-omission", data["omission"], "--accept-utility-limit", "0" * 64],
        [
            "--accept-omission",
            data["omission"],
            "--accept-utility-limit",
            ref(data),
            "--accept-utility-limit",
            ref(data),
        ],
    ):
        with pytest.raises(ValueError):
            approve(data, key, *args)
    assert not (data["root"] / "effects.jsonl").exists()
    approval = approve(
        data, key, "--accept-omission", data["omission"], "--accept-utility-limit", ref(data)
    )
    report, _ = execute(data, approval)
    assert report["status"] == "verified-with-accepted-limitations"
    assert report["accepted_omissions"][0]["process_pin_digest"] == data["omission"]
    assert report["accepted_utility_limits"] == [ref(data)]


@pytest.mark.parametrize(
    "damage",
    [
        "image",
        "parent",
        "uid",
        "boot",
        "pid",
        "ticks",
        "capabilities",
        "kind",
        "extra",
        "reference",
        "duplicate",
        "host-conflict",
    ],
)
def test_utility_identity_refusals(fixture, damage):
    data = fixture(utility="capability-btop")
    value = settings(data)["observation"]
    item = value["utilities"][0]
    identity = item["identity"]
    if damage == "image":
        identity["image_pin"] = value["processes"][0]["pin"]
    elif damage == "parent":
        identity["parent_pid"] = 999
    elif damage == "uid":
        identity["uid"] += 1
    elif damage == "boot":
        identity["boot_id"] = "foreign"
    elif damage == "pid":
        identity["pid"] = value["processes"][0]["pin"]["pid"]
    elif damage == "ticks":
        identity["start_ticks"] = True
    elif damage == "capabilities":
        identity["capabilities_digest"] = None
    elif damage == "kind":
        item["kind"] = "pi"
    elif damage == "extra":
        item["session_ref"] = "a" * 64
    elif damage == "host-conflict":
        value["processes"][0]["pin"]["pid"] = item["host_pin"]["pid"]
    if damage != "reference":
        readdress(item)
    else:
        item["utility_ref"] = "0" * 64
    if damage == "duplicate":
        value["utilities"].append(deepcopy(item))
    with pytest.raises(ValueError):
        observation(value, digest([]), VERSION2)


@pytest.mark.parametrize("field", ["pid", "start_ticks", "uid", "boot_id"])
def test_observed_image_must_agree_internally(fixture, field):
    data = fixture(utility="observed-image")
    value = settings(data)["observation"]
    item = value["utilities"][0]
    item["identity"]["image_pin"][field] = "other" if field == "boot_id" else 999
    readdress(item)
    with pytest.raises(ValueError):
        observation(value, digest([]), VERSION2)


@pytest.mark.parametrize(
    "field,value", [("owned", False), ("identity_proved", False), ("protected_overlap", True)]
)
def test_utility_ownership_not_waivable(fixture, field, value):
    data = fixture(utility="capability-btop", utility_only=True)
    observed = settings(data)["observation"]
    observed["utilities"][0][field] = value
    counts, omissions, blockers = coverage(observed, [ref(data)], VERSION2)
    assert "mandatory-utility-ownership-identity-or-protection-unproved" in blockers
    assert "omission-not-an-exact-missing-association" in blockers
    assert omissions == [] and counts["unique_saved_conversations"] == 0


@pytest.mark.parametrize(
    "field",
    [
        "identity",
        "installed_file",
        "capabilities",
        "sole_owned_leaf",
        "causal_window",
        "running_image",
    ],
)
def test_every_utility_predicate_required(fixture, field):
    data = fixture(utility="capability-btop")
    value = settings(data)
    value["proof"]["utilities"][0][field] = "unknown" if field == "running_image" else False
    assert not proof(value["proof"], ["c" * 64], VERSION2, value["observation"]["utilities"])


@pytest.mark.parametrize("damage", ["missing", "extra", "wrong-branch", "duplicate", "v1-body"])
def test_proof_exact_utility_set_and_branch(fixture, damage):
    data = fixture(utility="capability-btop")
    value = settings(data)
    result = value["proof"]
    if damage == "missing":
        result["utilities"] = []
    elif damage == "extra":
        result["utilities"][0]["utility_ref"] = "0" * 64
    elif damage == "wrong-branch":
        result["utilities"][0]["running_image"] = "proved"
    elif damage == "duplicate":
        result["utilities"] *= 2
    else:
        del result["utilities"]
    with pytest.raises(ValueError):
        proof(result, ["c" * 64], VERSION2, value["observation"]["utilities"])


@pytest.mark.parametrize(
    "mode",
    [
        "die-after-intent",
        "execute-pending-heartbeat",
        "execute-dispatched-heartbeat",
        "execute-final-invalid",
    ],
)
def test_v2_faults_preserve_limits_and_no_upgrade(fixture, monkeypatch, mode):
    data = fixture(utility="capability-btop", mode=mode)
    approval = approve(data, plan(data), "--accept-utility-limit", ref(data))
    report, code = execute(data, approval)
    assert code == 2 and report["status"] == "indeterminate"
    assert report["accepted_utility_limits"] == [ref(data)]
    assert report["overall_image_coverage_complete"] is False
    monkeypatch.setattr(Adapter, "call", lambda *a, **k: settings(data)["proof"])
    fresh, code = command(data, "verify", approval, "--kind", "reconstruction")
    assert code == 2 and fresh["status"] == "indeterminate"
    assert fresh["saved_conversations_recovered"] == 0


def test_v2_damaged_accounting_retains_evidence(fixture):
    data = fixture(utility="capability-btop")
    approval = approve(data, plan(data), "--accept-utility-limit", ref(data))
    execute(data, approval)
    ledger = Ledger(data["profile"])
    index = digest({"attempt_digest": approval, "sequence": 0, "event": "result"})
    damaged = ledger.store.path("recovery-events", index)
    damaged.write_text("{")
    report, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 2 and report["interruption_evidence"][0]["intent"]["kind"] == "shutdown"
    assert report["interruption_evidence"][0]["outcome"] == "unresolved"
    assert report["retry_authorized"] is False and damaged.read_text() == "{"
    with pytest.raises(ValueError):
        command(data, "verify", approval, "--kind", "reconstruction")


@pytest.mark.parametrize(
    "surface",
    ["profile", "config", "observation", "proof", "frame", "approval", "plan", "event", "receipt"],
)
def test_no_version_confusion(fixture, surface):
    data = fixture(utility="capability-btop")
    value = settings(data)
    with pytest.raises(ValueError):
        if surface in ("profile", "config"):
            path = data["root"] / (surface + ".json")
            altered = json.loads(path.read_text())
            altered["schema"] = VERSION
            private_json(path, altered)
            recovery_profile.load_profile(data["root"] / "config.json")
        elif surface == "observation":
            observation(value["observation"], digest([]), VERSION)
        elif surface == "proof":
            proof(value["proof"], ["c" * 64], VERSION)
        elif surface == "frame":
            request = {"protocol": VERSION2, "phase": "observe"}
            envelope(
                {
                    "protocol": VERSION,
                    "phase": "observe",
                    "request_digest": digest(request),
                    "type": "result",
                    "body": {},
                },
                request,
            )
        else:
            store = Store(data["root"] / "state")
            key = plan(data)
            if surface == "plan":
                candidate = store.get("plans", key)
                candidate["recovery"]["schema"] = VERSION
                approve(data, store.put("plans", candidate))
            else:
                approval = approve(data, key, "--accept-utility-limit", ref(data))
                record = store.get("approvals", approval)
                if surface == "approval":
                    record["schema"] = VERSION
                    request_payload(
                        "execute",
                        {
                            "attempt_digest": digest(record),
                            "plan_digest": key,
                            "approval": record,
                            "admitted": recovery.payload(store.get("plans", key)),
                        },
                        profile_digest=digest(data["profile"]),
                        expires_at=record["expires_at"],
                        schema=VERSION2,
                    )
                else:
                    execute(data, approval)
                    ledger = Ledger(data["profile"])
                    if surface == "event":
                        event = ledger.read_event(approval, 0, "intent")
                        changed = ledger.store.get("receipts", event["receipt_digest"])
                        changed["schema"] = VERSION
                        index = digest(
                            {"attempt_digest": approval, "sequence": 0, "event": "intent"}
                        )
                        private_json(
                            ledger.store.path("recovery-events", index),
                            {"receipt_digest": ledger.store.put("receipts", changed)},
                        )
                    else:
                        terminal = ledger.store.recovery_marker("recovery-terminal", approval)
                        changed = ledger.store.get("receipts", terminal["receipt_digest"])
                        changed["schema"] = VERSION
                        terminal["receipt_digest"] = ledger.store.put("receipts", changed)
                        private_json(ledger.store.path("recovery-terminal", approval), terminal)
                    ledger.attempt_status(approval)


def test_v1_history_inspectable_after_owner_upgrade_without_invocation(fixture, monkeypatch):
    data = fixture()
    approval = approve(data, plan(data))
    execute(data, approval)
    profile = deepcopy(data["profile"])
    profile["schema"] = VERSION2
    # A fabricated declaration only; diagnostic routing does not open platform files.
    profile["platform"] = {
        "kind": "owner-trusted-application-platform",
        "pins": [{"path": str(data["root"] / "absent-platform"), "sha256": "a" * 64}],
    }
    private_json(data["root"] / "profile.json", profile)

    def forbidden(*a, **kw):
        raise AssertionError("historical adapter invoked")

    monkeypatch.setattr(Adapter, "call", forbidden)
    inspected, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 2 and inspected["adapter_accounting"] == "unknown"
    assert inspected["canonical"][0]["status"] == "verified"
    assert inspected["plan_accounting"] == "valid"
    assert inspected["interruption_evidence"][0]["outcome"] == "observed"
    with pytest.raises(ValueError):
        Ledger(profile).available()


def test_platform_pins_are_checked_before_dispatch(fixture):
    data = fixture(utility="observed-image")
    (data["root"] / "platform.txt").write_text("changed")
    with pytest.raises(ValueError):
        plan(data)
    assert not (data["root"] / "phases.jsonl").exists()
