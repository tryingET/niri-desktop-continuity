"""Actual admission paths remain fenced; no synthetic v2 validator is installed in these tests."""

import os

import pytest
from test_reopen import saved
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_reader import ledger as ledger  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_routing as routing
from niri_desktop_continuity.restore_attempt import Attempt
from niri_desktop_continuity.restore_reader import DependencyReader, Limits
from niri_desktop_continuity.store import Store


def causes(error):
    result = []
    while error is not None:
        result.append(str(error))
        error = error.__cause__
    return " ".join(result)


@pytest.mark.parametrize(
    "acceptor",
    ["load", "admit", "require-clear", "lock", "attempt", "original", "other-store", "disposition"],
)
@pytest.mark.parametrize("tiny", [True, False])
def test_every_admission_path_routes_new_family_into_reader_and_never_grants_authority(
    ledger, tmp_path, monkeypatch, acceptor, tiny
):
    ledger.append()
    ledger.boundary()
    store, identity = ledger.store, ledger.identity
    key = store.put("snapshots", saved([]))
    other = Store(tmp_path / "other")
    assert other.put("snapshots", store.get("snapshots", key)) == key
    plan = store.put("plans", {"identity": identity})
    approval = store.put("approvals", {"plan": plan})
    calls = []

    def reader(**kwargs):
        calls.append(True)
        return DependencyReader(**{**kwargs, "limits": Limits(files=0) if tiny else Limits()})

    monkeypatch.setattr(routing, "DependencyReader", reader)
    monkeypatch.setattr(restore, "compositor_identity", lambda: identity)

    def forbidden(*_):
        pytest.fail("no observation, write or semantic legacy fallback after v2 dispatch")

    monkeypatch.setattr(store, "consume", forbidden)
    monkeypatch.setattr(store, "put", forbidden)
    with pytest.raises(ValueError) as error:
        if acceptor == "lock":
            with operation_lock.operation_lock(identity):
                forbidden()
        elif acceptor == "attempt":
            with Attempt(store, key, identity):
                forbidden()
        elif acceptor in {"original", "other-store"}:
            restore.restore(
                store if acceptor == "original" else other,
                key,
                object(),
                apply=True,
                observe=forbidden,
            )
        elif acceptor == "disposition":
            disposition.apply(store, approval, observer=forbidden)
        else:
            with operation_lock.operation_lock(identity, effectful=False, existing_only=True):
                {
                    "load": history.load,
                    "admit": history.admit,
                    "require-clear": history.require_clear,
                }[acceptor](identity)
    assert calls == [True]
    assert ("budget" if tiny else "overlapping or invalid preparation") in causes(error.value)
    assert len(list(ledger.directory.iterdir())) == 2
    assert not list((store.root / "used").iterdir())


def complete_v1(s):
    key = disposition.propose(
        s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file, observer=s.observe
    )["plan_digest"]
    approved = disposition.approve(
        s.store,
        key,
        confirmation=key,
        acceptance=disposition.ACCEPT,
        attest_client_returned=True,
        observer=s.observe,
    )["approval_digest"]
    result = disposition.apply(s.store, approved, observer=s.observe)
    return key, approved, result


def test_real_v1_completed_history_and_replays_ignore_tiny_new_limits(
    handwritten, monkeypatch, tmp_path
):
    s = handwritten
    before = {p: p.read_bytes() for p in s.directory.iterdir()}
    monkeypatch.setattr(
        routing, "DependencyReader", lambda **_: pytest.fail("v2 cap applied to legacy history")
    )
    _, approved, result = complete_v1(s)
    assert result["status"] == disposition.ACCEPT
    other = Store(tmp_path / "other")
    source = history.load(s.identity)[0][0]["snapshot_digest"]
    other.put("snapshots", s.store.get("snapshots", source))
    monkeypatch.setattr(restore, "compositor_identity", lambda: s.identity)
    for store in (s.store, other):
        replay = restore.restore(
            store,
            source,
            object(),
            apply=True,
            observe=lambda: pytest.fail("native observation on replay"),
        )
        assert replay["status"] == disposition.ACCEPT and replay["effects"] == []
        assert replay["historical"] is True
    assert disposition.apply(s.store, approved, observer=lambda: pytest.fail("no fresh proof"))[
        "historical"
    ]
    assert {p: p.read_bytes() for p in before} == before
    assert len(list(s.directory.iterdir())) == 10


def test_readonly_history_and_inspection_no_fsync_writes_or_native_observation(
    handwritten, monkeypatch
):
    s = handwritten
    opened = os.open

    def readonly(path, flags, *args, **kwargs):
        assert not flags & (os.O_RDWR | os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        return opened(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", readonly)
    monkeypatch.setattr(os, "fsync", lambda *_: pytest.fail("readonly fsync"))
    monkeypatch.setattr(disposition.proof, "observe", lambda: pytest.fail("native observation"))
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        assert history.load(s.identity)[2] == 9
    info = disposition.inspect(s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file)
    assert info["approval"] == "not-granted"
