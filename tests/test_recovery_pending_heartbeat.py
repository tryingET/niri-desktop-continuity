"""Correlated pending keepalives extend liveness, never effect or expiry authority."""

import socket
import time

import pytest
from test_recovery_orchestration import approve, execute
from test_saved_reopen import effects, plan
from test_saved_reopen import saved_fixture as saved_fixture

from niri_desktop_continuity import recovery_adapter
from niri_desktop_continuity.recovery_adapter import heartbeat_reply
from niri_desktop_continuity.recovery_ledger import Ledger


def test_pending_heartbeat_shape_is_bound_to_exact_existing_intent():
    pending = {"sequence": 2, "intent_ref": "a" * 64, "kind": "launch", "target_ref": "b" * 64}
    beat = {"sequence": 2, "intent_ref": "a" * 64}
    assert heartbeat_reply(beat, pending) == beat
    assert pending == {
        "sequence": 2,
        "intent_ref": "a" * 64,
        "kind": "launch",
        "target_ref": "b" * 64,
    }
    assert heartbeat_reply({}, None) == {}
    with pytest.raises(ValueError):
        heartbeat_reply(beat, None)
    with pytest.raises(ValueError):
        heartbeat_reply({}, pending)


def test_slow_pending_preflight_can_exceed_five_seconds_without_new_permit(saved):
    data = saved(mode="pending-long")
    approval = approve(data, plan(data))
    started = time.monotonic()
    report, status = execute(data, approval)
    assert time.monotonic() - started >= 5
    assert status == 0 and report["status"] == "verified"
    assert [row["kind"] for row in effects(data)] == ["launch", "focus"]
    # Seven correlated keepalives do not create extra journal events/permits.
    assert len(report["events"]) == 2
    assert len(Ledger(data["profile"]).events(approval)) == 2
    with pytest.raises(ValueError):
        execute(data, approval)


@pytest.mark.parametrize(
    "mode",
    [
        "pending-empty",
        "pending-wrong-sequence",
        "pending-bool-sequence",
        "pending-wrong-intent",
        "pending-extra",
        "pending-second-effect",
        "pending-disconnect",
    ],
)
def test_pending_keepalive_cannot_change_scope_or_allow_another_effect(saved, mode):
    data = saved(mode=mode)
    approval = approve(data, plan(data))
    report, status = execute(data, approval)
    assert status == 2 and report["status"] == "indeterminate"
    assert effects(data) == []
    events = Ledger(data["profile"]).events(approval)
    assert len(events) == 1 and events[0]["outcome"] == "unresolved"
    assert report["events"] == []
    with pytest.raises(ValueError):
        execute(data, approval)


def test_pending_heartbeats_cannot_extend_absolute_approval_expiry(saved):
    data = saved(mode="pending-expiry")
    approval = approve(data, plan(data, "--ttl", "4"))
    report, status = execute(data, approval)
    assert status == 2 and report["status"] == "indeterminate"
    assert effects(data) == []
    assert (data["root"] / "cancelled").exists()
    assert len(Ledger(data["profile"]).events(approval)) == 1


def test_late_pending_heartbeat_does_not_resurrect_lease_even_with_patient_socket(
    saved, monkeypatch
):
    data = saved(mode="pending-stall")
    approval = approve(data, plan(data))
    pair = socket.socketpair

    class PatientSocket(socket.socket):
        def settimeout(self, seconds):
            super().settimeout(seconds * 2)

    def socketpair():
        parent, child = pair()
        return PatientSocket(fileno=parent.detach()), child

    monkeypatch.setattr(recovery_adapter.socket, "socketpair", socketpair)
    started = time.monotonic()
    report, status = execute(data, approval)
    assert time.monotonic() - started >= 5
    assert status == 2 and report["status"] == "indeterminate"
    assert effects(data) == []
    assert (data["root"] / "cancelled").exists()
