"""Handwritten mixed-version, mixed-Store history: complete closure, not synthetic hook success."""

import json
from pathlib import Path

import pytest
from restore_v2_fixtures import next_attempt
from test_restore_disposition_handwritten import handwritten as handwritten
from test_restore_disposition_v2 import approve, propose
from test_restore_disposition_v2 import unassociated as unassociated

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.store import Store


def finish(s):
    key = propose(s)
    approval = approve(s, key)
    return key, approval, d.apply(s.store, approval, observer=s.observe)


def test_old_absolute_nine_then_new_five_ordinary_terminal_then_two_v2_across_stores(
    handwritten, tmp_path, monkeypatch
):
    a = handwritten
    key = d.propose(
        a.store, a.identity, a.attempt, a.interrupted, a.result, a.exit_file, observer=a.observe
    )["plan_digest"]
    approval = approve(a, key)
    d.apply(a.store, approval, observer=a.observe)
    assert len(list(a.directory.iterdir())) == 10
    b = next_attempt(a, tmp_path / "store-b", 1)
    kb, ab, rb = finish(b)
    assert b.store.get("plans", kb)["segment"]["start"] == 10
    c = next_attempt(a, tmp_path / "store-c", 2, ordinary=True)
    with operation_lock.operation_lock(a.identity):
        assert history.admit(a.identity)[2] == 19
    # The following baselines explicitly reflect later current topology, not a historical
    # preservation claim. Snapshot/attempt/launch identities are independently distinct.
    dcase = next_attempt(a, tmp_path / "store-d", 3)
    kd, ad, rd = finish(dcase)
    e = next_attempt(a, tmp_path / "store-e", 4)
    ke, ae, re = finish(e)
    assert e.store.get("plans", ke)["segment"]["start"] == 25
    assert dcase.store.get("plans", kd)["segment"]["start"] == 19
    manifest = e.store.get("plans", ke)["manifest"]
    paths = {p["path"] for p in manifest}
    for case, pk, ak, result in ((a, key, approval, None), (b, kb, ab, rb), (dcase, kd, ad, rd)):
        for kind, ref in (("plans", pk), ("approvals", ak), ("used", ak)):
            assert str(case.store.path(kind, ref)) in paths
        if result:
            assert str(case.store.path("receipts", result["receipt_digest"])) in paths
    for seq in (9, 15, 18, 24):
        p = a.directory / f"{seq:08d}.json"
        assert str(p) in paths
        record = json.loads(p.read_text())
        assert (
            str(Path(record["origin"]["root"]) / "receipts" / (record["receipt"] + ".json"))
            in paths
        )
    with operation_lock.operation_lock(a.identity):
        completed, active, count, _ = history.admit(a.identity)
    assert count == 31 and active is None and len(completed) == 5
    for case, ak in ((b, ab), (dcase, ad), (e, ae)):
        assert d.apply(case.store, ak, observer=lambda: pytest.fail("no historical observation"))[
            "historical"
        ]
    monkeypatch.setattr(restore, "compositor_identity", lambda: a.identity)
    caller = Store(tmp_path / "other-caller")
    assert caller.put("snapshots", b.store.get("snapshots", b.source)) == b.source
    result = restore.restore(
        caller,
        b.source,
        object(),
        apply=True,
        observe=lambda: pytest.fail("no historical native retry"),
    )
    assert result["historical"] and result["effects"] == []
    assert result["historical_association"] == "not-recorded"
    assert c.store.pointer("last-reopened") is None and re["historical_layout"] == "not-attempted"


@pytest.mark.parametrize("reuse", ["source", "attempt", "process"])
def test_prior_identity_reuse_rejected_before_current_native_proof(unassociated, tmp_path, reuse):
    s = unassociated
    finish(s)
    kwargs = {}
    if reuse == "source":
        kwargs["snapshot"] = s.store.get("snapshots", s.source)
    elif reuse == "attempt":
        kwargs["attempt"] = s.attempt
    else:
        kwargs["pid"] = 2000
    following = next_attempt(s, tmp_path / "following", 1, **kwargs)
    following.observe = lambda: pytest.fail("reuse must refuse before native observation")
    with pytest.raises(ValueError, match="exact fresh five-record"):
        propose(following)
