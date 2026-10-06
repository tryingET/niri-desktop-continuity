"""Three distinct wire goldens: immutable old history is never a new live proof."""

import json
import time
from copy import deepcopy

import pytest
from test_restore_exited_contract import recorded, recorded_new, recorded_self_v2
from test_restore_exited_history import FAMILY, sha
from test_restore_exited_history import legacy_ten as legacy_ten

from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_exited as lifecycle
from niri_desktop_continuity import restore_exited_history as historical
from niri_desktop_continuity import restore_exited_model as model
from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_exited_values as v
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_reader import ReaderStore

OLD = "native-niri-continuing-peer-pidfd-esrch.v1"
NEW = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v1"
SELF_V2 = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v2"


def golden(s, *, method, completed=True, expired=False):
    """Hand-author stored testimony, without pretending the old method can run today."""
    active, chain, reader = lifecycle.source(s.store, s.identity, s.attempt)
    try:
        bound = historical.binding(
            ReaderStore(s.store, reader), active, chain, s.interrupted, s.result, s.exit_file
        )
    finally:
        reader.close()
    current = {OLD: recorded, NEW: recorded_new, SELF_V2: recorded_self_v2}[method](s)
    now = int(time.time()) - (1000 if expired else 0)
    plan = {
        "schema": "desktop-continuity.restore-disposition.v3",
        "intent": "restore-disposition",
        "created": now,
        "expires": now + 300,
        **bound,
        "platform": deepcopy(v.PLATFORM),
        "current": current,
        "limits": deepcopy(v.LIMITS),
    }
    key = s.store.put("plans", plan)
    approval = {
        "schema": "desktop-continuity.restore-disposition.v3",
        "family": FAMILY,
        "branch": "exact-process-exited-and-window-absent",
        "intent": "restore-disposition",
        "plan": key,
        "confirmation": key,
        "acceptance": "operator-accepted-partial",
        "attest_client_returned": True,
        "platform_ack": sha(plan["platform"]),
        "caller": current["caller"],
        "created": now,
        "expires": now + 300,
    }
    approval_key = s.store.put("approvals", approval)
    receipt = {
        "schema": "desktop-continuity.restore-disposition.v3",
        "family": FAMILY,
        "branch": "exact-process-exited-and-window-absent",
        "status": "operator-accepted-partial",
        "plan": key,
        "approval": approval_key,
        "attempt": s.attempt,
        "interrupted_receipt": s.interrupted,
        "process_receipt": plan["segment"]["process_receipt"],
        "proof_method": method,
        "current_digest": sha(current),
        "platform_ack": sha(plan["platform"]),
        "caller": current["caller"],
        "disposition_effects": [],
        "historical_completion": "unproved",
        "historical_preservation": "unproved",
        "historical_association": "recorded",
        "historical_layout": "two-observed-actions-incomplete",
        "outcome": "unresolved",
        "native_session": "not-proved",
        "retry_authorized": False,
    }
    if completed:
        s.store.consume(
            approval_key,
            {
                "schema": "desktop-continuity.restore-disposition.v3",
                "family": FAMILY,
                "branch": "exact-process-exited-and-window-absent",
                "intent": "restore-disposition",
                "approval": approval_key,
                "plan": key,
            },
        )
        receipt_key = s.store.put("receipts", receipt)
        history.durable_create(
            s.directory / f"{len(chain):08d}.json",
            {
                "schema": "desktop-continuity.restore-history.v3",
                "seq": len(chain),
                "previous": sha(chain[-1][0]),
                "type": "operator-disposition",
                "attempt": s.attempt,
                "receipt": receipt_key,
                "origin": plan["origin"],
            },
        )
    return key, approval_key, receipt


