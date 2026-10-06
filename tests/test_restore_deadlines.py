"""Independent native transport oracles: absolute budgets and constructor-only retry."""

import errno
import json
import subprocess
import time
import traceback
from types import SimpleNamespace

import pytest
from test_restore_handshake import fabricated_elf as fabricated_elf  # noqa: F401
from test_restore_queries import run_boundary

from niri_desktop_continuity import restore
from niri_desktop_continuity.restore_failure_observation import FailureObservation
from niri_desktop_continuity.restore_layout import Layout
from niri_desktop_continuity.restore_observation import output_inventory


class ClockDesktop(restore.LiveDesktop):
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

        monkeypatch.setattr(restore.json, "loads", slow)
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
        monkeypatch.setattr(restore.json, "loads", fail)
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


def test_outputs_original_single_dispatch_and_unknown_names_refuse(monkeypatch):
    d = ClockDesktop()
    error = BlockingIOError(errno.EAGAIN, "outputs")
    calls = install(monkeypatch, d, [error])
    with pytest.raises(BlockingIOError) as raised:
        d._query("outputs")
    assert raised.value is error and len(calls) == 1 and not d.sleeps
    for name in ("action", "spawn", "Windows", "", "--json"):
        with pytest.raises(ValueError, match="unsupported restore read query"):
            d._query(name)
    assert len(calls) == 1


def test_version_ready_false_on_exhaustion(monkeypatch):
    d = ClockDesktop()
    calls = install(monkeypatch, d, [BlockingIOError(errno.EAGAIN, "version") for _ in range(3)])
    assert d.ready() is False and len(calls) == 3
    assert d.sleeps == [0.05, 0.10]


def test_native_reads_share_original_absolute_caller_budget(monkeypatch):
    d = ClockDesktop()
    first, second = Client(d, elapsed=0.3), Client(d, elapsed=0.3)
    calls = install(monkeypatch, d, [first, second], elapsed=0.1)
    deadline = d.clock + 1
    assert d.windows(deadline=deadline) == []
    assert d.workspaces(deadline=deadline) == []
    assert first.timeouts == [pytest.approx(0.9)]
    assert second.timeouts == [pytest.approx(0.5)]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "style", ["delegated", "instance", "override", "replacement", "keyword-free"]
)
@pytest.mark.parametrize("error", [TypeError("custom"), BlockingIOError(errno.EAGAIN, "custom")])
def test_layout_calls_selected_custom_receiver_once_no_signature_fallback(
    monkeypatch, style, error
):
    seen = []

    def custom(self, *, deadline=None):
        seen.append((self, deadline))
        raise error

    d = restore.LiveDesktop()
    receiver = d
    if style == "delegated":
        receiver = restore.LiveDesktop()
        d.windows = custom.__get__(receiver)
    elif style == "instance":
        d.windows = custom.__get__(d)
    elif style == "override":
        d = type("Override", (restore.LiveDesktop,), {"windows": custom})()
        receiver = d
    elif style == "replacement":
        monkeypatch.setattr(restore.LiveDesktop, "windows", custom)
    else:

        def keyword_free():
            raise AssertionError("body must not be entered with an unsupported keyword")

        d.windows = keyword_free
    layout = Layout.__new__(Layout)
    layout.desktop, layout.inventory_failed = d, False
    layout.output_inventory = output_inventory([])
    layout.failure_observation = FailureObservation()
    deadline = time.monotonic() + 10
    with pytest.raises(TypeError if style == "keyword-free" else type(error)) as raised:
        layout.sample(deadline)
    if style == "keyword-free":
        assert not seen
    else:
        assert raised.value is error and seen == [(receiver, deadline)]


