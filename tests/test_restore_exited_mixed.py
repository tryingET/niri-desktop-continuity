"""Actual v1+v2 sixteen-record prefix, then independent ten-record v3 across Stores."""

import json
from pathlib import Path

import pytest
from restore_v2_fixtures import append, next_attempt
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_disposition_v2 import approve
from test_restore_disposition_v2_adversarial import all_refuse, replace
from test_restore_disposition_v2_chain import finish
from test_restore_exited_contract import prepare
from test_restore_exited_dual_method import NEW, OLD, SELF_V2, golden
from test_restore_exited_history import fabricate

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.store import Store


@pytest.fixture(params=["old", "self-v1", "new"])
def mixed(handwritten, tmp_path, monkeypatch, request):
    a = handwritten
    key = d.propose(
        a.store, a.identity, a.attempt, a.interrupted, a.result, a.exit_file, observer=a.observe
    )["plan_digest"]
    approval = approve(a, key)
    d.apply(a.store, approval, observer=a.observe)
    b = next_attempt(a, tmp_path / "middle-store", 1)
    kb, ab, rb = finish(b)
    assert len(list(a.directory.iterdir())) == 16
    root = tmp_path / "last"
    root.mkdir(mode=0o700)
    s = fabricate(
        root,
        monkeypatch,
        identity=a.identity,
        process={"boot_id": a.identity["boot_id"], "pid": 2200, "start_ticks": 1},
    )
    s.attempt = "e" * 64
    append(a, s.store, s.attempt, s.transcript)
    s.directory = a.directory
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: a.directory.parent.parent)
    if request.param in ("old", "self-v1"):
        s.plan, s.approval, _ = golden(s, method=OLD if request.param == "old" else NEW)
    else:
        s = prepare(s, monkeypatch)
    s.result_value = d.apply(s.store, s.approval)
    s.prior = (a, key, approval, b, kb, ab, rb)
    return s


def test_real_sixteen_plus_ten_prefix_closure_and_cross_store_replay(mixed, tmp_path, monkeypatch):
    s = mixed
    plan = s.store.get("plans", s.plan)
    assert plan["segment"]["start"] == 16 and plan["segment"]["count"] == 10
    assert plan["history_count"] == 26
    assert (
        plan["segment"]["previous"]
        == json.loads((s.directory / "00000016.json").read_text())["previous"]
    )
    paths = {p["path"] for p in plan["manifest"]}
    a, ka, aa, b, kb, ab, rb = s.prior
    for case, pk, ak in ((a, ka, aa), (b, kb, ab)):
        for kind, key in (
            ("plans", pk),
            ("approvals", ak),
            ("used", ak),
            ("snapshots", case.store.get("plans", pk)["snapshot"]),
        ):
            assert str(case.store.path(kind, key)) in paths
    with operation_lock.operation_lock(s.identity):
        completed, active, count, _ = history.admit(s.identity)
    assert count == 27 and active is None and len(completed) == 3
    caller = Store(tmp_path / "other-caller")
    assert caller.put("snapshots", s.snapshot) == s.source
    monkeypatch.setattr(
        restore,
        "compositor_identity",
        lambda: pytest.fail("historical v3 replay needs no native route"),
    )
    result = restore.restore(
        caller,
        s.source,
        object(),
        apply=True,
        observe=lambda: pytest.fail("no current observation"),
    )
    assert result["historical_effects"] == s.actions and result["effects"] == []
    assert result["status"] == "operator-accepted-partial"


