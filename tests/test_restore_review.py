"""Handwritten review counterexamples: raw evidence, strict frames and bounded FIFO admission."""

import os
import socket
import struct
import threading
import time

import pytest

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity import restore_producer as producer
from niri_desktop_continuity import restore_wire as wire

DESIRED_ENV = {
    "NIRI_SOCKET": "/fabricated/niri.sock",
    "XDG_RUNTIME_DIR": "/fabricated/runtime",
    "WAYLAND_DISPLAY": "fabricated-wayland",
    "GDK_BACKEND": "wayland",
    "NORMAL_SETTING": "literal $HOME",
}


def encoded(env):
    return b"".join(f"{key}={value}".encode() + b"\0" for key, value in env.items())


class ObservedProcess(host.Process):
    """Replace proc byte acquisition, NOT the production environment decoder/comparison."""

    def __init__(self, raw):
        self.raw = raw

    def read(self, name):
        assert name == "environ"
        return self.raw

    def validate(self, expected, **kwargs):
        assert expected == {"fabricated": "image"}

    def argv(self):
        return ["fabricated-host"]


@pytest.mark.parametrize(
    "change",
    [
        {"GDK_BACKEND": "x11"},
        {"WAYLAND_SOCKET": "77"},
        {"LISTEN_FDS": "1"},
        {"NOTIFY_SOCKET": "/fabricated/control"},
        {"WATCHDOG_PID": "42"},
        {"NDC_CONTROL_SOCKET": "fabricated"},
    ],
)
def test_proof_rejects_raw_backend_or_forbidden_additions(monkeypatch, change):
    monkeypatch.setattr(host, "route", lambda identity: None)
    observed = ObservedProcess(encoded({**DESIRED_ENV, **change}))
    monkeypatch.setattr(producer.LaunchProof, "validate_cwd", lambda *args: None)
    proof = producer.LaunchProof(
        observed,
        {"fabricated": "image"},
        {"argv": ["fabricated-host"]},
        dict(DESIRED_ENV),
        {},
        None,
        {},  # cwd is independently exercised by the real producer/handshake tests
        None,
    )
    with pytest.raises(ValueError, match="environment"):
        proof.validate()
    assert proof.invalid


def test_raw_environment_is_not_rewritten_into_desired_evidence():
    raw = {**DESIRED_ENV, "GDK_BACKEND": "x11", "WAYLAND_SOCKET": "77"}
    process = ObservedProcess(encoded(raw))
    assert process.environment() == raw
    assert host.environment(process.environment()) == DESIRED_ENV


def test_exact_raw_environment_proof_positive(monkeypatch):
    monkeypatch.setattr(host, "route", lambda identity: None)
    monkeypatch.setattr(producer.LaunchProof, "validate_cwd", lambda *args: None)
    proof = producer.LaunchProof(
        ObservedProcess(encoded(DESIRED_ENV)),
        {"fabricated": "image"},
        {"argv": ["fabricated-host"]},
        dict(DESIRED_ENV),
        {},
        None,
        {},  # cwd is independently exercised by the real producer/handshake tests
        None,
    )
    proof.validate()
    assert not proof.invalid


@pytest.mark.parametrize(
    "raw",
    [
        encoded(DESIRED_ENV)[:-1],
        encoded(DESIRED_ENV) + b"\0",
        encoded(DESIRED_ENV) + b"GDK_BACKEND=x11\0",
        b"=value\0",
        b"missing-separator\0",
    ],
)
def test_raw_environment_structure_is_closed(raw):
    with pytest.raises(ValueError):
        ObservedProcess(raw).environment()


@pytest.mark.parametrize(
    "body",
    [b'{"x":1e999}', b'{"x":{"y":-1e999}}', b'{"x":[0,{"y":1e999}]}'],
)
def test_wire_rejects_overflow_nonfinite_at_any_depth(body):
    left, right = socket.socketpair()
    with left, right:
        left.sendall(struct.pack("!I", len(body)) + body)
        with pytest.raises(ValueError, match="nonfinite"):
            wire.receive(right, time.monotonic() + 1)


def test_wire_preserves_finite_float_values():
    left, right = socket.socketpair()
    with left, right:
        body = b'{"x":[1e308,-0.5]}'
        left.sendall(struct.pack("!I", len(body)) + body)
        assert wire.receive(right, time.monotonic() + 1) == {"x": [1e308, -0.5]}


@pytest.mark.parametrize("entry", ["image", "producer"])
def test_fifo_no_writer_refuses_promptly_without_dispatch(tmp_path, monkeypatch, entry):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(host, "route", lambda identity: None)
    fifo = tmp_path / "ghostty"
    os.mkfifo(fifo, 0o700)
    identity = {"boot_id": "fabricated", "socket_device": 1, "socket_inode": 2}
    calls, outcome = [], []
    started, finished = threading.Event(), threading.Event()
    original_open = os.open

    def opening(path, flags, *args, **kwargs):
        if os.fspath(path) == str(fifo):
            started.set()
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opening)

    class Store:
        def get(self, kind, key):
            assert (kind, key) == ("snapshots", "fabricated")
            return {}

    def invoke():
        try:
            if entry == "image":
                with host.Image(str(fifo)):
                    pytest.fail("FIFO admitted as an image")
            else:
                producer.produce(
                    Store(),
                    "fabricated",
                    {"kind": "shell", "argv": [str(fifo)], "cwd": str(tmp_path)},
                    identity,
                    timeout=5,
                    dispatch=lambda *args: calls.append(args),
                )
        except BaseException as error:
            outcome.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    try:
        assert started.wait(2), "probe did not reach FIFO open"
        prompt = finished.wait(0.25)  # No writer exists during the measured refusal interval.
    finally:
        # Only on RED: unblock our own FIFO reader to avoid leaving an active test thread.
        # No child/process is killed. GREEN never opens a writer at all.
        if worker.is_alive():
            release = original_open(fifo, os.O_RDWR | os.O_NONBLOCK)
            try:
                worker.join(2)
            finally:
                os.close(release)
        else:
            worker.join()
    assert not worker.is_alive()
    assert calls == [] and not producer.fence_path(identity).exists()
    assert len(outcome) == 1 and isinstance(outcome[0], ValueError)
    assert prompt, "FIFO admission blocked waiting for a writer"


def test_expiry_during_image_read_stops_before_intent_or_dispatch(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(host, "route", lambda identity: None)
    executable = tmp_path / "ghostty"
    executable.write_bytes(b"\x7fELF" + b"fabricated, never executed" * 100)
    executable.chmod(0o700)
    clock = [10.0]
    monkeypatch.setattr(wire.time, "monotonic", lambda: clock[0])
    read = os.pread

    def expired_read(*args):
        result = read(*args)
        clock[0] = 20.0
        return result

    monkeypatch.setattr(os, "pread", expired_read)
    calls = []

    class Store:
        root = tmp_path / "state"

        def get(self, kind, key):
            return {}

        def put(self, kind, value):
            calls.append("receipt")
            return "a" * 64

    identity = {"boot_id": "fabricated", "socket_device": 1, "socket_inode": 2}
    with pytest.raises(TimeoutError):
        producer.produce(
            Store(),
            "fabricated",
            {"kind": "shell", "argv": [str(executable)], "cwd": str(tmp_path)},
            identity,
            timeout=1,
            dispatch=lambda *args: calls.append("dispatch"),
        )
    assert calls == []
    assert not producer.fence_path(identity).exists()