def test_inherited_native_layout_sample_uses_deadline_and_mandatory_outputs(monkeypatch):
    d = type("Inherited", (restore.LiveDesktop,), {})()
    calls = []

    def construct(argv, **kwargs):
        calls.append(argv[-1])
        replies = {
            "windows": "[]",
            "workspaces": '[{"id":41,"idx":1,"output":"DP-1","is_focused":true,"active_window_id":null}]',
            "outputs": '[{"name":"DP-1","logical":{"scale":8.0}}]',
        }
        return SimpleNamespace(returncode=0, communicate=lambda **kw: (replies[argv[-1]], None))

    monkeypatch.setattr(subprocess, "Popen", construct)
    layout = Layout.__new__(Layout)
    layout.desktop, layout.inventory_failed = d, False
    layout.output_inventory = output_inventory([{"name": "DP-1", "logical": {"scale": 8.0}}])
    layout.failure_observation = FailureObservation()
    value = layout.sample(time.monotonic() + 1)
    assert value["windows"] == [] and value["outputs"] == [{"name": "DP-1", "scale": 8.0}]
    assert calls == ["windows", "workspaces", "outputs"]


@pytest.mark.parametrize("offset", [-1, 0])
def test_expired_caller_budget_never_constructs_or_supplies_payload(monkeypatch, offset):
    d = ClockDesktop()
    calls = install(monkeypatch, d, [])
    with pytest.raises(TimeoutError) as raised:
        d.windows(deadline=d.clock + offset)
    assert type(raised.value) is TimeoutError
    assert str(raised.value) == "bootstrap absolute deadline exceeded or invalid"
    assert not calls and not d.sleeps


@pytest.mark.parametrize("budget,count", [(0.04, 1), (0.05, 1), (0.12, 2), (0.14, 2)])
def test_tiny_caller_budget_preserves_last_eagain(monkeypatch, budget, count):
    d = ClockDesktop()
    d.clock = 0.0  # Exact handwritten boundary, not rounded subtraction at a large uptime.
    errors = [BlockingIOError(errno.EAGAIN, str(i)) for i in range(count)]
    cause = ValueError("last original cause")
    errors[-1].__cause__ = cause
    calls = install(monkeypatch, d, errors)
    with pytest.raises(BlockingIOError) as raised:
        d.windows(deadline=d.clock + budget)
    assert raised.value is errors[-1] and len(calls) == count
    assert raised.value.__cause__ is cause and raised.value.errno == errno.EAGAIN
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"
    assert d.sleeps == ([] if count == 1 else [0.05])


@pytest.mark.parametrize(
    "shape",
    [
        "ordinary",
        "inherited",
        "subclass-override",
        "instance-forward",
        "delegated",
        "class-symbol",
        "class-method",
    ],
)
def test_native_positive_selected_receiver_shapes_call_actual_query_once_each(monkeypatch, shape):
    native = restore.LiveDesktop
    original_windows, original_workspaces = native.windows, native.workspaces
    original_query = native.__dict__["_query"]
    selected, receivers, constructions = [], [], []

    def windows(self, *, deadline=None):
        selected.append(("windows", self, deadline))
        return original_windows(self, deadline=deadline)

    def workspaces(self, *, deadline=None):
        selected.append(("workspaces", self, deadline))
        return original_workspaces(self, deadline=deadline)

    if shape in {"inherited", "subclass-override"}:
        methods = {} if shape == "inherited" else {"windows": windows, "workspaces": workspaces}
        desktop = type("PositiveNative", (native,), methods)()
    else:
        desktop = native()
    chosen = desktop
    if shape == "instance-forward":
        desktop.windows = lambda *, deadline=None: windows(desktop, deadline=deadline)
        desktop.workspaces = lambda *, deadline=None: workspaces(desktop, deadline=deadline)
    elif shape == "delegated":
        chosen = native()
        desktop.windows, desktop.workspaces = chosen.windows, chosen.workspaces
    elif shape == "class-symbol":
        monkeypatch.setattr(restore, "LiveDesktop", object)
    elif shape == "class-method":
        monkeypatch.setattr(native, "windows", windows)
        monkeypatch.setattr(native, "workspaces", workspaces)

    def query(self, name, *, deadline=None):
        receivers.append((self, name, deadline))
        return original_query.__get__(self, type(self))(name, deadline=deadline)

    monkeypatch.setattr(native, "_query", query)
    payloads = {
        "windows": "[]",
        "workspaces": '[{"id":41,"idx":1,"output":"DP-1","is_focused":true,"active_window_id":null}]',
        "outputs": '[{"name":"DP-1","logical":{"scale":8.0}}]',
    }

    def constructor(argv, **kwargs):
        name = argv[3]
        constructions.append(name)
        assert kwargs == {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "close_fds": True,
        }
        if constructions == ["windows"]:
            raise BlockingIOError(errno.EAGAIN, "native positive constructor")

        def communicate(*, timeout):
            assert 0 < timeout <= 3
            return payloads[name], ""

        return SimpleNamespace(returncode=0, communicate=communicate)

    monkeypatch.setattr(subprocess, "Popen", constructor)
    deadline = time.monotonic() + 3
    layout = Layout.__new__(Layout)
    layout.desktop, layout.inventory_failed = desktop, False
    layout.output_inventory = output_inventory([{"name": "DP-1", "logical": {"scale": 8.0}}])
    layout.failure_observation = FailureObservation()
    value = layout.sample(deadline)
    assert value["windows"] == [] and value["outputs"] == [{"name": "DP-1", "scale": 8.0}]
    assert receivers == [
        (chosen, "windows", deadline),
        (chosen, "workspaces", deadline),
        (desktop, "outputs", deadline),
    ]
    assert constructions == ["windows", "windows", "workspaces", "outputs"]
    if shape in {"subclass-override", "instance-forward", "class-method"}:
        assert selected == [("windows", desktop, deadline), ("workspaces", desktop, deadline)]


