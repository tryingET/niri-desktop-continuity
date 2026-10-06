"""Given/When/Then fault oracles: fabricated IO only; never a compositor."""

import inspect
import json
import os

import pytest

from niri_desktop_continuity import cli
from niri_desktop_continuity import operation_lock as locks
from niri_desktop_continuity import restore_disposition_cli as command
from niri_desktop_continuity import restore_reader_io as bounded
from niri_desktop_continuity.restore_reader import Counters

SECRET = "PRIVATE-SENTINEL-ARGUMENT"


def objects(root):
    seen, pending = set(), [root]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        if item.__cause__ is not None:
            pending.append(item.__cause__)
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions)


def assert_wire(text, *, phase, reason, cleanup=False, publication="not-attempted"):
    expected = {
        "status": "error",
        "error": "restore-disposition-refused",
        "diagnostic": {
            "schema": "restore-accounting-failure.v1",
            "phase": phase,
            "phase_state": "entered",
            "reason": reason,
            "publication": publication,
            "cleanup_failure": cleanup,
        },
    }
    # Handwritten field/value oracle, not the producer's encoder or table.
    assert text == json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n"
    assert len(text.encode("ascii")) <= 2048
    assert SECRET not in text and "Traceback" not in text


@pytest.mark.parametrize("failure", [OSError(SECRET), KeyboardInterrupt(SECRET), SystemExit(0)])
def test_given_disposition_when_body_fails_then_bounded_nonzero(failure, monkeypatch, capsys):
    reached = []

    def run(args):
        assert args.command == "restore-disposition"
        reached.append("body")
        raise failure

    monkeypatch.setattr(cli, "run", run)
    try:
        status = cli.main(["restore-disposition", "apply", "a" * 64])
    except BaseException as observed:
        assert reached == ["body"]  # RED is a reached operation, not import/parser failure.
        pytest.fail(f"command boundary let cancellation escape: {type(observed).__name__}")
    assert reached == ["body"]
    out = capsys.readouterr()
    assert not out.out
    reason = "io-failed" if isinstance(failure, OSError) else "interrupted"
    assert status == (
        2 if reason == "io-failed" else 130 if isinstance(failure, KeyboardInterrupt) else 1
    )
    assert_wire(out.err, phase="route", reason=reason)


@pytest.mark.parametrize(
    "argv",
    [
        ["restore-disposition", "apply", SECRET, "--unknown", SECRET],
        ["restore-disposition", "propose", SECRET, "--family", SECRET],
        ["--state-root", SECRET, "restore-disposition", "missing-" + SECRET],
    ],
)
def test_given_selected_command_when_parser_refuses_then_no_argument_echo(argv, capsys):
    try:
        status = cli.main(argv)
    except SystemExit as observed:
        assert observed.code == 2  # Real argparse rejection reached in RED.
        status = observed.code
    out = capsys.readouterr()
    assert status == 2 and not out.out
    assert_wire(out.err, phase="parse", reason="invalid-arguments")


def test_given_private_value_named_command_when_other_command_then_old_boundary(
    monkeypatch, capsys
):
    reached = []

    def run(args):
        reached.append(args.command)
        raise ValueError("unchanged-other-command")

    monkeypatch.setattr(cli, "run", run)
    assert cli.main(["--state-root", "restore-disposition", "history"]) == 2
    assert reached == ["history"]
    assert json.loads(capsys.readouterr().err) == {
        "status": "error",
        "error": "unchanged-other-command",
    }


def test_given_disposition_library_when_store_fails_then_same_primary_and_prior(monkeypatch):
    primary, prior = ValueError(SECRET), OSError("prior")
    primary.__cause__ = prior
    reached = []

    def fail(*args, **kwargs):
        reached.append("store")
        raise primary

    monkeypatch.setattr(command, "Store", fail)
    args = cli.parser().parse_args(["restore-disposition", "apply", "a" * 64])
    with pytest.raises(BaseException) as caught:
        command.run(args)
    assert reached == ["store"]
    assert caught.value is primary
    assert caught.value.__cause__ is prior


