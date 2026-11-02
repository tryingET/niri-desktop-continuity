"""Niri reads and the compositor identity behind every writer lock, with fabricated sockets only."""

import os
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from niri_desktop_continuity import probe
from niri_desktop_continuity.model import readiness


@pytest.fixture
def niri_socket(tmp_path, monkeypatch):
    # Bound relatively: tmp_path carries the test name and AF_UNIX paths stop at 108 bytes.
    monkeypatch.chdir(tmp_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind("n.sock")
        monkeypatch.setenv("NIRI_SOCKET", str(tmp_path / "n.sock"))
        yield tmp_path / "n.sock"


def test_identity_pins_boot_path_inode_and_device_of_the_socket(niri_socket):
    info = os.stat(niri_socket)
    assert probe.compositor_identity() == {
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "niri_socket": str(niri_socket),
        "socket_inode": info.st_ino,
        "socket_device": info.st_dev,
    }


def test_identity_is_unavailable_without_a_socket_variable(monkeypatch):
    monkeypatch.delenv("NIRI_SOCKET", raising=False)
    with pytest.raises(ValueError, match="NIRI_SOCKET unavailable"):
        probe.compositor_identity()


def test_identity_refuses_a_path_that_is_not_a_socket(tmp_path, monkeypatch):
    path = tmp_path / "plain"
    path.write_text("")
    monkeypatch.setenv("NIRI_SOCKET", str(path))
    with pytest.raises(ValueError, match="must belong to the current user"):
        probe.compositor_identity()


def test_identity_refuses_a_socket_of_another_user(niri_socket, monkeypatch):
    monkeypatch.setattr(probe.os, "getuid", lambda: os.stat(niri_socket).st_uid + 1)
    with pytest.raises(ValueError, match="must belong to the current user"):
        probe.compositor_identity()


def test_identity_of_a_vanished_socket_is_an_error_not_an_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("NIRI_SOCKET", str(tmp_path / "gone"))
    with pytest.raises(FileNotFoundError):
        probe.compositor_identity()


def reply(monkeypatch, stdout):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


@pytest.mark.parametrize("command", ["outputs", "windows", "workspaces", "layers", "version"])
def test_query_runs_one_bounded_read(monkeypatch, command):
    calls = reply(monkeypatch, '[{"id": 1}]')
    assert probe.Niri().query(command) == [{"id": 1}]
    assert calls == [
        (
            ["niri", "msg", "--json", command],
            {"capture_output": True, "text": True, "timeout": 10, "check": True},
        )
    ]


@pytest.mark.parametrize("command", ["action", "spawn", "Windows", "", "--json"])
def test_query_refuses_anything_but_the_read_commands(monkeypatch, command):
    calls = reply(monkeypatch, "[]")
    with pytest.raises(ValueError, match="not an admitted read-only"):
        probe.Niri().query(command)
    assert calls == []


def test_query_refuses_a_reply_over_the_bound_before_parsing(monkeypatch):
    reply(monkeypatch, "[" + " " * (8 * 1024 * 1024) + "]")
    with pytest.raises(ValueError, match="exceeds observation bound"):
        probe.Niri().query("windows")


def test_query_accepts_a_reply_at_the_bound(monkeypatch):
    reply(monkeypatch, "[" + " " * (8 * 1024 * 1024 - 2) + "]")
    assert probe.Niri().query("windows") == []


def test_a_desktop_without_an_active_workspace_is_not_ready():
    snapshot = {
        "outputs": [{"name": "DP-1", "logical": {"w": 1}, "current_mode": 0}],
        "workspaces": [{"id": 1, "output": "DP-1"}],
        "windows": [],
        "coherent": True,
    }
    assert readiness(snapshot) == {"ready": False, "reasons": ["no-active-workspace"]}