CALLER_ERROR = "bootstrap absolute deadline exceeded or invalid"


@pytest.mark.parametrize("name", ["windows", "workspaces", "version"])
@pytest.mark.parametrize("left", [-1, 0, float("nan"), float("inf"), -float("inf"), 301])
def test_amendment_invalid_caller_exact_owner_error_before_dispatch(monkeypatch, name, left):
    d = ClockDesktop()
    d.clock = 1000.0  # Validate remaining duration, not the absolute epoch.
    calls = install(monkeypatch, d, [])
    with pytest.raises(TimeoutError) as raised:
        d._query(name, deadline=1000 + left)
    assert type(raised.value) is TimeoutError and str(raised.value) == CALLER_ERROR
    assert raised.value.args == (CALLER_ERROR,) and not calls and not d.sleeps


@pytest.mark.parametrize("name", ["windows", "workspaces", "version"])
def test_amendment_exact_300_remaining_is_valid_and_local_cap_is_ten(monkeypatch, name):
    d = ClockDesktop()
    d.clock = 1000.0
    client = Client(d)
    calls = install(monkeypatch, d, [client])
    assert d._query(name, deadline=1300.0) == []
    assert client.timeouts == [10.0] and len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize("name", ["windows", "workspaces", "version"])
@pytest.mark.parametrize("kind", [TypeError, OverflowError])
def test_amendment_arithmetic_error_is_actual_original_object(monkeypatch, name, kind):
    error = kind("actual subtraction")

    class Deadline:
        def __sub__(self, other):
            raise error

    d = ClockDesktop()
    calls = install(monkeypatch, d, [])
    with pytest.raises(kind) as raised:
        d._query(name, deadline=Deadline())
    assert raised.value is error and not calls and not d.sleeps


@pytest.mark.parametrize("phase", ["construct", "communicate", "decode"])
@pytest.mark.parametrize(
    "deadline,end,kind",
    [
        (None, 21, subprocess.TimeoutExpired),
        (30, 21, subprocess.TimeoutExpired),
        (15, 16, TimeoutError),
        (20, 20, TimeoutError),
        (15, 25, TimeoutError),
    ],
)
def test_amendment_local_caller_tie_both_late_success_classification(
    monkeypatch, phase, deadline, end, kind
):
    d = ClockDesktop()
    d.clock = 10.0
    client = Client(d, elapsed=end - 10 if phase == "communicate" else 0)
    calls = install(monkeypatch, d, [client], elapsed=end - 10 if phase == "construct" else 0)
    decoded = []

    def decode(text):
        decoded.append(text)
        if phase == "decode":
            d.clock = end
        return []

    monkeypatch.setattr(restore.json, "loads", decode)
    with pytest.raises(kind) as raised:
        d._query("windows", deadline=deadline)
    assert type(raised.value) is kind and len(calls) == 1 and not d.sleeps
    if kind is TimeoutError:
        assert str(raised.value) == CALLER_ERROR and raised.value.args == (CALLER_ERROR,)
    else:
        assert raised.value.cmd == ["niri", "msg", "--json", "windows"]
        assert raised.value.timeout == 10
        assert raised.value.output is None and raised.value.stderr is None
    assert len(client.timeouts) == (0 if phase == "construct" else 1)
    assert len(decoded) == (1 if phase == "decode" else 0)


