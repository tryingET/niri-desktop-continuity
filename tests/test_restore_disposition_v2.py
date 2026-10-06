"""Handwritten five-record oracle; no planner/executor/geometry predictor produces this data."""

import json

import pytest
from test_restore_disposition_handwritten import handwritten as handwritten

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history

FAMILY = "exec-observed-unassociated"


def make_unassociated(s):
    for seq in range(5, 9):
        (s.directory / f"{seq:08d}.json").unlink()  # ONLY files just fabricated by this fixture.
    old = s.store.get("receipts", s.interrupted)
    original = {
        "status": "interrupted",
        "windows": [
            {
                "entry": old["windows"][0]["entry"],
                "window_id": 1,
                "status": "launch-indeterminate",
                "geometry_coverage": {"width": "requested-pending", "position": "not-recorded"},
                "process_receipt": old["windows"][0]["process_receipt"],
            }
        ],
        "effects": [],
        "final_observation": {"unavailable": True},
        "native_session": "not-proved",
        "error_type": "ValueError",
        "error": "foreign active window",
    }
    prepared = s.store.get(
        "receipts", json.loads((s.directory / "00000000.json").read_text())["receipt"]
    )
    s.source = prepared["snapshot_digest"]
    s.interrupted = s.store.put("receipts", original)
    s.result.write_text(
        json.dumps({"snapshot_digest": s.source, "receipt_digest": s.interrupted, **original})
    )
    return s


@pytest.fixture
def unassociated(handwritten):
    return make_unassociated(handwritten)


def propose(s):
    return d.propose(
        s.store,
        s.identity,
        s.attempt,
        s.interrupted,
        s.result,
        s.exit_file,
        family=FAMILY,
        observer=s.observe,
    )["plan_digest"]


def approve(s, key):
    return d.approve(
        s.store,
        key,
        confirmation=key,
        acceptance="operator-accepted-partial",
        attest_client_returned=True,
        observer=s.observe,
    )["approval_digest"]


def test_given_five_literal_records_when_explicitly_accounted_then_only_partial_release(
    unassociated,
):
    s = unassociated
    originals = {p: p.read_bytes() for p in s.directory.iterdir()}
    with pytest.raises(ValueError):
        d.propose(
            s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file, observer=s.observe
        )
    key = propose(s)
    plan = s.store.get("plans", key)
    assert plan["schema"] == "desktop-continuity.restore-disposition.v2"
    assert plan["segment"]["start"] == 0 and plan["segment"]["count"] == 5
    assert plan["segment"]["previous"] is None
    assert len(plan["manifest"]) == 12
    approved = approve(s, key)
    result = d.apply(s.store, approved, observer=s.observe)
    body = s.store.get("receipts", result["receipt_digest"])
    assert body == {
        "schema": "desktop-continuity.restore-disposition.v2",
        "family": FAMILY,
        "status": "operator-accepted-partial",
        "plan": key,
        "approval": approved,
        "attempt": s.attempt,
        "interrupted_receipt": s.interrupted,
        "process_receipt": s.store.get("receipts", s.interrupted)["windows"][0]["process_receipt"],
        "disposition_effects": [],
        "historical_completion": "unproved",
        "historical_association": "not-recorded",
        "historical_layout": "not-attempted",
        "outcome": "unresolved",
        "native_session": "not-proved",
        "retry_authorized": False,
    }
    assert not result["historical"] and result["effects"] == []
    assert s.store.pointer("last-reopened") is None
    assert {p: p.read_bytes() for p in originals} == originals
    assert sorted(p.name for p in s.directory.iterdir()) == [f"{i:08d}.json" for i in range(6)]
    with operation_lock.operation_lock(s.identity):
        assert history.admit(s.identity)[1] is None
    assert d.apply(s.store, approved, observer=lambda: pytest.fail("no historical native probe"))[
        "historical"
    ]
    assert (
        d.inspect(
            s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY
        )["admission"]
        == "not-granted"
    )
