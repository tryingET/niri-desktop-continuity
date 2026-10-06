"""Independent closed-value, witness and lifecycle veto tests; no native observer stub in CLI."""

import json
import os
from contextlib import contextmanager
from copy import deepcopy

import pytest
from test_restore_exited_history import FAMILY, scene, sha
from test_restore_exited_history import legacy_ten as legacy_ten

from niri_desktop_continuity import launch, operation_lock, probe
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_exited_values as values
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_reader import DependencyReader
from niri_desktop_continuity.restore_retained import json_bytes


@pytest.mark.parametrize("field", ["object", "member"])
def test_duplicate_version_keys_refuse_before_native_proof(legacy_ten, monkeypatch, field):
    s = legacy_ten
    path = s.store.path("snapshots", s.source)
    raw = path.read_text()
    if field == "object":
        raw = raw.replace(
            '"niri_version": {',
            '"niri_version": {"compositor":"fixture-version","cli":"fixture-client"}, "niri_version": {',
            1,
        )
    else:
        raw = raw.replace(
            '"compositor": "fixture-version"',
            '"compositor": "fixture-version", "compositor": "fixture-version"',
            1,
        )
    path.write_text(raw)
    monkeypatch.setattr(
        proof, "current", lambda *_a, **_kw: pytest.fail("malformed source reached native proof")
    )
    with pytest.raises(ValueError):
        d.propose(s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY)
    assert not list((s.store.root / "plans").iterdir())


def recorded(s):
    state = scene(0)
    caller = {"boot_id": "fabricated-boot", "pid": 9000, "start_ticks": 3}
    ns = {"device": 4, "inode": 5}
    return {
        "method": "native-niri-continuing-peer-pidfd-esrch.v1",
        "state": state,
        "owned_window_ids": [],
        "protected_window_ids": [70, 80],
        "processes": [
            {"boot_id": "fabricated-boot", "pid": p, "start_ticks": 2} for p in (1000070, 1000080)
        ],
        "peer": {
            "process": {"boot_id": "fabricated-boot", "pid": 3000, "start_ticks": 2},
            "credentials": {"pid": 3000, "uid": os.getuid(), "gid": os.getgid()},
            "endpoint": {
                "path": "/fabricated/niri.sock",
                "directory": {"device": 1, "inode": 2},
                "device": 11,
                "inode": 22,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "mode": 0o600,
            },
            "inventory": {"snapshot": s.source, "row_digest": sha(s.peer)},
            "version": "fixture-version",
            "running_image": {"device": 2, "inode": 3, "sha256": "e" * 64},
        },
        "scope": {
            "pid_namespace": ns,
            "user_namespace": {"device": 4, "inode": 6},
            "procfs": {"device": 7, "inode": 8, "filesystem": "proc", "init_pid_namespace": ns},
        },
        "absence": {
            "process": s.process,
            "primitive": "linux-pidfd-open",
            "flags": 0,
            "errno": "ESRCH",
        },
        "caller": {"process": caller, "ancestry": [{"process": caller, "ppid": 1}]},
    }


def recorded_new(s):
    # Immutable self-v1 historical golden; recorded() above remains the legacy wire oracle.
    current = recorded(s)
    current["method"] = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v1"
    current["scope"]["procfs"] = {
        "device": 7,
        "inode": 8,
        "filesystem": "proc",
        "mount_id": 2**63,
        "pid_namespace": {"device": 4, "inode": 5},
    }
    return current


def recorded_self_v2(s):
    # Independent method/procfs expectation; never relabel the self-v1 oracle above.
    current = recorded(s)
    current["method"] = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v2"
    current["scope"]["procfs"] = {
        "device": 7,
        "inode": 8,
        "filesystem": "proc",
        "mount_id": 2**63,
        "pid_namespace": {"device": 4, "inode": 5},
    }
    return current


@pytest.fixture
def accounting(legacy_ten, monkeypatch):
    return prepare(legacy_ten, monkeypatch)