@pytest.mark.parametrize("failures", [1, 2])
@pytest.mark.parametrize("phase", ["construct", "communicate", "decode"])
@pytest.mark.parametrize("deadline,end", [(None, 21), (30, 21), (15, 16), (20, 20), (15, 25)])
def test_amendment_pending_last_eagain_outranks_both_success_overruns(
    monkeypatch, failures, phase, deadline, end
):
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
            d.clock = end
        return client

    communicate = client.communicate

    def late_communicate(*, timeout):
        result = communicate(timeout=timeout)
        if phase == "communicate":
            d.clock = end
        return result

    def decode(text):
        decoded.append(text)
        if phase == "decode":
            d.clock = end
        return []

    monkeypatch.setattr(subprocess, "Popen", construct)
    monkeypatch.setattr(client, "communicate", late_communicate)
    monkeypatch.setattr(restore.json, "loads", decode)
    with pytest.raises(BlockingIOError) as raised:
        d.windows(deadline=deadline)
    assert raised.value is errors[-1] and raised.value.__cause__ is causes[-1]
    assert raised.value.errno == errno.EAGAIN
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"
    assert len(calls) == failures + 1 <= 3 and d.sleeps == [0.05, 0.10][:failures]
    assert len(client.timeouts) == (0 if phase == "construct" else 1)
    assert len(decoded) == (1 if phase == "decode" else 0)


@pytest.mark.parametrize("deadline,end", [(None, 21), (30, 21), (15, 16), (20, 20), (15, 25)])
def test_amendment_pending_constructor_refusal_and_scheduler_overrun(monkeypatch, deadline, end):
    d = ClockDesktop()
    d.clock = 10.0
    error = BlockingIOError(errno.EAGAIN, "scheduler original")
    error.__cause__ = ValueError("original cause")
    calls = install(monkeypatch, d, [error])

    def sleep(seconds):
        d.sleeps.append(seconds)
        d.clock = end

    monkeypatch.setattr(d, "sleep", sleep)
    with pytest.raises(BlockingIOError) as raised:
        d.windows(deadline=deadline)
    assert raised.value is error and raised.value.__cause__.args == ("original cause",)
    assert raised.value.errno == errno.EAGAIN and len(calls) == 1 and d.sleeps == [0.05]
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "construct"


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("caller_expired", [False, True])
def test_amendment_actual_communicate_timeout_not_reclassified(
    monkeypatch, pending, caller_expired
):
    d = ClockDesktop()
    d.clock = 10.0
    error = subprocess.TimeoutExpired(["actual", "transport"], 0.25, output="out", stderr="err")
    error.__cause__ = ValueError("actual cause")
    original = dict(error.__dict__)
    client = Client(d, elapsed=11 if caller_expired else 0, error=error)
    prior = [BlockingIOError(errno.EAGAIN, "prior")] if pending else []
    calls = install(monkeypatch, d, [*prior, client])
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        d.windows(deadline=15)
    assert raised.value is error and error.__dict__ == original
    assert error.__cause__.args == ("actual cause",)
    assert len(calls) == 1 + int(pending) and len(client.timeouts) == 1
    assert d.sleeps == ([0.05] if pending else [])


@pytest.mark.parametrize("phase", ["clock", "sleep", "decode"])
@pytest.mark.parametrize("kind", [BlockingIOError, KeyboardInterrupt, SystemExit])
def test_amendment_actual_operation_error_not_masked_by_pending(monkeypatch, phase, kind):
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
        monkeypatch.setattr(restore.json, "loads", fail)
    with pytest.raises(kind) as raised:
        d.windows(deadline=15)
    assert raised.value is error and error.__cause__.args == ("actual cause",)
    assert len(calls) == (2 if phase == "decode" else 1)
    assert len(client.timeouts) == (1 if phase == "decode" else 0)