def test_v1_v2_v3_ordinary_v3_cumulative_chain(mixed, tmp_path, monkeypatch):
    first = mixed
    seed = first.prior[0]
    ordinary = next_attempt(seed, tmp_path / "ordinary-store", 2, ordinary=True)
    root = tmp_path / "fifth"
    root.mkdir(mode=0o700)
    later = fabricate(
        root,
        monkeypatch,
        identity=first.identity,
        process={"boot_id": first.identity["boot_id"], "pid": 2201, "start_ticks": 2},
        peer={
            "pid": 3000,
            "start_ticks": 2,
            "ppid": 1,
            "comm": "another-niri-name",
            "cgroup": None,
        },
    )
    later.attempt = "f" * 64
    append(seed, later.store, later.attempt, later.transcript)
    later.directory = seed.directory
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: seed.directory.parent.parent)
    prepare(later, monkeypatch)
    result = d.apply(later.store, later.approval)
    assert result["status"] == "operator-accepted-partial"
    plan = later.store.get("plans", later.plan)
    assert plan["segment"]["start"] == 30 and plan["history_count"] == 40
    completed, active, count, _ = history.admit(first.identity)
    assert count == 41 and active is None and len(completed) == 5
    assert completed[3]["snapshot_digest"] == ordinary.source
    terminal = json.loads((seed.directory / "00000029.json").read_text())["receipt"]
    path = ordinary.store.path("receipts", terminal)
    path.write_bytes(path.read_bytes() + b" ")
    all_refuse(later, later.approval, monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        d.inspect(
            later.store,
            None,
            later.attempt,
            later.interrupted,
            later.result,
            later.exit_file,
            family="associated-shell-protected-dimensions-interrupted",
        )


@pytest.mark.parametrize(
    "dependency",
    ["prior-plan", "prior-source", "prior-witness", "prior-used", "process", "current-source"],
)
@pytest.mark.parametrize("mode", ["missing", "whitespace", "inode"])
def test_mixed_closure_corruption_blocks_actual_consumers(
    mixed, tmp_path, monkeypatch, dependency, mode
):
    s = mixed
    a, ka, aa, b, kb, ab, rb = s.prior
    prior_plan = a.store.get("plans", ka)
    paths = {
        "prior-plan": a.store.path("plans", ka),
        "prior-source": a.store.path("snapshots", prior_plan["snapshot"]),
        "prior-witness": Path(prior_plan["witness"]["client_result"]["path"]),
        "prior-used": b.store.path("used", ab),
        "process": s.store.path("receipts", s.receipt["windows"][0]["process_receipt"]),
        "current-source": s.store.path("snapshots", s.source),
    }
    replace(paths[dependency], mode)
    if dependency == "current-source" and mode == "missing":
        for accept in (lambda: history.admit(s.identity), lambda: d.apply(s.store, s.approval)):
            with pytest.raises((ValueError, OSError)):
                accept()
    else:
        all_refuse(s, s.approval, monkeypatch, tmp_path)


def test_all_three_method_testimonies_in_one_immutable_mixed_history(mixed, tmp_path, monkeypatch):
    first = mixed
    seed = first.prior[0]
    present = first.store.get("plans", first.plan)["current"]["method"]
    original = {p: p.read_bytes() for p in first.directory.iterdir()}
    approvals = [(first.store, first.approval)]
    for index, method in enumerate(m for m in (OLD, NEW, SELF_V2) if m != present):
        root = tmp_path / f"historical-{index}"
        root.mkdir(mode=0o700)
        later = fabricate(
            root,
            monkeypatch,
            identity=first.identity,
            process={"boot_id": first.identity["boot_id"], "pid": 2300 + index, "start_ticks": 2},
            peer={
                "pid": 3000,
                "start_ticks": 2,
                "ppid": 1,
                "comm": f"fixture-{index}",
                "cgroup": None,
            },
        )
        later.attempt = str(index + 6) * 64
        append(seed, later.store, later.attempt, later.transcript)
        later.directory = seed.directory
        monkeypatch.setattr(operation_lock, "runtime_root", lambda: seed.directory.parent.parent)
        _, approved, _ = golden(later, method=method, expired=True)
        approvals.append((later.store, approved))
    completed, active, count, _ = history.admit(first.identity)
    assert active is None and count == 49
    assert {row["result"].get("proof_method") for row in completed[2:]} == {OLD, NEW, SELF_V2}
    for store, approval in approvals:
        assert d.apply(store, approval)["historical"]
    assert {p: p.read_bytes() for p in original} == original
