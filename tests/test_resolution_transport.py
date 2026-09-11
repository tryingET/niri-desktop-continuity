"""Fabricated socket transport and isolated child lock-boundary tests; no native invocation."""

import os
import socket
import sys
import threading
from pathlib import Path
from subprocess import PIPE, Popen

import pytest
from test_resolution_fixtures import approved, candidate, packet
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401

from niri_desktop_continuity import (
    recovery_transition,
    resolution_candidate,
    resolution_graph,
    resolution_observer,
)
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_profile import profile_path as account_profile_path
from niri_desktop_continuity.recovery_protocol import decode_frame, encode
from niri_desktop_continuity.resolution_evidence import PROTOCOL


@pytest.mark.parametrize(
    "frame_kind", ["result", "heartbeat", "effect", "effect-result", "wrong-binding", "trailing"]
)
def test_observer_only_heartbeat_and_result_never_effect_permits(
    resolution, monkeypatch, frame_kind
):
    key, value = candidate(resolution)
    resolution_candidate.approve(key, key, "resolution-observe-only")
    graph = resolution_graph.initial(value)
    observed = []
    waited = []

    def popen(argv, **kwargs):
        assert argv == [
            value["observer"]["interpreter"]["path"],
            "-I",
            "-S",
            value["observer"]["endpoint"]["path"],
        ]
        assert set(kwargs["env"]) == {"NDC_RESOLUTION_FD"}
        fd = int(kwargs["env"]["NDC_RESOLUTION_FD"])
        assert kwargs["pass_fds"] == (fd,) and kwargs["close_fds"] is True
        sock = socket.socket(fileno=os.dup(fd))
        sock.settimeout(2)

        def worker():
            try:
                with sock, sock.makefile("rb") as stream:
                    request = decode_frame(stream.readline())
                    assert request == {
                        "protocol": PROTOCOL,
                        "candidate_digest": key,
                        "graph_digest": digest(graph),
                        "phase": "observe-settlement",
                        "expires_at": value["expires_at"],
                    }
                    envelope = {
                        "protocol": PROTOCOL,
                        "request_digest": digest(request),
                        "type": frame_kind,
                        "body": {},
                    }
                    if frame_kind == "heartbeat":
                        sock.sendall(encode(envelope))
                        reply = decode_frame(stream.readline())
                        observed.append(reply)
                        assert reply["type"] == "continue" and reply["body"] == {}
                    if frame_kind in ("result", "heartbeat", "wrong-binding", "trailing"):
                        envelope.update(type="result", body=packet(value, digest(graph)))
                    if frame_kind == "wrong-binding":
                        envelope["request_digest"] = "0" * 64
                    sock.sendall(encode(envelope))
                    if frame_kind == "trailing":
                        sock.sendall(b"x")
            except (OSError, ValueError):
                pass

        thread = threading.Thread(target=worker)
        thread.start()

        class Child:
            def wait(self):
                waited.append(True)
                thread.join()
                return 0

        return Child()

    monkeypatch.setattr("subprocess.Popen", popen)
    if frame_kind in ("result", "heartbeat"):
        result = resolution_observer.observe(key, digest(graph))
        assert result["schema"] == "desktop-continuity.settlement-packet.v1"
    else:
        with pytest.raises(ValueError):
            resolution_observer.observe(key, digest(graph))
    assert waited and all(v["type"] == "continue" for v in observed)


def test_isolated_child_reads_edge_under_parent_locks_without_reacquiring(resolution, monkeypatch):
    import json

    from niri_desktop_continuity.resolution_lock import owner_guard

    approval, _ = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    # Real exec, not fork-inherited ContextVar state or the thread-backed double.
    # Explicit scratch profile injection exists only in this test program.
    program = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from niri_desktop_continuity import recovery_profile, recovery_resolution
from niri_desktop_continuity.resolution_lock import owner_guard
recovery_profile.profile_path = lambda: Path(sys.argv[2])
profile = recovery_profile.identify_profile()
edge = recovery_resolution.legacy_disposition(profile, sys.argv[3], sys.argv[4], 'indeterminate')
# Nonblocking kernel flock makes either child reacquisition a contract error.
for operation in ('guard', 'load'):
    try:
        if operation == 'guard':
            with owner_guard():
                raise AssertionError('child acquired parent lock')
        else:
            recovery_profile.load_profile()
    except BlockingIOError:
        pass
    else:
        raise AssertionError('serialized child operation unexpectedly succeeded')
print(json.dumps(edge))
"""
    with owner_guard():
        with Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                program,
                str(Path(resolution_candidate.__file__).resolve().parents[1]),
                str(resolution["root"] / "profile.json"),
                str(resolution["worker"]),
                resolution["attempt"],
            ],
            cwd=resolution["root"],
            env={},
            close_fds=True,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
        ) as child:
            stdout, stderr = child.communicate()
            assert child.returncode == 0, stderr
    assert json.loads(stdout) == {
        "historical_status": "indeterminate",
        "resolution_disposition": "abandoned-settled",
        "accounted_settled": True,
        "replay_authorized": False,
    }
    # This proves the portable pure-read/lock boundary, NOT owner peer authentication.


def test_anchor_ignores_environment_and_caller_state_root(resolution, monkeypatch):
    from types import SimpleNamespace

    from niri_desktop_continuity import recovery_profile

    # Restore actual anchor implementation with a fabricated account lookup, not HOME.
    monkeypatch.setattr(
        recovery_profile.pwd, "getpwuid", lambda _: SimpleNamespace(pw_dir=str(resolution["root"]))
    )
    monkeypatch.setattr(recovery_profile, "profile_path", account_profile_path)
    monkeypatch.setenv("HOME", str(resolution["root"] / "untrusted"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(resolution["root"] / "untrusted"))
    assert (
        resolution_candidate.anchor("candidates", "a" * 64).parent
        == resolution["root"] / ".config/niri-desktop-continuity/recovery-candidates"
    )