def test_amendment_blockingioerror_subclass_never_retries(monkeypatch):
    class Derived(BlockingIOError):
        pass

    d = ClockDesktop()
    error = Derived(errno.EAGAIN, "not exact type")
    calls = install(monkeypatch, d, [error])
    with pytest.raises(Derived) as raised:
        d.windows()
    assert raised.value is error and len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize("pending", [False, True])
def test_amendment_sequenced_clock_one_sample_per_existing_check(monkeypatch, pending):
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
    assert d.windows(deadline=1001) == []
    assert seen == values and len(calls) == (2 if pending else 1)
    assert client.timeouts == [pytest.approx(0.6)]  # 1001 - 1000.4, not a helper clock.
    assert d.sleeps == ([0.05] if pending else [])


@pytest.mark.parametrize("pending", [False, True])
def test_amendment_sequenced_clock_caller_refusal_has_no_extra_operations(monkeypatch, pending):
    d = ClockDesktop()
    values = [10, 10.1, 10.2, 10.3, 10.4, 16] if pending else [10, 10.1, 10.2, 16]
    seen, client, decoded = [], Client(d), []

    def clock():
        value = values[len(seen)]
        seen.append(value)
        return value

    error = BlockingIOError(errno.EAGAIN, "pending")
    calls = install(monkeypatch, d, [error, client] if pending else [client])
    monkeypatch.setattr(d, "monotonic", clock)
    monkeypatch.setattr(restore.json, "loads", lambda text: decoded.append(text))
    with pytest.raises(BlockingIOError if pending else TimeoutError) as raised:
        d.windows(deadline=15)
    assert seen == values and not decoded and len(calls) == (2 if pending else 1)
    assert client.timeouts == [pytest.approx(4.6 if pending else 4.8)]
    if pending:
        assert raised.value is error
    else:
        assert type(raised.value) is TimeoutError and str(raised.value) == CALLER_ERROR


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("kind", [BlockingIOError, KeyboardInterrupt, SystemExit])
def test_amendment_actual_communicate_error_with_expired_caller_is_unwrapped(
    monkeypatch, pending, kind
):
    d = ClockDesktop()
    d.clock = 10.0
    error = kind(errno.EAGAIN, "actual") if kind is BlockingIOError else kind("actual")
    error.__cause__ = ValueError("actual cause")
    client = Client(d, elapsed=11, error=error)
    prior = [BlockingIOError(errno.EAGAIN, "cached")] if pending else []
    calls = install(monkeypatch, d, [*prior, client])
    with pytest.raises(kind) as raised:
        d.windows(deadline=15)
    assert raised.value is error and error.__cause__.args == ("actual cause",)
    assert len(calls) == 1 + int(pending) and len(client.timeouts) == 1
    assert d.sleeps == ([0.05] if pending else [])


@pytest.mark.parametrize("deadline,end", [(None, 21), (30, 21), (15, 16), (20, 20), (15, 25)])
def test_amendment_caught_constructor_error_budget_priority(monkeypatch, deadline, end):
    d = ClockDesktop()
    d.clock = 10.0
    error = BlockingIOError(errno.EAGAIN, "caught original")
    cause = ValueError("origin")
    error.__cause__ = cause
    calls = install(monkeypatch, d, [error], elapsed=end - 10)
    with pytest.raises(BlockingIOError) as raised:
        d.windows(deadline=deadline)
    assert raised.value is error and error.__cause__ is cause and error.errno == errno.EAGAIN
    assert traceback.extract_tb(error.__traceback__)[-1].name == "construct"
    assert len(calls) == 1 and not d.sleeps