def lock_fixture(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    directory = tmp_path / "niri-desktop-continuity-locks"
    directory.mkdir(mode=0o700)
    identity = {"boot_id": "fixture", "socket_device": 1, "socket_inode": 2}
    from niri_desktop_continuity.model import digest

    path = directory / f"{digest(identity)}.lock"
    path.write_bytes(b"")
    path.chmod(0o600)
    monkeypatch.setattr(locks, "runtime_root", lambda: tmp_path)
    return identity


@pytest.mark.parametrize("where", ["pre-yield", "body"])
def test_given_owned_lock_when_primary_and_close_fail_then_all_actual_objects(
    tmp_path, monkeypatch, where
):
    identity = lock_fixture(tmp_path, monkeypatch)
    primary, prior, cleanup = ValueError(SECRET), OSError("prior"), KeyboardInterrupt("cleanup")
    primary.__cause__ = prior
    closed, reached = [], []
    real_close = os.close

    def close(fd):
        closed.append(fd)
        real_close(fd)
        raise cleanup

    def check(path):
        reached.append("pre-yield")
        if where == "pre-yield":
            raise primary

    monkeypatch.setattr(locks, "check_file", check)
    monkeypatch.setattr(locks.os, "close", close)
    options = {"effectful": False, "existing_only": True}
    # Exercise the exact defective legacy path on baseline, not a missing-keyword proxy RED.
    if "_preserve_disposition_failures" in inspect.signature(locks.operation_lock).parameters:
        options["_preserve_disposition_failures"] = True
    with pytest.raises(BaseException) as caught:
        with locks.operation_lock(identity, **options):
            reached.append("body")
            raise primary
    assert reached == (["pre-yield"] if where == "pre-yield" else ["pre-yield", "body"])
    assert len(closed) == 1
    assert caught.value is primary
    assert {id(e) for e in objects(caught.value)} >= {id(primary), id(prior), id(cleanup)}


def test_given_reserved_file_when_read_and_both_closes_fail_then_all_objects(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / "evidence"
    path.write_bytes(b"fabricated")
    path.chmod(0o600)
    reservation = bounded.identity(path)
    primary, prior = ValueError(SECRET), SystemExit(7)
    primary.__cause__ = prior
    cleanups = [OSError("file-close"), KeyboardInterrupt("directory-close")]
    reached, closed = [], []
    real_close = os.close

    def read(fd, count):
        reached.append((fd, count))
        raise primary

    def close(fd):
        real_close(fd)
        closed.append(fd)
        raise cleanups[len(closed) - 1]

    monkeypatch.setattr(bounded.os, "read", read)
    monkeypatch.setattr(bounded.os, "close", close)
    with pytest.raises(BaseException) as caught:
        bounded.raw(path, reservation, Counters())
    assert len(reached) == 1 and reached[0][1] == len(b"fabricated")
    assert len(closed) == 2 and len(set(closed)) == 2
    assert caught.value is primary
    assert {id(e) for e in objects(caught.value)} >= {
        id(primary),
        id(prior),
        *(id(e) for e in cleanups),
    }


@pytest.mark.parametrize("value", [None, 0, True, False, "private", -1, 256, 8])
def test_given_runtime_system_exit_when_projected_then_actual_integer_policy(
    value, monkeypatch, capsys
):
    failure = SystemExit(value)

    def run(args):
        raise failure

    monkeypatch.setattr(cli, "run", run)
    expected = 8 if type(value) is int and value == 8 else 1
    assert cli.main(["restore-disposition", "apply", "a" * 64]) == expected
    assert_wire(capsys.readouterr().err, phase="route", reason="interrupted")


@pytest.mark.parametrize(
    "members,expected",
    [
        ([SystemExit(6), SystemExit(6)], 6),
        ([SystemExit(6), SystemExit(7)], 1),
        ([SystemExit(True), SystemExit(0)], 1),
        ([SystemExit(6), KeyboardInterrupt(SECRET)], 130),
        ([OSError(SECRET), RuntimeError(SECRET)], 1),
    ],
)
def test_given_actual_group_when_projected_then_closed_nonzero(
    members, expected, monkeypatch, capsys
):
    primary = BaseExceptionGroup(SECRET, members)

    def run(args):
        raise primary

    monkeypatch.setattr(cli, "run", run)
    assert cli.main(["restore-disposition", "apply", "a" * 64]) == expected
    reason = "unexpected" if not any(isinstance(e, SystemExit) for e in members) else "interrupted"
    assert_wire(capsys.readouterr().err, phase="route", reason=reason)


@pytest.mark.parametrize(
    "option,value",
    [
        ("--state-root", "restore-disposition"),
        ("--state-root=restore-disposition", None),
    ],
)
def test_given_command_string_as_option_value_when_selected_then_not_disposition(option, value):
    argv = [option, *([] if value is None else [value]), "history"]
    assert cli._disposition_selected(argv) is False
    assert cli._disposition_selected(
        ["--state-root", SECRET, "restore-disposition", "apply", SECRET]
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["restore-disposition", "--help"],
        ["restore-disposition", "apply", "--help"],
    ],
)
def test_given_explicit_help_when_selected_then_static_success(argv, capsys):
    assert cli.main(argv) == 0
    out = capsys.readouterr()
    assert "usage:" in out.out and not out.err


@pytest.mark.parametrize("fault", ["serialize", "write", "short-write", "flush"])
def test_given_completed_body_when_output_fails_then_no_success_or_retry(
    fault, monkeypatch, capsys
):
    from niri_desktop_continuity import restore_disposition_failure as failures

    events = []
    real_json = cli.json.dumps

    def run(args):
        events.append("body-returned-after-teardown")
        return {"status": "operator-accepted-partial"}, 2

    def dumps(value, **options):
        if fault == "serialize" and value.get("status") == "operator-accepted-partial":
            events.append("serialize")
            raise KeyboardInterrupt(SECRET)
        return real_json(value, **options)

    class Stream:
        def write(self, text):
            events.append("write")
            if fault == "write":
                raise BrokenPipeError(SECRET)
            return 1 if fault == "short-write" else len(text)

        def flush(self):
            events.append("flush")
            raise SystemExit(9)

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli.json, "dumps", dumps)
    monkeypatch.setattr(cli.sys, "stdout", Stream())
    assert (
        cli.main(["restore-disposition", "apply", "a" * 64])
        == {
            "serialize": 130,
            "write": 2,
            "short-write": 2,
            "flush": 9,
        }[fault]
    )
    assert events == [
        "body-returned-after-teardown",
        *(
            {
                "serialize": ["serialize"],
                "write": ["write"],
                "short-write": ["write"],
                "flush": ["write", "flush"],
            }[fault]
        ),
    ]
    assert_wire(
        capsys.readouterr().err,
        phase="result",
        reason=("io-failed" if fault in {"write", "short-write"} else "interrupted"),
    )
    assert failures._active.get() is None  # Per invocation, no stale cross-command tracker.


