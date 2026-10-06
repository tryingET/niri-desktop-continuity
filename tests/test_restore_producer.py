"""Launch producer contracts; fabricated IPC/processes only, no native applications."""

import importlib
import os
import socket
import struct
import sys
import time
from pathlib import Path

import pytest


def module(name):
    return importlib.import_module(f"niri_desktop_continuity.restore_{name}")


def recipe(tmp_path, *, kind="command", flags=(), tail=("tool", "a b", "$HOME")):
    return {
        "kind": kind,
        "argv": [str(tmp_path / "ghostty"), *flags, *(["-e", *tail] if tail else [])],
        "cwd": str(tmp_path),
    }


@pytest.mark.parametrize("kind", ["shell", "command", "declared", "pi", "claude"])
def test_controlled_host_preserves_literal_command_and_existing_directory(tmp_path, kind):
    host = module("host")
    tail = () if kind == "shell" else ("tool", "a b", "$HOME", "--config-file=literal")
    result = host.admit(recipe(tmp_path, kind=kind, tail=tail))
    assert result == {
        "argv": [
            str(tmp_path / "ghostty"),
            "--config-default-files=false",
            "--gtk-single-instance=false",
            "--initial-window=true",
            f"--working-directory={tmp_path}",
            *(["-e", *tail] if tail else []),
        ],
        "cwd": str(tmp_path),
    }


@pytest.mark.parametrize(
    "flags", [("--config-file=private",), ("--gtk-single-instance=true",), ("+new-window",)]
)
def test_conflicting_host_semantics_refused(tmp_path, flags):
    with pytest.raises(ValueError):
        module("host").admit(recipe(tmp_path, flags=flags))


def test_missing_directory_and_arbitrary_apps_refused(tmp_path):
    host = module("host")
    value = recipe(tmp_path)
    value["cwd"] = str(tmp_path / "absent")
    with pytest.raises(ValueError):
        host.admit(value)
    with pytest.raises(ValueError):
        host.admit(recipe(tmp_path, kind="app"))


def test_environment_is_explicitly_wayland_without_service_control_fds():
    env = module("host").environment(
        {
            "NIRI_SOCKET": "/fabricated/niri.sock",
            "WAYLAND_DISPLAY": "wayland-test",
            "XDG_RUNTIME_DIR": "/fabricated/runtime",
            "WAYLAND_SOCKET": "41",
            "GDK_BACKEND": "x11,wayland",
            "LISTEN_FDS": "2",
            "LISTEN_PID": "5",
            "NOTIFY_SOCKET": "/fabricated/notify",
            "INVOCATION_ID": "old",
            "CREDENTIALS_DIRECTORY": "/fabricated/credentials",
            "CONTROL_PID": "321",
            "XDG_ACTIVATION_TOKEN": "stale",
            "NORMAL_USER_SETTING": "literal",
        }
    )
    assert env == {
        "NIRI_SOCKET": "/fabricated/niri.sock",
        "WAYLAND_DISPLAY": "wayland-test",
        "XDG_RUNTIME_DIR": "/fabricated/runtime",
        "GDK_BACKEND": "wayland",
        "NORMAL_USER_SETTING": "literal",
    }


def test_wire_complete_frame_and_absolute_deadline():
    wire = module("wire")
    left, right = socket.socketpair()
    with left, right:
        deadline = time.monotonic() + 1
        wire.send(left, {"type": "hello", "nonce": "fabricated"}, deadline)
        assert wire.receive(right, deadline) == {"type": "hello", "nonce": "fabricated"}
        with pytest.raises(TimeoutError):
            wire.receive(right, time.monotonic() - 1)


def test_wire_partial_eof_is_not_a_permit():
    wire = module("wire")
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b'\x00\x00\x00\x20{"type":"exec"')
        left.shutdown(socket.SHUT_WR)
        with pytest.raises((ValueError, EOFError)):
            wire.receive(right, time.monotonic() + 1)