@pytest.mark.parametrize("method", [OLD, NEW, SELF_V2])
def test_three_completed_goldens_replay_and_inspect_without_native(legacy_ten, monkeypatch, method):
    s = legacy_ten
    key, approval, expected = golden(s, method=method)
    files = {
        p: p.read_bytes()
        for root in (s.store.root, s.directory)
        for p in root.rglob("*")
        if p.is_file()
    }
    monkeypatch.setattr(proof, "current", lambda *_a, **_k: pytest.fail("historical native query"))
    from niri_desktop_continuity import restore_exited_syscalls as calls

    def forbidden(*_a, **_k):
        pytest.fail("historical kernel query")

    monkeypatch.setattr("os.uname", forbidden)
    monkeypatch.setattr("os.pidfd_open", forbidden, raising=False)
    monkeypatch.setattr(calls, "identity", forbidden)
    monkeypatch.setattr(calls, "namespace", forbidden)

    monkeypatch.setattr(time, "time", lambda: s.store.get("plans", key)["expires"] + 1000)
    result = d.apply(s.store, approval)
    assert s.store.get("receipts", result["receipt_digest"]) == expected
    assert result["historical"] and result["effects"] == []
    assert (
        d.inspect(s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY)[
            "canonical"
        ]
        == "validated"
    )
    assert history.load(s.identity)[1] is None
    from niri_desktop_continuity.restore import restore

    result = restore(s.store, s.source, object(), apply=True, observe=forbidden)
    assert result["historical"] and result["effects"] == []
    assert result["proof_method"] == method
    assert {p: p.read_bytes() for p in files} == files
    monkeypatch.setattr(v, "METHOD", "ambient-wrong-default")
    assert model.receipt(key, approval, s.store.get("plans", key), expected["caller"]) == expected


@pytest.mark.parametrize("method", [OLD, NEW])
@pytest.mark.parametrize("stage", ["approve", "apply"])
def test_unfinished_old_method_refuses_before_native_barriers_or_writes(
    legacy_ten, monkeypatch, stage, method
):
    s = legacy_ten
    key, approval, _ = golden(s, method=method, completed=False)
    monkeypatch.setattr(proof, "current", lambda *_a, **_k: pytest.fail("legacy native query"))
    monkeypatch.setattr("os.fsync", lambda *_: pytest.fail("legacy authority barrier/write"))
    with pytest.raises(ValueError, match="historical current method"):
        if stage == "apply":
            d.apply(s.store, approval)
        else:
            d.approve(
                s.store,
                key,
                confirmation=key,
                acceptance=v.ACCEPT,
                attest_client_returned=True,
                platform_ack=sha(v.PLATFORM),
            )
    assert not (s.directory / "00000010.pending").exists()
    assert not s.store.path("used", approval).exists()


@pytest.mark.parametrize("factory", [recorded, recorded_new, recorded_self_v2])
@pytest.mark.parametrize("change", ["method", "cross-keys", "extra", "missing", "namespace"])
def test_exact_variant_grammar_refuses_cross_substitution(legacy_ten, factory, change):
    s = legacy_ten
    current = deepcopy(factory(s))
    proc = current["scope"]["procfs"]
    if change == "method":
        current["method"] = "unknown"
    if change == "cross-keys":
        current["method"] = NEW if current["method"] == OLD else OLD
    if change == "extra":
        proc["proof_version"] = 1
    if change == "missing":
        del proc["filesystem"]
    if change == "namespace":
        proc["init_pid_namespace" if current["method"] == OLD else "pid_namespace"] = {
            "device": 4,
            "inode": 99,
        }
    with pytest.raises(ValueError):
        v.current(current, s.snapshot, s.process, 12000)


@pytest.mark.parametrize("factory", [recorded_new, recorded_self_v2])
@pytest.mark.parametrize("mount", [True, 1.0, "1", 0, -1, 2**64, 2**63, 2**64 - 1])
def test_mount_id_only_unsigned_grammar_and_serialization(legacy_ten, mount, factory):
    s = legacy_ten
    current = factory(s)
    current["scope"]["procfs"]["mount_id"] = mount
    if type(mount) is int and 1 <= mount < 2**64:
        v.current(current, s.snapshot, s.process, 12000)
        assert json.loads(json.dumps(current))["scope"]["procfs"]["mount_id"] == mount
    else:
        with pytest.raises(ValueError):
            v.current(current, s.snapshot, s.process, 12000)


@pytest.mark.parametrize("method", [OLD, NEW, SELF_V2])
def test_committed_receipt_method_must_equal_validated_plan(legacy_ten, method):
    s = legacy_ten
    _, approval, receipt = golden(s, method=method)
    receipt["proof_method"] = NEW if method == OLD else OLD
    key = s.store.put("receipts", receipt)
    path = s.directory / "00000010.json"
    record = json.loads(path.read_text())
    record["receipt"] = key
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="damaged or incomplete"):
        d.apply(s.store, approval)