@pytest.mark.parametrize("fault", ["encoding", "write", "flush"])
def test_given_primary_when_diagnostic_fails_then_primary_and_exit_survive(fault, monkeypatch):
    from niri_desktop_continuity import restore_disposition_failure as failures

    primary, prior, diagnostic = OSError(SECRET), ValueError("prior"), SystemExit(0)
    primary.__cause__ = prior
    calls = []

    def encode(*args, **kwargs):
        calls.append("encoding")
        raise diagnostic

    class Stream:
        def write(self, text):
            calls.append("write")
            if fault == "write":
                raise diagnostic
            return len(text)

        def flush(self):
            calls.append("flush")
            raise diagnostic

    if fault == "encoding":
        monkeypatch.setattr(failures.json, "dumps", encode)
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.report(tracker, primary, Stream()) == 2
        assert tracker.failure is primary and primary.__cause__ is prior
        assert tracker.diagnostic_failures == [diagnostic]
    assert (
        calls == {"encoding": ["encoding"], "write": ["write"], "flush": ["write", "flush"]}[fault]
    )


@pytest.mark.parametrize("where", ["returned", "primary", "cleanup-only"])
def test_given_resource_owner_when_unwinding_then_phase_and_all_errors(where):
    from niri_desktop_continuity import restore_disposition_failure as failures
    from niri_desktop_continuity.restore_exited_resources import resources

    primary, prior = ValueError(SECRET), OSError("prior")
    primary.__cause__ = prior
    cleanups = [KeyboardInterrupt("first"), SystemExit(17)]
    events = []

    def close(i):
        events.append(i)
        raise cleanups[i]

    with failures.invocation() as tracker:
        try:
            with resources() as stack:
                stack.callback(close, 0)
                stack.callback(close, 1)
                with failures.phase("history"):
                    if where == "primary":
                        raise primary
                if where == "returned":
                    raise primary
        except BaseException as observed:
            assert events == [1, 0]
            present = {id(e) for e in objects(observed)}
            assert present >= {id(e) for e in cleanups}
            if where != "cleanup-only":
                assert observed is primary and id(prior) in present
            status, body = failures.projection(tracker, observed)
            assert status == 130 and body["diagnostic"]["cleanup_failure"] is True
            assert body["diagnostic"]["phase"] == (
                "cleanup" if where == "cleanup-only" else "history"
            )
            assert body["diagnostic"]["phase_state"] == (
                "returned" if where == "returned" else "entered"
            )
        else:
            pytest.fail("cleanup faults were not reached")
        stack.close()
        assert events == [1, 0]  # No repeat on retired owners.