def prepare(s, monkeypatch):
    s.veto = lambda: None
    s.stage = 0

    @contextmanager
    def measured(source, launched, associated, *, expires, expected=None):
        # Explicit semantic lifecycle double, not a kernel-proof test or production factory.
        assert source == s.snapshot and launched == s.process and associated == 12000
        s.stage += 1
        current = recorded_self_v2(s)
        current["caller"]["process"]["pid"] += s.stage
        current["caller"]["ancestry"][0]["process"] = current["caller"]["process"]
        if expected is not None:
            assert proof.stable(current) == proof.stable(expected)
        yield current, lambda: s.veto()

    monkeypatch.setattr(proof, "current", measured)
    s.proposed = d.propose(
        s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY
    )
    s.plan = s.proposed["plan_digest"]
    s.approval = d.approve(
        s.store,
        s.plan,
        confirmation=s.plan,
        acceptance="operator-accepted-partial",
        attest_client_returned=True,
        platform_ack=s.proposed["platform_digest"],
    )["approval_digest"]
    return s


def test_handwritten_receipt_projection_and_distinct_callers(accounting):
    s = accounting
    result = d.apply(s.store, s.approval)
    receipt = s.store.get("receipts", result["receipt_digest"])
    assert set(receipt) == set(
        "schema family branch status plan approval attempt interrupted_receipt process_receipt proof_method current_digest platform_ack caller disposition_effects historical_completion historical_preservation historical_association historical_layout outcome native_session retry_authorized".split()
    )
    assert receipt["historical_association"] == "recorded"
    assert receipt["historical_layout"] == "two-observed-actions-incomplete"
    assert receipt["historical_preservation"] == receipt["historical_completion"] == "unproved"
    assert receipt["outcome"] == "unresolved" and receipt["retry_authorized"] is False
    assert receipt["caller"]["process"]["pid"] == 9003
    assert result["historical_effects"] == s.actions and result["effects"] == []
    assert d.apply(s.store, s.approval)["historical"] is True
    with operation_lock.operation_lock(s.identity):
        assert history.admit(s.identity)[2] == 11


def test_expired_completed_approval_is_historical_without_native(accounting, monkeypatch):
    import time

    s = accounting
    result = d.apply(s.store, s.approval)
    plan = s.store.get("plans", s.plan)
    monkeypatch.setattr(time, "time", lambda: plan["expires"] + 1000)
    monkeypatch.setattr(
        proof, "current", lambda *_a, **_kw: pytest.fail("historical expiry replay opened proof")
    )
    replay = d.apply(s.store, s.approval)
    assert replay["historical"] and replay["receipt_digest"] == result["receipt_digest"]
    assert replay["effects"] == [] and replay["historical_effects"] == s.actions


def test_direct_foreign_store_replay_refuses_before_native(accounting, tmp_path, monkeypatch):
    from niri_desktop_continuity.store import Store

    s = accounting
    d.apply(s.store, s.approval)
    other = Store(tmp_path / "foreign")
    assert other.put("plans", s.store.get("plans", s.plan)) == s.plan
    assert other.put("approvals", s.store.get("approvals", s.approval)) == s.approval
    monkeypatch.setattr(
        proof, "current", lambda *_a, **_kw: pytest.fail("foreign replay opened proof")
    )
    with pytest.raises(ValueError, match="original Store"):
        d.apply(other, s.approval)


@pytest.mark.parametrize("phase", ["last-capacity", "prepublish"])
def test_given_slow_last_io_when_live_veto_then_stage_remains_fenced(
    accounting, monkeypatch, phase
):
    s = accounting
    reserve = DependencyReader.reserve_commit
    armed = False

    def capacity(reader, artifacts, **kwargs):
        nonlocal armed
        result = reserve(reader, artifacts, **kwargs)
        if any(p.suffix == ".pending" and p.exists() for p, _ in artifacts):
            armed = True
        return result

    def veto():
        consumed = s.store.path("used", s.approval).exists()
        if armed and (phase == "last-capacity" or consumed):
            raise ValueError("fabricated late current drift")

    monkeypatch.setattr(DependencyReader, "reserve_commit", capacity)
    s.veto = veto
    with pytest.raises(ValueError, match="late current"):
        d.apply(s.store, s.approval)
    assert (s.directory / "00000010.pending").exists()
    assert not (s.directory / "00000010.json").exists()
    assert s.store.path("used", s.approval).exists() == (phase == "prepublish")
    with pytest.raises(ValueError):
        with operation_lock.operation_lock(s.identity):
            pytest.fail("stage must fence every writer")
    with pytest.raises(ValueError):
        d.apply(s.store, s.approval)


