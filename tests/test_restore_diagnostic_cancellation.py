"""Given/When/Then cancellation oracles; only fabricated IPC/process proofs."""

import pytest
from test_restore_failure_observation import no_native_effects as no_native_effects  # noqa: F401
from test_restore_failure_observation import setup
from test_restore_integration import integrated as integrated  # noqa: F401
from test_restore_integration import stall_host_clock_after_association

from niri_desktop_continuity import restore_failure_observation as diagnostic
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt

FAULTS = [KeyboardInterrupt, SystemExit, MemoryError, OSError, ValueError]


def outcome(s, entry, error):
    try:
        _, result = s.run([entry])
    except BaseException as caught:
        assert caught is error
        assert not isinstance(error, Exception)  # ordinary executor errors become receipts
    else:
        assert isinstance(error, Exception)
        assert result["status"] == "interrupted"
        assert result["error_type"] == type(error).__name__
        assert result["error"] == str(error)
        assert result["effects"] == []
        assert "first_rejected_observation" not in result
    assert not s.desktop.actions
    assert s.store.pointer("last-reopened") is None
    assert all(proof.invalid for proof in s.proofs)
    with pytest.raises(ValueError, match="unresolved"):
        history.require_clear(s.identity)


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize("phase", ["constructor", "after-layout-intent"])
@pytest.mark.parametrize("edge", ["before-query", "after-successful-query"])
def test_given_normal_query_when_clock_fails_then_no_later_dispatch(
    integrated, monkeypatch, fault, phase, edge
):
    s = integrated
    entry = setup(s)
    stalled = stall_host_clock_after_association(monkeypatch)
    error = fault("fabricated timing cancellation")
    intent, real_clock, windows = Attempt.intent, diagnostic.time.monotonic_ns, s.desktop.windows
    armed = phase == "constructor"
    ticks, injections, callback_reads = [], [], []

    def arm(attempt, action, details):
        nonlocal armed
        result = intent(attempt, action, details)
        if action == "layout" and not injections:
            armed = True  # intent is already durable, but no dispatch has occurred
        return result

    def read(*args, **kwargs):
        if ticks:
            callback_reads.append(True)
        return windows(*args, **kwargs)

    def clock():
        if armed and not injections:
            ticks.append(True)
            if len(ticks) == (1 if edge == "before-query" else 2):
                injections.append((len(s.proofs), len(callback_reads)))
                raise error
        return real_clock()

    monkeypatch.setattr(Attempt, "intent", arm)
    monkeypatch.setattr(s.desktop, "windows", read)
    monkeypatch.setattr(diagnostic.time, "monotonic_ns", clock)
    outcome(s, entry, error)
    assert stalled == ([] if phase == "constructor" else ["association"])
    assert injections == [(0 if phase == "constructor" else 1, 0 if edge == "before-query" else 1)]
    assert len(s.proofs) == injections[0][0]  # no additional host launch after the fault


@pytest.mark.parametrize("clock_fault", FAULTS)
@pytest.mark.parametrize("callback_fault", FAULTS)
def test_given_query_exception_when_end_clock_also_fails_then_original_unwinds(
    integrated, monkeypatch, clock_fault, callback_fault
):
    s = integrated
    entry = setup(s)
    original = callback_fault("fabricated original query failure")
    secondary = clock_fault("fabricated secondary clock failure")
    intent, windows, real_clock = Attempt.intent, s.desktop.windows, diagnostic.time.monotonic_ns
    armed = False
    callback_failures, clock_failures = [], []

    def arm(attempt, action, details):
        nonlocal armed
        result = intent(attempt, action, details)
        if action == "layout":
            armed = True
        return result

    def read(*args, **kwargs):
        if armed and not callback_failures:
            callback_failures.append(True)
            raise original
        return windows(*args, **kwargs)

    def clock():
        if callback_failures and not clock_failures:
            clock_failures.append(True)
            raise secondary
        return real_clock()

    monkeypatch.setattr(Attempt, "intent", arm)
    monkeypatch.setattr(s.desktop, "windows", read)
    monkeypatch.setattr(diagnostic.time, "monotonic_ns", clock)
    outcome(s, entry, original)
    assert callback_failures == clock_failures == [True]
    assert len(s.proofs) == 1


@pytest.mark.parametrize("fault", FAULTS)
def test_given_callback_failure_when_end_clock_fails_then_exception_identity(monkeypatch, fault):
    evidence = diagnostic.FailureObservation()
    original = OSError("fabricated original callback failure")
    calls = []

    def clock():
        calls.append(True)
        if len(calls) == 2:
            raise fault("fabricated end clock failure")
        return 100

    def callback():
        raise original

    monkeypatch.setattr(diagnostic.time, "monotonic_ns", clock)
    with pytest.raises(OSError) as caught:
        evidence.query("windows", callback)
    assert caught.value is original
    assert calls == [True, True]
