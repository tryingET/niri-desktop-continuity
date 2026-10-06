"""Actual disposition compositions with real reader/cache teardown; fabricated state only."""

import os
from types import SimpleNamespace

import pytest
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_disposition_v2 import unassociated as unassociated  # noqa: F401
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_history import legacy_ten as legacy_ten  # noqa: F401

from niri_desktop_continuity import cli
from niri_desktop_continuity import restore_disposition_cli as routing
from niri_desktop_continuity import restore_disposition_v2 as v2
from niri_desktop_continuity import restore_exited as v3
from niri_desktop_continuity.restore_disposition_failure import failure_objects, invocation
from niri_desktop_continuity.restore_reader import DependencyReader


@pytest.mark.parametrize(
    "version,stage",
    [(v, s) for v in (2, 3) for s in ("inspect", "propose", "apply", "prepared", "publish")],
)
def test_actual_lifecycle_retains_primary_prior_and_both_caches(
    request, monkeypatch, version, stage
):
    module = v3 if version == 3 else v2
    s = request.getfixturevalue("accounting" if version == 3 else "unassociated")
    if version == 2:
        from test_restore_disposition_v2 import approve, propose

        s.plan = propose(s)
        s.approval = approve(s, s.plan)
    primary, prior = KeyboardInterrupt("PRIVATE-primary"), RuntimeError("PRIVATE-prior")
    primary.__cause__ = prior
    errors, events, readers = [], [], []
    real_close = DependencyReader.close
    real_fd_close = os.close

    def fd_close(fd):
        real_fd_close(fd)  # Actual lock descriptor release, then a fabricated release fault.
        events.append(("real-fd-close", fd))
        error = OSError("PRIVATE-lock-close")
        errors.append(error)
        raise error

    class Cache(dict):
        def __init__(self, value, error, label):
            super().__init__(value)
            self.error, self.label = error, label

        def clear(self):
            events.append(self.label)
            super().clear()
            raise self.error

    def close(reader):
        if not reader.closed:
            # Keep all normal reads intact; inject only actual owned cache release.
            for name in ("cache", "parsed"):
                error = OSError("PRIVATE-" + name)
                errors.append(error)
                setattr(reader, name, Cache(getattr(reader, name), error, (id(reader), name)))
            readers.append(reader)
        return real_close(reader)

    def fail(*args, **kwargs):
        events.append("reached-primary")
        # Arm teardown only after this exact semantic boundary is reached. Normal routing
        # and barrier retirement before the primary remain unchanged.
        monkeypatch.setattr(DependencyReader, "close", close)
        monkeypatch.setattr(os, "close", fd_close)
        raise primary

    if stage in ("inspect", "propose"):
        monkeypatch.setattr(v3.historical if version == 3 else v2.model, "binding", fail)

        def action():
            return (
                module.inspect(s.store, s.attempt, s.interrupted, s.result, s.exit_file)
                if version == 3
                else module.inspect(
                    s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file
                )
            )

        if stage == "propose":

            def action():
                return (
                    module.propose(s.store, s.attempt, s.interrupted, s.result, s.exit_file)
                    if version == 3
                    else module.propose(
                        s.store,
                        s.identity,
                        s.attempt,
                        s.interrupted,
                        s.result,
                        s.exit_file,
                        observer=s.observe,
                    )
                )
    elif stage == "prepared":

        def action():
            with module.operation_lock(
                s.identity,
                effectful=False,
                existing_only=True,
                _preserve_disposition_failures=True,
            ):
                with module.prepared(s.store, s.plan):
                    fail()
    elif stage == "apply":
        # Candidate-ending validation: actual input reader, before native proof.
        monkeypatch.setattr(module.model, "approval_valid", fail)

        def action():
            return (
                module.apply(s.store, s.approval)
                if version == 3
                else module.apply(s.store, s.approval, observer=s.observe)
            )
    else:
        # Actual publication after real stage creation and fresh readers, no native proof.
        real_fresh = module.io.fresh_chain

        def fresh(*args, **kwargs):
            result = real_fresh(*args, **kwargs)
            monkeypatch.setattr(module, "stage_valid", fail)
            return result

        monkeypatch.setattr(module.io, "fresh_chain", fresh)

        def action():
            return (
                module.apply(s.store, s.approval)
                if version == 3
                else module.apply(s.store, s.approval, observer=s.observe)
            )

    with invocation() as tracker:
        with pytest.raises(BaseException) as caught:
            action()
        assert "reached-primary" in events
        assert caught.value is primary
        retained = list(failure_objects(caught.value))
        assert prior in retained and all(error in retained for error in errors)
        assert errors and tracker.failure is primary and tracker.cleanup_failure
        assert all(reader.closed for reader in readers)
        assert len(events) == len(set(events))
        assert events[-1][0] == "real-fd-close"  # Flock released LAST, exactly once.
        assert sum(isinstance(e, tuple) and e[0] == "real-fd-close" for e in events) == 1
        if stage == "prepared":
            assert len(readers) == 2  # Initial and authoritative reader BOTH attempted.


@pytest.mark.parametrize("socket", [None, ""])
@pytest.mark.parametrize("stage", ["inspect", "propose"])
def test_missing_socket_exact_refusal_no_lookup_or_effects(
    tmp_path, monkeypatch, capsys, socket, stage
):
    from niri_desktop_continuity.store import Store

    store = Store(tmp_path / "private")
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    if socket is None:
        monkeypatch.delenv("NIRI_SOCKET", raising=False)
    else:
        monkeypatch.setenv("NIRI_SOCKET", socket)
    reached = []

    def forbidden(*args, **kwargs):
        reached.append("unexpected-lookup-or-effect")
        pytest.fail("missing socket must refuse before native identity or disposition")

    monkeypatch.setattr(routing, "compositor_identity", forbidden)
    monkeypatch.setattr(routing.disposition, stage, forbidden)
    args = [
        "--state-root",
        str(store.root),
        "restore-disposition",
        stage,
        "PRIVATE-sentinel",
        "--interrupted-receipt",
        "f" * 64,
        "--client-result",
        str(tmp_path / "PRIVATE-result"),
        "--client-exit",
        str(tmp_path / "PRIVATE-exit"),
    ]
    assert cli.main(args) == 2
    out = capsys.readouterr()
    assert not out.out and "PRIVATE" not in out.err
    import json

    assert json.loads(out.err)["diagnostic"]["reason"] == "ineligible-evidence"
    assert not reached
    assert {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()} == before
    # Private exact exception assertion, never part of public diagnostic output.
    with pytest.raises(ValueError) as caught:
        routing._run(SimpleNamespace(disposition_stage=stage, family=None), store)
    assert type(caught.value) is ValueError and str(caught.value) == "NIRI_SOCKET unavailable"
