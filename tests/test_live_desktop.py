"""Niri IPC transport oracles: one bounded read budget and constructor-only retry."""

import errno
import json
import subprocess
import time
import traceback

import pytest

from niri_desktop_continuity.restore import LiveDesktop


class ClockDesktop(LiveDesktop):
    def __init__(self):
        self.clock = time.monotonic()
        self.sleeps = []

    def monotonic(self):
        return self.clock

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds


class Client:
    def __init__(self, desktop, *, elapsed=0, response="[]", status=0, error=None):
        self.desktop, self.elapsed, self.response = desktop, elapsed, response
        self.returncode, self.error, self.timeouts = status, error, []

    def communicate(self, *, timeout):
        self.timeouts.append(timeout)
        self.desktop.clock += self.elapsed
        if self.error is not None:
            raise self.error
        return self.response, None

    def __getattr__(self, name):
        if name in {"wait", "terminate", "kill", "__enter__", "__exit__"}:
            raise AssertionError("no implicit cleanup: " + name)
        raise AttributeError(name)


def install(monkeypatch, desktop, sequence, elapsed=0):
    calls = []

    def construct(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs == {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "close_fds": True,
        }
        desktop.clock += elapsed
        value = sequence[len(calls) - 1]
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(subprocess, "Popen", construct)
    return calls


@pytest.mark.parametrize("name", ["windows", "workspaces", "version"])
@pytest.mark.parametrize("failures", [0, 1, 2])
def test_three_static_reads_exact_backoffs_and_remaining_budget(monkeypatch, name, failures):
    d = ClockDesktop()
    client = Client(d)
    errors = [BlockingIOError(errno.EAGAIN, "constructor") for _ in range(failures)]
    calls = install(monkeypatch, d, [*errors, client], elapsed=0.25)
    assert d._query(name) == []
    assert len(calls) == failures + 1
    assert d.sleeps == [0.05, 0.10][:failures]
    assert client.timeouts == [pytest.approx(10 - 0.25 * (failures + 1) - sum(d.sleeps))]
    assert [a for a, _ in calls] == [["niri", "msg", "--json", name]] * (failures + 1)


@pytest.mark.parametrize("name", ["windows", "workspaces", "version"])
def test_exhaustion_preserves_last_object_cause_errno_boundary_traceback(monkeypatch, name):
    d = ClockDesktop()
    errors = [BlockingIOError(errno.EAGAIN, str(i)) for i in range(3)]
    cause = ValueError("original cause")
    errors[-1].__cause__ = cause
    calls = install(monkeypatch, d, errors)
    with pytest.raises(BlockingIOError) as raised:
        d._query(name)
    assert raised.value is errors[-1] and raised.value.__cause__ is cause
    assert raised.value.errno == errno.EAGAIN and len(calls) == 3
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"
    assert d.sleeps == [0.05, 0.10]


@pytest.mark.parametrize("elapsed", [9.96, 10.0, 12.0])
def test_pending_eagain_budget_refuses_new_dispatch_preserving_object(monkeypatch, elapsed):
    d = ClockDesktop()
    error = BlockingIOError(errno.EAGAIN, "same object")
    calls = install(monkeypatch, d, [error], elapsed=elapsed)
    with pytest.raises(BlockingIOError) as raised:
        d.windows()
    assert raised.value is error and len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize("phase", ["construct", "communicate", "decode", "sleep"])
def test_late_success_and_sleep_never_renew_budget(monkeypatch, phase):
    d = ClockDesktop()
    client = Client(d, elapsed=11 if phase == "communicate" else 0)
    error = BlockingIOError(errno.EAGAIN, "pending")
    calls = install(
        monkeypatch,
        d,
        [error, client] if phase == "sleep" else [client],
        elapsed=11 if phase == "construct" else 0,
    )
    loads = json.loads
    if phase == "decode":

        def slow(text):
            value = loads(text)
            d.clock += 11
            return value

        monkeypatch.setattr(json, "loads", slow)
    if phase == "sleep":
        monkeypatch.setattr(d, "sleep", lambda seconds: setattr(d, "clock", d.clock + 11))
    expected = BlockingIOError if phase == "sleep" else subprocess.TimeoutExpired
    with pytest.raises(expected) as raised:
        d.windows()
    assert len(calls) == 1
    if phase == "construct":
        assert not client.timeouts
    if phase == "sleep":
        assert raised.value is error


@pytest.mark.parametrize(
    "error",
    [
        BlockingIOError(errno.EAGAIN, "communicate"),
        subprocess.TimeoutExpired(["read"], 0.2),
        UnicodeError("decode"),
        KeyboardInterrupt("cancel"),
        SystemExit("cancel"),
    ],
)
def test_communication_failure_single_client_no_termination(monkeypatch, error):
    d = ClockDesktop()
    client = Client(d, error=error)
    calls = install(monkeypatch, d, [client])
    with pytest.raises(type(error)) as raised:
        d.windows()
    assert raised.value is error and len(calls) == 1 and len(client.timeouts) == 1
    assert not d.sleeps


@pytest.mark.parametrize("phase", ["clock", "sleep", "decode"])
def test_eagain_outside_constructor_is_not_replayed(monkeypatch, phase):
    d = ClockDesktop()
    error = BlockingIOError(errno.EAGAIN, "not construction")
    client = Client(d)
    calls = install(
        monkeypatch, d, [BlockingIOError(errno.EAGAIN, "initial")] if phase == "sleep" else [client]
    )

    def fail(*args):
        raise error

    if phase == "clock":
        monkeypatch.setattr(d, "monotonic", fail)
    elif phase == "sleep":
        monkeypatch.setattr(d, "sleep", fail)
    else:
        monkeypatch.setattr(json, "loads", fail)
    with pytest.raises(BlockingIOError) as raised:
        d.windows()
    assert raised.value is error and len(calls) == (0 if phase == "clock" else 1)


@pytest.mark.parametrize(
    "error",
    [
        BlockingIOError(errno.EPERM, "permission"),
        OSError("ordinary EAGAIN"),
        ValueError("constructor"),
        subprocess.CalledProcessError(2, ["read"]),
        KeyboardInterrupt("cancel"),
        SystemExit("cancel"),
    ],
)
def test_other_constructor_failures_not_retried(monkeypatch, error):
    if type(error) is OSError:
        error.errno = errno.EAGAIN
    d = ClockDesktop()
    calls = install(monkeypatch, d, [error])
    with pytest.raises(type(error)) as raised:
        d.windows()
    assert raised.value is error and len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize(
    "response,status,error_type", [("{", 0, ValueError), ("[]", 2, subprocess.CalledProcessError)]
)
def test_decoding_and_nonzero_exit_not_retried(monkeypatch, response, status, error_type):
    d = ClockDesktop()
    calls = install(monkeypatch, d, [Client(d, response=response, status=status)])
    with pytest.raises(error_type):
        d.windows()
    assert len(calls) == 1 and not d.sleeps


def test_unknown_query_names_refuse_before_any_client(monkeypatch):
    d = ClockDesktop()
    calls = install(monkeypatch, d, [])
    for name in ("action", "spawn", "Windows", "", "--json"):
        with pytest.raises(ValueError, match="unsupported restore read query"):
            d._query(name)
    assert not calls


def test_version_ready_false_on_exhaustion(monkeypatch):
    d = ClockDesktop()
    calls = install(monkeypatch, d, [BlockingIOError(errno.EAGAIN, "version") for _ in range(3)])
    assert d.ready() is False and len(calls) == 3
    assert d.sleeps == [0.05, 0.10]


@pytest.mark.parametrize("phase", ["construct", "communicate", "decode"])
def test_late_success_is_the_transport_timeout_with_its_exact_fields(monkeypatch, phase):
    d = ClockDesktop()
    d.clock = 10.0
    client = Client(d, elapsed=11 if phase == "communicate" else 0)
    calls = install(monkeypatch, d, [client], elapsed=11 if phase == "construct" else 0)
    decoded = []

    def decode(text):
        decoded.append(text)
        if phase == "decode":
            d.clock = 21
        return []

    monkeypatch.setattr(json, "loads", decode)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        d._query("windows")
    assert type(raised.value) is subprocess.TimeoutExpired
    assert len(calls) == 1 and not d.sleeps
    assert raised.value.cmd == ["niri", "msg", "--json", "windows"]
    assert raised.value.timeout == 10
    assert raised.value.output is None and raised.value.stderr is None
    assert len(client.timeouts) == (0 if phase == "construct" else 1)
    assert len(decoded) == (1 if phase == "decode" else 0)


@pytest.mark.parametrize("failures", [1, 2])
@pytest.mark.parametrize("phase", ["construct", "communicate", "decode"])
def test_pending_last_eagain_outranks_a_late_success(monkeypatch, failures, phase):
    d = ClockDesktop()
    d.clock = 10.0
    errors = [BlockingIOError(errno.EAGAIN, str(i)) for i in range(failures)]
    causes = [ValueError("origin " + str(i)) for i in range(failures)]
    for error, cause in zip(errors, causes, strict=True):
        error.__cause__ = cause
    client, calls, decoded = Client(d), [], []

    def construct(argv, **kwargs):
        calls.append(argv)
        if len(calls) <= failures:
            raise errors[len(calls) - 1]
        if phase == "construct":
            d.clock = 21
        return client

    communicate = client.communicate

    def late_communicate(*, timeout):
        result = communicate(timeout=timeout)
        if phase == "communicate":
            d.clock = 21
        return result

    def decode(text):
        decoded.append(text)
        if phase == "decode":
            d.clock = 21
        return []

    monkeypatch.setattr(subprocess, "Popen", construct)
    monkeypatch.setattr(client, "communicate", late_communicate)
    monkeypatch.setattr(json, "loads", decode)
    with pytest.raises(BlockingIOError) as raised:
        d.windows()
    assert raised.value is errors[-1] and raised.value.__cause__ is causes[-1]
    assert raised.value.errno == errno.EAGAIN
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"
    assert len(calls) == failures + 1 <= 3 and d.sleeps == [0.05, 0.10][:failures]
    assert len(client.timeouts) == (0 if phase == "construct" else 1)
    assert len(decoded) == (1 if phase == "decode" else 0)


def test_pending_constructor_refusal_survives_a_scheduler_overrun(monkeypatch):
    d = ClockDesktop()
    d.clock = 10.0
    error = BlockingIOError(errno.EAGAIN, "scheduler original")
    error.__cause__ = ValueError("original cause")
    calls = install(monkeypatch, d, [error])

    def sleep(seconds):
        d.sleeps.append(seconds)
        d.clock = 21

    monkeypatch.setattr(d, "sleep", sleep)
    with pytest.raises(BlockingIOError) as raised:
        d.windows()
    assert raised.value is error and raised.value.__cause__.args == ("original cause",)
    assert raised.value.errno == errno.EAGAIN and len(calls) == 1 and d.sleeps == [0.05]
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"


@pytest.mark.parametrize("pending", [False, True])
def test_actual_communicate_timeout_is_not_reclassified(monkeypatch, pending):
    d = ClockDesktop()
    d.clock = 10.0
    error = subprocess.TimeoutExpired(["actual", "transport"], 0.25, output="out", stderr="err")
    error.__cause__ = ValueError("actual cause")
    original = dict(error.__dict__)
    client = Client(d, error=error)
    prior = [BlockingIOError(errno.EAGAIN, "prior")] if pending else []
    calls = install(monkeypatch, d, [*prior, client])
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        d.windows()
    assert raised.value is error and error.__dict__ == original
    assert error.__cause__.args == ("actual cause",)
    assert len(calls) == 1 + int(pending) and len(client.timeouts) == 1
    assert d.sleeps == ([0.05] if pending else [])


@pytest.mark.parametrize("phase", ["clock", "sleep", "decode"])
@pytest.mark.parametrize("kind", [BlockingIOError, KeyboardInterrupt, SystemExit])
def test_actual_operation_error_is_not_masked_by_pending(monkeypatch, phase, kind):
    d = ClockDesktop()
    d.clock = 10.0
    pending = BlockingIOError(errno.EAGAIN, "cached constructor")
    error = kind(errno.EAGAIN, "actual") if kind is BlockingIOError else kind("actual")
    error.__cause__ = ValueError("actual cause")
    client = Client(d)
    calls = install(monkeypatch, d, [pending, client])

    def fail(*args):
        raise error

    if phase == "clock":
        observations = []

        def clock():
            observations.append(True)
            if len(observations) == 3:  # Start, before constructor, caught-EAGAIN budget.
                raise error
            return d.clock

        monkeypatch.setattr(d, "monotonic", clock)
    elif phase == "sleep":
        monkeypatch.setattr(d, "sleep", fail)
    else:
        monkeypatch.setattr(json, "loads", fail)
    with pytest.raises(kind) as raised:
        d.windows()
    assert raised.value is error and error.__cause__.args == ("actual cause",)
    assert len(calls) == (2 if phase == "decode" else 1)
    assert len(client.timeouts) == (1 if phase == "decode" else 0)


def test_blockingioerror_subclass_never_retries(monkeypatch):
    class Derived(BlockingIOError):
        pass

    d = ClockDesktop()
    error = Derived(errno.EAGAIN, "not exact type")
    calls = install(monkeypatch, d, [error])
    with pytest.raises(Derived) as raised:
        d.windows()
    assert raised.value is error and len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize("pending", [False, True])
def test_sequenced_clock_one_sample_per_existing_check(monkeypatch, pending):
    d = ClockDesktop()
    values = (
        [1000, 1000.1, 1000.2, 1000.3, 1000.4, 1000.5, 1000.6]
        if pending
        else [1000, 1000.1, 1000.4, 1000.7, 1000.9]
    )
    seen, client = [], Client(d)

    def clock():
        value = values[len(seen)]  # Extra observations fail, rather than silently repeat.
        seen.append(value)
        return value

    monkeypatch.setattr(d, "monotonic", clock)
    errors = [BlockingIOError(errno.EAGAIN, "pending")] if pending else []
    calls = install(monkeypatch, d, [*errors, client])
    assert d.windows() == []
    assert seen == values and len(calls) == (2 if pending else 1)
    assert client.timeouts == [pytest.approx(9.6)]  # 1010 - 1000.4, not a helper clock.
    assert d.sleeps == ([0.05] if pending else [])


def test_caught_constructor_error_keeps_budget_priority(monkeypatch):
    d = ClockDesktop()
    d.clock = 10.0
    error = BlockingIOError(errno.EAGAIN, "caught original")
    cause = ValueError("origin")
    error.__cause__ = cause
    calls = install(monkeypatch, d, [error], elapsed=11)
    with pytest.raises(BlockingIOError) as raised:
        d.windows()
    assert raised.value is error and error.__cause__ is cause and error.errno == errno.EAGAIN
    assert traceback.extract_tb(error.__traceback__)[-1].name == "construct"
    assert len(calls) == 1 and not d.sleeps


class Effect:
    """A `niri msg action` client; killing it after an ambiguous reply would be a new effect."""

    def __init__(self, *, status=0, error=None):
        self.status, self.error, self.waits = status, error, []

    def wait(self, *, timeout):
        self.waits.append(timeout)
        if self.error is not None:
            raise self.error
        return self.status

    def __getattr__(self, name):
        if name in {"kill", "terminate", "communicate", "__enter__", "__exit__"}:
            raise AssertionError("no implicit cleanup: " + name)
        raise AttributeError(name)


def install_effect(monkeypatch, client):
    calls = []

    def construct(argv, **kwargs):
        calls.append((argv, kwargs))
        return client

    monkeypatch.setattr(subprocess, "Popen", construct)
    return calls


def test_action_is_one_client_with_the_exact_command_and_no_inherited_streams(monkeypatch):
    client = Effect()
    calls = install_effect(monkeypatch, client)
    LiveDesktop().action("focus-window", "--id", "7")
    assert calls == [
        (
            ["niri", "msg", "action", "focus-window", "--id", "7"],
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            },
        )
    ]
    assert client.waits == [10]


def test_spawn_passes_the_command_after_a_separator(monkeypatch):
    calls = install_effect(monkeypatch, Effect())
    LiveDesktop().spawn(["ghostty", "-e", "--odd"])
    assert calls[0][0] == ["niri", "msg", "action", "spawn", "--", "ghostty", "-e", "--odd"]


def test_action_timeout_is_ambiguous_so_it_neither_kills_nor_retries(monkeypatch):
    error = subprocess.TimeoutExpired(["niri"], 10)
    client = Effect(error=error)
    calls = install_effect(monkeypatch, client)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        LiveDesktop().action("focus-window", "--id", "7")
    assert raised.value is error and len(calls) == 1 and client.waits == [10]


def test_action_nonzero_exit_raises_once(monkeypatch):
    client = Effect(status=1)
    calls = install_effect(monkeypatch, client)
    with pytest.raises(subprocess.CalledProcessError) as raised:
        LiveDesktop().action("focus-window", "--id", "7")
    assert raised.value.returncode == 1 and len(calls) == 1
