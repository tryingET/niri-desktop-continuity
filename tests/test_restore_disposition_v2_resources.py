"""Actual semantic closures and prospective boundaries, not a accepting routing stub."""

import json

import pytest
from restore_v2_fixtures import next_attempt
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_disposition_v2 import approve, propose
from test_restore_disposition_v2 import unassociated as unassociated
from test_restore_disposition_v2_chain import finish

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_reader as readers
from niri_desktop_continuity import restore_reader_io as bounded
from niri_desktop_continuity.restore_reader import Limits


def test_fixed_v2_prefix_cap_does_not_retroactively_budget_ordinary_suffix(
    unassociated, tmp_path, monkeypatch
):
    s = unassociated
    _, approval, _ = finish(s)
    next_attempt(s, tmp_path / "ordinary", 1, ordinary=True)
    monkeypatch.setattr(readers, "Limits", lambda: Limits(files=20))
    with operation_lock.operation_lock(s.identity):
        assert history.admit(s.identity)[2] == 9
    assert d.apply(s.store, approval, observer=lambda: pytest.fail("no new proof"))["historical"]


def test_second_boundary_is_fresh_cumulative_and_refuses_before_suffix_payload_decode(
    unassociated, tmp_path, monkeypatch
):
    s = unassociated
    finish(s)
    ordinary = next_attempt(s, tmp_path / "ordinary", 1, ordinary=True)
    following = next_attempt(s, tmp_path / "following", 2)
    finish(following)
    suffix_payloads = set()
    for seq in range(6, 15):
        record = json.loads((s.directory / f"{seq:08d}.json").read_text())
        suffix_payloads.add(
            str(
                (ordinary.store if seq < 9 else following.store).path("receipts", record["receipt"])
            )
        )
    calls, raw = [], bounded.raw

    def trace(path, *args):
        calls.append(str(path))
        return raw(path, *args)

    monkeypatch.setattr(bounded, "raw", trace)
    monkeypatch.setattr(readers, "Limits", lambda: Limits(files=20))
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        with pytest.raises(ValueError):
            history.admit(s.identity)
    assert not suffix_payloads.intersection(calls)
    # Exactly sufficient cumulative footprint: includes same-byte exit files at BOTH paths.
    monkeypatch.setattr(readers, "Limits", lambda: Limits(files=47))
    with operation_lock.operation_lock(s.identity):
        completed = history.admit(s.identity)[0]
    assert len(completed[-1]["_evidence"]) == 47
    exits = [
        p
        for p in completed[-1]["_evidence"]
        if p["path"] in {str(s.exit_file), str(following.exit_file)}
    ]
    assert len(exits) == 2 and exits[0]["sha256"] == exits[1]["sha256"]


@pytest.mark.parametrize("limit", [19, 20])
def test_complete_prospective_count_last_before_consume(unassociated, monkeypatch, limit):
    s = unassociated
    key, approval = propose(s), None
    approval = approve(s, key)
    monkeypatch.setattr(readers, "Limits", lambda: Limits(files=limit))
    if limit == 19:
        with pytest.raises(ValueError, match="budget"):
            d.apply(s.store, approval, observer=s.observe)
        assert not list((s.store.root / "used").iterdir())
        assert len(list(s.directory.iterdir())) == 5
    else:
        assert (
            d.apply(s.store, approval, observer=s.observe)["status"] == "operator-accepted-partial"
        )


def test_explicit_seed_conflicts_retire_before_dedup_or_read(unassociated):
    s = unassociated
    reader = readers.DependencyReader()
    _, pin = reader.evidence(s.result)
    changed = {**pin, "inode": pin["inode"] + 1}
    with pytest.raises(ValueError):
        reader.expect([changed])
    assert reader.closed and not reader.cache and not reader.parsed
    with pytest.raises(ValueError):
        reader.expect([pin])


def test_v1_cli_artifact_route_does_not_inherit_new_closure_limits(handwritten, monkeypatch):
    s = handwritten
    monkeypatch.setattr(readers, "Limits", lambda: Limits(files=0, raw_bytes=0))
    key = d.propose(
        s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file, observer=s.observe
    )["plan_digest"]
    approved = approve(s, key)
    assert d.apply(s.store, approved, observer=s.observe)["status"] == "operator-accepted-partial"


@pytest.mark.parametrize("delta", [-1, 0])
def test_complete_prospective_raw_bytes_handwritten_boundary(unassociated, monkeypatch, delta):
    s = unassociated
    key = propose(s)
    approval = approve(s, key)
    paths = {
        s.result,
        s.exit_file,
        s.store.path("receipts", s.interrupted),
        s.store.path("snapshots", s.source),
        s.store.path("plans", key),
        s.store.path("approvals", approval),
    }
    records = []
    for seq in range(5):
        path = s.directory / f"{seq:08d}.json"
        record = json.loads(path.read_text())
        records.append(record)
        paths.update({path, s.store.path("receipts", record["receipt"])})
    process_key = s.store.get("receipts", s.interrupted)["windows"][0]["process_receipt"]
    paths.add(s.store.path("receipts", process_key))
    assert len(paths) == 17
    receipt = {
        "schema": "desktop-continuity.restore-disposition.v2",
        "family": "exec-observed-unassociated",
        "status": "operator-accepted-partial",
        "plan": key,
        "approval": approval,
        "attempt": s.attempt,
        "interrupted_receipt": s.interrupted,
        "process_receipt": process_key,
        "disposition_effects": [],
        "historical_completion": "unproved",
        "historical_association": "not-recorded",
        "historical_layout": "not-attempted",
        "outcome": "unresolved",
        "native_session": "not-proved",
        "retry_authorized": False,
    }
    from test_restore_disposition_handwritten import sha

    used = {
        "schema": "desktop-continuity.restore-disposition.v2",
        "family": "exec-observed-unassociated",
        "intent": "restore-disposition",
        "approval": approval,
        "plan": key,
    }
    ending = {
        "schema": "desktop-continuity.restore-history.v3",
        "seq": 5,
        "previous": sha(records[-1]),
        "type": "operator-disposition",
        "attempt": s.attempt,
        "receipt": sha(receipt),
        "origin": records[-1]["origin"],
    }
    future = [
        (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
        (json.dumps(used) + "\n").encode(),
        (json.dumps(ending, sort_keys=True) + "\n").encode(),
    ]
    required = sum(p.stat().st_size for p in paths) + sum(map(len, future))
    monkeypatch.setattr(readers, "Limits", lambda: Limits(raw_bytes=required + delta))
    if delta:
        with pytest.raises(ValueError, match="budget"):
            d.apply(s.store, approval, observer=s.observe)
        assert not list((s.store.root / "used").iterdir())
        assert len(list(s.directory.iterdir())) == 5
    else:
        assert d.apply(s.store, approval, observer=s.observe)["effects"] == []


def test_inspection_stops_at_invalid_v2_before_routing_later_envelopes(
    unassociated, tmp_path, monkeypatch
):
    from niri_desktop_continuity import restore_retained as retained

    s = unassociated
    key, _, _ = finish(s)
    next_attempt(s, tmp_path / "ordinary", 1, ordinary=True)
    s.store.path("plans", key).write_text("{}")
    raw, calls = retained.raw, []

    def trace(path):
        calls.append(str(path))
        return raw(path)

    monkeypatch.setattr(retained, "raw", trace)
    with pytest.raises(ValueError):
        d.inspect(
            s.store,
            s.identity,
            s.attempt,
            s.interrupted,
            s.result,
            s.exit_file,
            family="exec-observed-unassociated",
        )
    assert str(s.directory / "00000006.json") not in calls
