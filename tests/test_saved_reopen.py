"""Handwritten additive effect/proof oracles; all transports and state are fabricated."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_recovery_orchestration import approve, command, execute
from test_recovery_review_regressions import repin
from test_saved_reopen_backend import REF, SAVED_SET, provision

from niri_desktop_continuity import cli, operation_lock, recovery, recovery_profile
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_protocol import ADDITIVE, CONTRACT, observation, proof
from niri_desktop_continuity.store import Store


@pytest.fixture(name="saved")
def saved_fixture(tmp_path, monkeypatch):
    def make(**kwargs):
        data = provision(tmp_path / "fake", **kwargs)
        root = data["root"]
        monkeypatch.setattr(operation_lock, "runtime_root", lambda: root / "runtime")
        monkeypatch.setattr(recovery_profile, "profile_path", lambda: root / "profile.json")
        monkeypatch.setattr(cli, "capture", lambda **_: deepcopy(data["snapshot"]))
        return data

    return make


def plan(data, *extra):
    return command(
        data,
        "plan",
        data["snapshot_digest"],
        "--intent",
        "reconstruct",
        "--mode",
        "additive",
        "--saved-set",
        SAVED_SET,
        "--adapter-config",
        str(data["root"] / "config.json"),
        *extra,
    )[0]["plan_digest"]


def settings(data):
    return json.loads((data["root"] / "settings.json").read_text())


def effects(data):
    path = data["root"] / "effects.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("present", [False, True])
def test_complete_existing_cli_lifecycle_without_old_processes(saved, present):
    data = saved(present=present)
    key = plan(data)
    store = Store(data["root"] / "state")
    proposal = store.get("plans", key)
    assert proposal["selection"] == {
        "window_ids": [],
        "pids": [],
        "requested_window_ids": [],
        "requested_pids": [],
        "app_id": None,
        "version": None,
    }
    assert proposal["affected"]["window_ids"] == proposal["affected"]["pids"] == []
    assert proposal["recovery"]["observation"]["processes"] == []
    assert proposal["desired"]["windows"] == data["snapshot"]["windows"]
    preview, code = command(data, "preview", key, "--kind", "plans")
    assert code == 0 and preview["runtime_effects"] == "none"
    approved = approve(data, key)
    assert approved == approve(data, key) and not effects(data)
    assert store.get("approvals", approved)["saved_set"] == SAVED_SET
    report, code = execute(data, approved)
    assert code == 0 and report["status"] == "verified" and report["schema"] == ADDITIVE
    # Handwritten oracle: launch the missing ref once, then only the admitted focus.
    assert effects(data) == (
        []
        if present
        else [
            {"kind": "launch", "target_ref": REF},
            {"kind": "focus", "target_ref": digest(proposal["focus_pin"])},
        ]
    )
    assert report["saved_conversations_restored"] == int(not present)
    assert report["saved_conversations_already_present"] == int(present)
    assert report["saved_conversations_unresolved"] == 0
    assert set(report["proof"]["dimensions"]) == {
        "causal_ownership",
        "new_images",
        "focus",
        "protected_preservation",
    }
    assert report["process_memory"] == "unsupported"
    verified, code = command(data, "verify", approved, "--kind", "reconstruction")
    assert code == 0 and verified["status"] == "verified"
    inspected, code = command(data, "inspect", approved, "--kind", "reconstruction")
    assert code == 0 and inspected["status"] == "verified"
    assert inspected["retry_authorized"] is False
    assert Ledger(data["profile"]).disposition() == [
        {"attempt_digest": approved, "status": "verified"}
    ]
    with pytest.raises(ValueError):
        execute(data, approved)
    other = Store(data["root"] / "other")
    for kind, address in (
        ("snapshots", data["snapshot_digest"]),
        ("plans", key),
        ("approvals", approved),
    ):
        other.put(kind, store.get(kind, address))
    with pytest.raises(ValueError):
        recovery.execute(other, approved, cli.capture)


@pytest.mark.parametrize(
    "mode,count",
    [
        ("shutdown", 0),
        ("service", 0),
        ("layout", 0),
        ("duplicate", 1),
        ("wrong-ref", 0),
        ("early-focus", 0),
        ("wrong-focus", 1),
        ("omitted-launch", 0),
        ("disconnect", 0),
    ],
)
def test_exact_effect_permits_stop_without_retry(saved, mode, count, monkeypatch):
    data = saved(mode=mode)
    approved = approve(data, plan(data))
    report, code = execute(data, approved)
    assert code == 2 and report["status"] == "indeterminate"
    assert len(effects(data)) == count
    assert all(item["kind"] == "launch" for item in effects(data))
    before = (data["root"] / "ledger/recovery-terminal" / f"{approved}.json").read_bytes()
    good = settings(data)["proof"]
    monkeypatch.setattr(Adapter, "call", lambda *a, **kw: deepcopy(good))
    fresh, code = command(data, "verify", approved, "--kind", "reconstruction")
    assert code == 2 and fresh["status"] == "indeterminate"
    assert fresh["saved_conversations_restored"] == 0
    assert (data["root"] / "ledger/recovery-terminal" / f"{approved}.json").read_bytes() == before
    with pytest.raises(ValueError):
        execute(data, approved)


def test_present_ref_never_grants_launch(saved):
    data = saved(present=True, mode="no-op-launch")
    report, code = execute(data, approve(data, plan(data)))
    assert code == 2 and report["status"] == "indeterminate" and not effects(data)


@pytest.mark.parametrize(
    "predicate", ["file", "cwd", "runtime", "bootstrap", "surface", "causal_window"]
)
def test_each_native_predicate_required_for_missing_and_present(saved, predicate):
    data = saved()
    value = settings(data)
    value["proof"]["native"][0][predicate] = False
    assert proof(value["proof"], [REF], ADDITIVE) is False
    repin(data, value)
    report, code = execute(data, approve(data, plan(data)))
    assert code == 2 and report["status"] == "partial"
    assert report["saved_conversations_restored"] == 0


@pytest.mark.parametrize(
    "dimension", ["causal_ownership", "new_images", "focus", "protected_preservation"]
)
def test_each_additive_dimension_mandatory(saved, dimension):
    data = saved()
    value = settings(data)["proof"]
    value["dimensions"][dimension]["status"] = "unknown"
    assert proof(value, [REF], ADDITIVE) is False


@pytest.mark.parametrize(
    "damage", ["duplicate", "overlap", "union", "old-process", "extra", "wrong-set"]
)
def test_closed_saved_selection_refuses_identity_confusion(saved, damage):
    data = saved()
    value = settings(data)
    obs = value["observation"]
    if damage == "duplicate":
        obs["saved_selection"]["missing_refs"].append(REF)
    elif damage == "overlap":
        obs["saved_selection"]["present_refs"] = [REF]
    elif damage == "union":
        obs["session_refs"] = []
    elif damage == "old-process":
        obs["processes"] = [{"pid": 999}]
    elif damage == "extra":
        obs["argv"] = ["fabricated"]
    elif damage == "wrong-set":
        obs["saved_set"] = "0" * 64
    if damage != "wrong-set":
        with pytest.raises(ValueError):
            observation(obs, digest([]), ADDITIVE)
    repin(data, value)
    with pytest.raises(ValueError):
        plan(data)
    assert not effects(data)


@pytest.mark.parametrize("damage", ["unsupported", "unproved", "unresolved", "empty"])
def test_blocked_selection_never_approved(saved, damage):
    data = saved()
    value = settings(data)
    obs = value["observation"]
    if damage == "unsupported":
        obs["supported"] = False
    elif damage == "unproved":
        obs["selection_proved"] = False
    elif damage == "unresolved":
        obs["saved_selection"].update(missing_refs=[], unresolved_refs=[REF])
    else:
        obs["saved_selection"]["missing_refs"] = []
        obs["session_refs"] = []
    repin(data, value)
    key = plan(data)
    with pytest.raises(ValueError):
        approve(data, key)
    assert not effects(data)


@pytest.mark.parametrize(
    "extra",
    [
        ["--window-id", "1"],
        ["--pid", "101"],
        ["--app-id", "fabricated"],
        ["--app-id", ""],
        ["--version", "1"],
        ["--version", ""],
        ["--omit-association", "0" * 64],
        ["--mode", "replacement"],
        ["--saved-set", "bad"],
    ],
)
def test_mode_does_not_accept_destructive_or_untyped_selection(saved, extra):
    data = saved()
    with pytest.raises(ValueError):
        plan(data, *extra)
    assert not (data["root"] / "phases.jsonl").exists()


def test_fresh_state_expiry_pin_and_scope_drift_refuse(saved):
    data = saved()
    key = plan(data)
    store = Store(data["root"] / "state")
    old = deepcopy(data["snapshot"])
    data["snapshot"]["windows"][0]["is_focused"] = False
    with pytest.raises(ValueError):
        approve(data, key)
    data["snapshot"] = old
    value = store.get("plans", key)
    value["created_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
    value["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    expired = store.put("plans", value)
    with pytest.raises(ValueError):
        approve(data, expired)
    (data["root"] / "endpoint.py").write_text("# fabricated pin drift\n")
    with pytest.raises(ValueError):
        approve(data, key)
    assert not effects(data)


def test_approval_explicit_losses_and_saved_set_binding(saved):
    data = saved()
    key = plan(data)
    store = Store(data["root"] / "state")
    for confirm, loss in (("0" * 64, CONTRACT), (key, None)):
        with pytest.raises(ValueError):
            recovery.approve(
                store, key, cli.capture, confirmation=confirm, losses=loss, omissions=[]
            )
    approved = approve(data, key)
    value = store.get("approvals", approved)
    value["saved_set"] = "0" * 64
    forged = store.put("approvals", value)
    with pytest.raises(ValueError):
        execute(data, forged)
    assert not effects(data)