@pytest.mark.parametrize("phase", ["subtract", "finite"])
def test_amendment_actual_budget_operation_error_not_masked_by_pending(monkeypatch, phase):
    d = ClockDesktop()
    d.clock = 10.0
    pending = BlockingIOError(errno.EAGAIN, "pending")
    actual = OverflowError("budget operation")

    class Deadline:
        def __sub__(self, checked):
            if calls and phase == "subtract":
                raise actual
            return 5.0

    calls = install(monkeypatch, d, [pending])
    if phase == "finite":
        import math

        finite = math.isfinite

        def check(value):
            if calls:
                raise actual
            return finite(value)

        monkeypatch.setattr(restore.math, "isfinite", check)
    with pytest.raises(OverflowError) as raised:
        d.windows(deadline=Deadline())
    assert raised.value is actual and len(calls) == 1 and not d.sleeps


def test_amendment_outputs_original_caller_clock_and_single_dispatch(monkeypatch):
    # Outputs retains restore_wire.remaining's clock, not eligible self.monotonic.
    d = ClockDesktop()
    seen, client = [], Client(d)
    values = [10, 10.2, 10.4, 10.6]

    def original_clock():
        value = values[len(seen)]
        seen.append(value)
        return value

    def forbidden():
        raise AssertionError("Outputs must not sample eligible query clock")

    monkeypatch.setattr(time, "monotonic", original_clock)
    monkeypatch.setattr(d, "monotonic", forbidden)
    calls = install(monkeypatch, d, [client])
    assert d._query("outputs", deadline=11) == []
    assert seen == values and len(calls) == 1 and not d.sleeps
    assert client.timeouts == [pytest.approx(0.8)]


def test_amendment_actual_integrated_communicate_timeout_after_pending(
    tmp_path, fabricated_elf, monkeypatch
):
    from unittest.mock import patch

    from niri_desktop_continuity.restore_attempt import Attempt

    native, observed = restore.LiveDesktop._query, Attempt.observed
    proofs, attempts, communicated, records = [], [], [], []
    actual = subprocess.TimeoutExpired(["actual", "transport"], 0.25, output="out", stderr="err")
    actual.__cause__ = ValueError("actual cause")
    fields = dict(actual.__dict__)
    append = Attempt.append

    def record(self, kind, payload):
        result = append(self, kind, payload)
        records.append(kind)
        return result

    def proof(self, evidence):
        result = observed(self, evidence)
        if evidence.get("phase") == "process-observed":
            proofs.append(evidence)
        return result

    def query(self, name, *, deadline=None):
        if name != "windows" or len(proofs) != 2 or deadline is None:
            return native(self, name, deadline=deadline)
        construct = subprocess.Popen  # The reached real-executor fault fixture, not a fake proof.

        def client(argv, **kwargs):
            attempts.append(argv[-1])
            created = construct(argv, **kwargs)  # First constructor raises real boundary EAGAIN.

            class Reply:
                @property
                def returncode(self):
                    return created.returncode

                def communicate(self, *, timeout):
                    created.communicate(timeout=timeout)
                    communicated.append(timeout)
                    raise actual

                def __getattr__(self, name):
                    raise AssertionError("no communicate-error cleanup: " + name)

            return Reply()

        with patch.object(subprocess, "Popen", client):
            try:
                return native(self, name, deadline=deadline)
            except subprocess.TimeoutExpired as exc:
                assert exc is actual and exc.__dict__ == fields
                raise

    with (
        patch.object(Attempt, "observed", proof),
        patch.object(Attempt, "append", record),
        patch.object(restore.LiveDesktop, "_query", query),
    ):
        result = run_boundary(tmp_path, fabricated_elf, scenario="communicate-timeout")
    assert len(proofs) == 2 and attempts == ["windows", "windows"] and len(communicated) == 1
    assert result["error_type"] == "TimeoutExpired" and result["error"] == str(actual)
    assert actual.__cause__.args == ("actual cause",) and actual.__dict__ == fields
    assert records.count("association") == 1 and "terminal" not in records
    assert result["status"] == "interrupted" and len(result["effects"]) == 1


def test_amendment_actual_postlaunch_caller_expiry_no_new_authority(tmp_path, fabricated_elf):
    result = run_boundary(tmp_path, fabricated_elf, failures=0, scenario="caller-expiry")
    assert result["status"] == "interrupted" and result["error_type"] == "TimeoutError"
    assert (tmp_path / "boundary-evidence.json").is_file()