@pytest.mark.parametrize(
    "options",
    [
        {"_preserve_disposition_failures": 1},
        {"_preserve_disposition_failures": None},
        {"_preserve_disposition_failures": True},
        {"_preserve_disposition_failures": True, "effectful": False},
    ],
)
def test_given_invalid_lock_opt_in_when_requested_then_refuse_before_acquisition(
    options, monkeypatch
):
    def unexpected():
        pytest.fail("invalid opt-in reached runtime directory")

    monkeypatch.setattr(locks, "runtime_root", unexpected)
    with pytest.raises(ValueError):
        with locks.operation_lock({}, **options):
            pytest.fail("invalid opt-in yielded")


def test_given_default_lock_when_body_and_close_fail_then_legacy_behavior(tmp_path, monkeypatch):
    identity = lock_fixture(tmp_path, monkeypatch)
    primary, cleanup = ValueError("legacy-body"), OSError("legacy-close")
    real_close = os.close
    closed = []

    def close(fd):
        closed.append(fd)
        real_close(fd)
        raise cleanup

    monkeypatch.setattr(locks.os, "close", close)
    with pytest.raises(OSError) as caught:
        with locks.operation_lock(identity, effectful=False, existing_only=True):
            raise primary
    assert caught.value is cleanup and len(closed) == 1
    assert (
        inspect.signature(locks.operation_lock).parameters["_preserve_disposition_failures"].default
        is False
    )


def test_given_reader_when_both_cache_retirements_fail_then_all_objects_once():
    from niri_desktop_continuity.restore_reader import DependencyReader

    reader = DependencyReader()
    failures, calls = [OSError("raw-cache"), SystemExit(0)], []

    class Cache(dict):
        def __init__(self, index):
            super().__init__()
            self.index = index

        def clear(self):
            calls.append(self.index)
            raise failures[self.index]

    reader.cache, reader.parsed = Cache(0), Cache(1)
    with pytest.raises(BaseExceptionGroup) as caught:
        reader.close()
    assert caught.value.exceptions == tuple(failures)
    assert calls == [0, 1] and reader.closed
    reader.close()
    assert calls == [0, 1]