def test_pidfd_process_pin_and_running_image_are_independent():
    host = module("host")
    with host.Image(str(Path(sys.executable).resolve())) as image:
        with host.Process(os.getpid()) as process:
            process.validate(image.pin)
            assert process.pin["pid"] == os.getpid()
            with pytest.raises(ValueError):
                process.validate({**image.pin, "inode": image.pin["inode"] + 1})


@pytest.mark.parametrize("body", [b'{"type":"hello","type":"exec"}', b'{"x":NaN}', b"[]"])
def test_wire_rejects_nonclosed_json(body):
    wire = module("wire")
    left, right = socket.socketpair()
    with left, right:
        left.sendall(struct.pack("!I", len(body)) + body)
        with pytest.raises(ValueError):
            wire.receive(right, time.monotonic() + 1)


def test_wire_rejects_oversize_without_reading_body():
    wire = module("wire")
    left, right = socket.socketpair()
    with left, right:
        left.sendall(struct.pack("!I", wire.MAX_FRAME + 1))
        with pytest.raises(ValueError, match="size"):
            wire.receive(right, time.monotonic() + 1)


def test_complete_frame_arriving_after_deadline_is_refused(monkeypatch):
    wire = module("wire")
    clock = [10.0]
    monkeypatch.setattr(wire.time, "monotonic", lambda: clock[0])

    class Trickle:
        data = struct.pack("!I", 2) + b"{}"

        def settimeout(self, value):
            assert value > 0

        def recv(self, size):
            part, self.data = self.data[:size], self.data[size:]
            if not self.data:
                clock[0] = 12.0
            return part

    with pytest.raises(TimeoutError):
        wire.receive(Trickle(), 11.0)


@pytest.mark.parametrize("pid,uid,expected", [(12, -1, None), (0, None, None), (12, None, 13)])
def test_peer_credentials_not_nonce_or_pid_guess(pid, uid, expected):
    class Peer:
        def getsockopt(self, *args):
            return struct.pack("3i", pid, os.getuid() if uid is None else uid, os.getgid())

    with pytest.raises(ValueError, match="credentials"):
        module("wire").peer_pid(Peer(), expected)


def test_process_start_change_is_permanent_even_with_same_pid(monkeypatch):
    host = module("host")
    with host.Process(os.getpid()) as process:
        original = dict(process.pin)
        monkeypatch.setattr(host, "process_pin", lambda pid: {**original, "start_ticks": -1})
        with pytest.raises(ValueError, match="identity ended"):
            process.live()
        monkeypatch.setattr(host, "process_pin", lambda pid: original)
        with pytest.raises(ValueError):
            process.live()


def test_script_wrapper_and_symlink_executable_refused(tmp_path):
    host = module("host")
    script = tmp_path / "ghostty"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o700)
    with pytest.raises(ValueError, match="ELF"):
        host.Image(str(script))
    link = tmp_path / "linked"
    link.symlink_to(Path(sys.executable).resolve())
    with pytest.raises(OSError):
        host.Image(str(link))


def test_niri_dispatch_route_and_descriptor_boundary(monkeypatch):
    producer = module("producer")
    calls, routes = [], []
    identity = {"niri_socket": "/fabricated/niri.sock"}
    monkeypatch.setattr(producer.host, "route", lambda value: routes.append(value))
    waits = []

    class Client:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def wait(self, *, timeout):
            waits.append(timeout)
            return 0

    monkeypatch.setattr(producer.subprocess, "Popen", Client)
    producer.niri_spawn(
        ["fabricated-python", "-I", "-m", "fabricated"], identity, time.monotonic() + 1
    )
    assert routes == [identity, identity]
    argv, options = calls[0]
    assert argv[0] == [
        "niri",
        "msg",
        "action",
        "spawn",
        "--",
        "fabricated-python",
        "-I",
        "-m",
        "fabricated",
    ]
    assert options["close_fds"] is True
    assert options["env"]["NIRI_SOCKET"] == identity["niri_socket"]
    assert len(waits) == 1 and 0 < waits[0] <= 1


