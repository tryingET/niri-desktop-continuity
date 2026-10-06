"""Given recorded proof, malformed Version must never grant historical authority."""

from copy import deepcopy

import pytest
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_contract import recorded
from test_restore_exited_history import FAMILY
from test_restore_exited_history import legacy_ten as legacy_ten  # noqa: F401
from test_restore_exited_semantics import rewrite

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_exited_values as values
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt

BAD_VERSIONS = [
    pytest.param(None, id="null"),
    pytest.param(False, id="boolean"),
    pytest.param(0, id="number"),
    pytest.param({}, id="object"),
    pytest.param([], id="array"),
    pytest.param("", id="empty"),
    pytest.param("\0", id="nul-string"),
    pytest.param("x" * 4097, id="overlong"),
    pytest.param("fixture-client", id="cli-only-match"),
]


def test_given_no_comparison_when_validating_source_then_return_compositor():
    source = {"niri_version": {"compositor": "fixture-version", "cli": "fixture-client"}}
    original = deepcopy(source)
    assert values.version(source) == "fixture-version"
    assert values.version(source, "fixture-version") == "fixture-version"
    assert source == original


@pytest.mark.parametrize("bad", BAD_VERSIONS)
def test_given_explicit_invalid_version_when_comparing_then_refuse(bad):
    source = {"niri_version": {"compositor": "fixture-version", "cli": "fixture-client"}}
    with pytest.raises(ValueError):
        values.version(source, bad)


@pytest.mark.parametrize("bad", BAD_VERSIONS)
def test_given_invalid_recorded_version_when_decoding_then_refuse(legacy_ten, bad):
    current = recorded(legacy_ten)
    current["peer"]["version"] = bad
    with pytest.raises(ValueError):
        values.current(current, legacy_ten.snapshot, legacy_ten.process, 12000)


@pytest.mark.parametrize("bad", BAD_VERSIONS)
@pytest.mark.parametrize(
    "consumer",
    ["admit", "effectful-lock", "attempt", "direct-replay", "ordinary-replay", "inspect"],
)
def test_given_invalid_recorded_version_when_consuming_then_never_admit(
    accounting, monkeypatch, consumer, bad
):
    s = accounting
    original = disposition.apply(s.store, s.approval)
    # Given valid original evidence and a self-consistent but semantically invalid ending.
    inputs = {
        path: path.read_bytes()
        for path in s.directory.glob("*.json")
        if path.name != "00000010.json"
    }
    for path in (s.result, s.exit_file, s.store.path("snapshots", s.source)):
        inputs[path] = path.read_bytes()

    def change(plan, _receipt):
        plan["current"]["peer"]["version"] = bad

    approval = rewrite(s, original, change)

    def no_native(*_args, **_kwargs):
        pytest.fail("historical refusal must not query the desktop or reopen native proof")

    monkeypatch.setattr(proof, "current", no_native)

    def consume():
        if consumer == "admit":
            with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
                return history.admit(s.identity)
        if consumer == "effectful-lock":
            with operation_lock.operation_lock(s.identity):
                return "effect authority granted"
        if consumer == "attempt":
            with Attempt(s.store, s.source, s.identity) as attempt:
                attempt.check()
                return "attempt admitted"
        if consumer == "direct-replay":
            return disposition.apply(s.store, approval)
        if consumer == "ordinary-replay":
            return restore.restore(s.store, s.source, object(), apply=True, observe=no_native)
        return disposition.inspect(
            s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY
        )

    # When any accepting consumer encounters it, then refuse without effects or evidence repair.
    try:
        with pytest.raises(ValueError):
            consume()
    finally:
        assert {path: path.read_bytes() for path in inputs} == inputs
        assert s.store.pointer("last-reopened") is None