def test_given_shadowed_exception_properties_when_projected_then_actual_slots_and_closed_reason():
    from niri_desktop_continuity import restore_disposition_failure as failures

    class Exit(SystemExit):
        @property
        def code(self):
            raise RuntimeError(SECRET)

        @property
        def __cause__(self):
            raise RuntimeError(SECRET)

    class Group(BaseExceptionGroup):
        @property
        def exceptions(self):
            raise RuntimeError(SECRET)

    exit_error = Exit(19)
    group = Group(SECRET, [exit_error])
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.projection(tracker, group)[0] == 19
    actual_prior = KeyboardInterrupt(SECRET)
    BaseException.__cause__.__set__(exit_error, actual_prior)
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.projection(tracker, group)[0] == 130

    class HiddenClass(Exception):
        @property
        def __class__(self):
            raise RuntimeError(SECRET)

    hidden = HiddenClass(SECRET)
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.projection(tracker, hidden)[0] == 1

    corrupted = failures.Refusal("invalid-arguments")
    corrupted.reason = SECRET
    with failures.invocation() as tracker:
        tracker.enter("history")
        status, value = failures.projection(tracker, corrupted)
        assert status == 1 and value["diagnostic"]["reason"] == "unexpected"
        assert SECRET not in json.dumps(value)


@pytest.mark.parametrize("multiple", [False, True])
def test_given_reserved_file_when_cleanup_only_then_sole_or_group_identity(
    tmp_path, monkeypatch, multiple
):
    tmp_path.chmod(0o700)
    path = tmp_path / "evidence"
    path.write_bytes(b"fabricated")
    path.chmod(0o600)
    reservation = bounded.identity(path)
    failures = [KeyboardInterrupt("file-close"), SystemExit(19)]
    real_close = os.close
    closed = []

    def close(fd):
        real_close(fd)
        closed.append(fd)
        if len(closed) == 1 or multiple:
            raise failures[len(closed) - 1]

    monkeypatch.setattr(bounded.os, "close", close)
    with pytest.raises(BaseException) as caught:
        bounded.raw(path, reservation, Counters())
    if multiple:
        assert isinstance(caught.value, BaseExceptionGroup)
        assert caught.value.exceptions == tuple(failures)
    else:
        assert caught.value is failures[0]
    assert len(closed) == 2


def test_given_primary_when_projection_construction_fails_then_chosen_exit_retained(monkeypatch):
    from niri_desktop_continuity import restore_disposition_failure as failures

    primary, diagnostic = KeyboardInterrupt(SECRET), OSError("projection")

    def fail(*args):
        raise diagnostic

    monkeypatch.setattr(failures, "projection", fail)
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.report(tracker, primary, None) == 130
        assert tracker.failure is primary
        assert tracker.diagnostic_failures == [diagnostic]


def test_given_cyclic_causes_and_implicit_context_when_projected_then_identity_walk_only():
    from niri_desktop_continuity import restore_disposition_failure as failures

    primary, prior = OSError("primary"), ValueError("prior")
    primary.__cause__, prior.__cause__ = prior, primary
    primary.__context__ = KeyboardInterrupt("not-authoritative")
    with failures.invocation() as tracker:
        tracker.enter("history")
        assert failures.projection(tracker, primary)[0] == 2
        assert {id(e) for e in failures.failure_objects(primary)} == {id(primary), id(prior)}


def test_given_lock_when_close_reuses_number_then_retired_owner_never_recloses(
    tmp_path, monkeypatch
):
    identity = lock_fixture(tmp_path, monkeypatch)
    primary, cleanup = ValueError("primary"), SystemExit(0)
    real_close = os.close
    calls, replacement = [], []
    replacement_path = tmp_path / "replacement"
    replacement_path.write_bytes(b"fabricated replacement")
    replacement_path.chmod(0o600)

    def close(fd):
        calls.append(fd)
        real_close(fd)
        new = os.open(replacement_path, os.O_RDONLY | os.O_CLOEXEC)
        replacement.append(new)
        assert new == fd
        raise cleanup

    monkeypatch.setattr(locks.os, "close", close)
    manager = locks.operation_lock(
        identity, effectful=False, existing_only=True, _preserve_disposition_failures=True
    )
    try:
        with pytest.raises(ValueError) as caught:
            with manager:
                raise primary
        assert caught.value is primary
        assert cleanup in list(objects(primary))
        assert len(calls) == len(replacement) == 1
        assert os.read(replacement[0], 100) == b"fabricated replacement"
        assert os.fstat(replacement[0]).st_ino == replacement_path.stat().st_ino
    finally:
        for fd in replacement:
            real_close(fd)