def test_niri_client_timeout_does_not_kill_or_retry(monkeypatch):
    producer = module("producer")
    calls = []
    monkeypatch.setattr(producer.host, "route", lambda value: None)

    class Client:
        def __init__(self, *args, **kwargs):
            calls.append(args)

        def wait(self, *, timeout):
            raise producer.subprocess.TimeoutExpired("fabricated-ipc-client", timeout)

        def kill(self):
            pytest.fail("IPC client must not be killed on ambiguous dispatch")

        terminate = kill

    monkeypatch.setattr(producer.subprocess, "Popen", Client)
    with pytest.raises(producer.subprocess.TimeoutExpired):
        producer.niri_spawn(["fabricated"], {"niri_socket": "/fabricated"}, time.monotonic() + 1)
    assert len(calls) == 1


@pytest.mark.parametrize("budget,expected", [(0.5, 0.5), (25, 10)])
def test_association_query_uses_remaining_budget_capped_at_ipc_limit(monkeypatch, budget, expected):
    from niri_desktop_continuity import restore

    clock, waits = [10.0], []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    class Client:
        returncode = 0

        def __init__(self, *args, **kwargs):
            assert kwargs["close_fds"]

        def communicate(self, *, timeout):
            waits.append(timeout)
            return "[]", None

        def kill(self):
            pytest.fail("no query timeout termination")

        terminate = kill

    monkeypatch.setattr(restore.subprocess, "Popen", Client)
    assert restore.LiveDesktop().windows(deadline=10 + budget) == []
    assert waits == [expected]


def test_association_query_late_reply_refused_without_kill(monkeypatch):
    from niri_desktop_continuity import restore

    clock = [10.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    class Client:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, *, timeout):
            clock[0] = 12.0
            return "[]", None

        def kill(self):
            pytest.fail("no query timeout termination")

        terminate = kill

    monkeypatch.setattr(restore.subprocess, "Popen", Client)
    with pytest.raises(TimeoutError):
        restore.LiveDesktop().workspaces(deadline=11)


@pytest.mark.parametrize("fault", [OSError, KeyboardInterrupt, SystemExit])
def test_attempt_all_proofs_and_lock_close_after_first_failure(tmp_path, fault):
    from types import SimpleNamespace

    from niri_desktop_continuity.restore_attempt import Attempt

    producer = module("producer")
    closed, proofs = [], []
    error = fault("fabricated process close failure")

    def fail():
        closed.append("first")
        raise error

    for close in (fail, lambda: closed.append("second")):
        fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        proofs.append(
            producer.LaunchProof(SimpleNamespace(close=close), None, {}, None, None, None, {}, fd)
        )
    attempt = Attempt(None, None, {})
    attempt.proofs = proofs
    attempt.lock = SimpleNamespace(__exit__=lambda *args: closed.append("lock"))
    with pytest.raises(fault) as raised:
        attempt.__exit__(None, None, None)
    assert raised.value is error
    assert closed == ["first", "second", "lock"]
    assert all(p.cwd_fd is None for p in proofs)
    assert not attempt.active and attempt.poisoned


def test_attempt_preserves_body_and_multiple_cleanup_failures():
    from types import SimpleNamespace

    from niri_desktop_continuity.restore_attempt import Attempt

    body, first, second, lock = (
        ValueError("body"),
        OSError("first"),
        KeyboardInterrupt(),
        OSError("lock"),
    )

    def fail(error):
        raise error

    attempt = Attempt(None, None, {})
    attempt.proofs = [
        SimpleNamespace(close=lambda: fail(first)),
        SimpleNamespace(close=lambda: fail(second)),
    ]
    attempt.lock = SimpleNamespace(__exit__=lambda *args: fail(lock))
    with pytest.raises(BaseExceptionGroup) as raised:
        attempt.__exit__(type(body), body, None)
    assert raised.value.exceptions == (body, first, second, lock)


def test_attempt_successful_cleanup_does_not_suppress_original_exception():
    from types import SimpleNamespace

    from niri_desktop_continuity.restore_attempt import Attempt

    body = KeyboardInterrupt("body")
    attempt = Attempt(None, None, {})
    args = []
    attempt.lock = SimpleNamespace(__exit__=lambda *values: args.append(values))
    assert attempt.__exit__(type(body), body, None) is None
    assert args == [(type(body), body, None)]