@pytest.mark.parametrize(
    "extra",
    [
        {
            "first_rejected_observation": {
                "schema": "restore-protected-dimensions.v1",
                "unavailable": True,
            }
        },
        {"unknown": None},
    ],
)
def test_diagnostic_bearing_original_is_never_legacy(legacy_ten, extra):
    s = legacy_ten
    receipt = {**s.receipt, **extra}
    key = s.store.put("receipts", receipt)
    s.result.write_text(json.dumps({"snapshot_digest": s.source, "receipt_digest": key, **receipt}))
    with pytest.raises(ValueError):
        d.inspect(s.store, None, s.attempt, key, s.result, s.exit_file, family=FAMILY)


@pytest.mark.parametrize("member", ["compositor", "cli"])
@pytest.mark.parametrize("bad", [None, True, False, 1, [], {}, "", "\0", "x" * 4097])
def test_invalid_version_members_are_not_coerced(member, bad):
    value = {"compositor": "fixture-version", "cli": "different-client"}
    value[member] = bad
    with pytest.raises(ValueError):
        values.version({"niri_version": value}, "fixture-version")


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "fixture-version",
        True,
        False,
        1,
        [],
        {},
        {"compositor": "fixture-version"},
        {"cli": "fixture-version"},
        {"compositor": "fixture-version", "cli": "x", "extra": None},
    ],
)
def test_invalid_version_object_is_not_compatibility_alias(bad):
    with pytest.raises(ValueError):
        values.version({"niri_version": bad}, "fixture-version")


@pytest.mark.parametrize("version", ["x", "x" * 4096, "build override / café", " fixture-version "])
def test_exact_version_match_with_independent_cli_provenance(version):
    assert (
        values.version({"niri_version": {"cli": "other", "compositor": version}}, version)
        == version
    )
    assert (
        values.version({"niri_version": {"cli": version, "compositor": version}}, version)
        == version
    )


@pytest.mark.parametrize(
    "wrong", ["Fixture-version", "fixture-version ", "fixture-versioń", "other"]
)
def test_cli_match_cannot_rescue_compositor_mismatch(wrong):
    with pytest.raises(ValueError):
        values.version(
            {"niri_version": {"compositor": wrong, "cli": "fixture-version"}}, "fixture-version"
        )


@pytest.mark.parametrize(
    "raw", [b'{"niri_version":{},"niri_version":{}}', b'{"compositor":"x","cli":"x","cli":"x"}']
)
def test_duplicate_raw_source_keys_refuse(raw):
    with pytest.raises(ValueError):
        json_bytes(raw)


def test_actual_capture_keeps_both_cli_members_then_v3_projects_compositor(monkeypatch):
    identity = {
        "boot_id": "fixture",
        "niri_socket": "/fixture/socket",
        "socket_device": 1,
        "socket_inode": 2,
    }
    monkeypatch.setattr(probe, "compositor_identity", lambda: identity)
    monkeypatch.setattr(probe, "window_processes", lambda _: ([], []))
    monkeypatch.setattr(probe, "process_inventory", lambda: ([], True))
    monkeypatch.setattr(launch, "window_recipes", lambda *_: {})
    replies = {
        "version": '{"compositor":"fixture-version","cli":"fixture-client-version"}',
        "outputs": "{}",
        "windows": "[]",
        "workspaces": "[]",
        "layers": "[]",
    }

    def query(argv, **kwargs):
        from types import SimpleNamespace

        assert argv[:3] == ["niri", "msg", "--json"]
        return SimpleNamespace(stdout=replies[argv[3]])

    monkeypatch.setattr(probe.subprocess, "run", query)
    source = probe.capture()
    original = deepcopy(source)
    assert source["niri_version"] == {
        "compositor": "fixture-version",
        "cli": "fixture-client-version",
    }
    assert values.version(source, "fixture-version") == "fixture-version"
    assert source == original


def test_platform_ack_missing_or_wrong_refuses_before_native(accounting, monkeypatch):
    s = accounting
    monkeypatch.setattr(
        proof, "current", lambda *_a, **_k: pytest.fail("no native proof without acknowledgement")
    )
    for ack in (None, "a" * 64):
        with pytest.raises(ValueError):
            d.approve(
                s.store,
                s.plan,
                confirmation=s.plan,
                acceptance="operator-accepted-partial",
                attest_client_returned=True,
                platform_ack=ack,
            )
