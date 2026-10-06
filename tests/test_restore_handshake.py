"""Real installed bootstrap, Unix credentials, pidfds and descriptor exec of a fabricated ELF.

The optional C compiler builds a tiny bounded test process, NOT Ghostty. Nothing connects to Niri.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_reopen import FakeDesktop, observation, saved

from niri_desktop_continuity import operation_lock, probe, restore
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_producer as producer
from niri_desktop_continuity import restore_wire as wire
from niri_desktop_continuity.store import Store


def journal_records(identity, store):
    return [
        (r, store.get("receipts", r["receipt"]))
        for r in [history.read(p) for p in sorted(producer.fence_path(identity).glob("*.json"))]
    ]


@pytest.fixture(scope="module")
def fabricated_elf(tmp_path_factory):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("real descriptor-exec fixture requires a local C compiler")
    directory = tmp_path_factory.mktemp("fabricated-elf")
    source = directory / "host.c"
    source.write_text(r"""
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
int main(int argc, char **argv) {
    char cwd[4096];
    FILE *out = fopen(getenv("NDC_TEST_REPORT"), "w");
    if (!out || !getcwd(cwd, sizeof cwd)) return 2;
    fprintf(out, "pid=%ld\ncwd=%s\nbackend=%s\nnormal=%s\n",
            (long)getpid(), cwd, getenv("GDK_BACKEND"), getenv("NORMAL_USER_SETTING"));
    for (int i = 0; i < argc; ++i) fprintf(out, "arg=%s\n", argv[i]);
    for (int i = 0; i < 1024; ++i)
        if (i != fileno(out) && fcntl(i, F_GETFD) != -1) fprintf(out, "fd=%d\n", i);
    fclose(out);
    char *quit = getenv("NDC_TEST_QUIT");
    if (quit) {
        for (int i = 0; i < 3000 && access(quit, F_OK); ++i) usleep(10000);
    } else {
        /* Cooperative cwd drift trigger, fabricated fixture only. */
        char trigger[4096], ack[4096];
        snprintf(trigger, sizeof trigger, "%s.chdir", getenv("NDC_TEST_REPORT"));
        snprintf(ack, sizeof ack, "%s.changed", getenv("NDC_TEST_REPORT"));
        for (int i = 0; i < 200; ++i) {
            if (!access(trigger, F_OK)) {
                if (chdir("/")) return 3;
                FILE *done = fopen(ack, "w");
                if (done) fclose(done);
            }
            usleep(10000);
        }
    } /* bounded autonomous exit; the test never kills it */
    return 0;
}
""")
    executable = directory / "ghostty"
    subprocess.run([compiler, str(source), "-o", str(executable)], check=True, close_fds=True)
    return executable


@pytest.fixture
def sandbox(tmp_path, monkeypatch, fabricated_elf):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)

    def forbidden(*args, **kwargs):
        pytest.fail("real Niri dispatch is forbidden in this test")

    monkeypatch.setattr(producer, "niri_spawn", forbidden)
    # A short path stays within sockaddr_un even under a long TMPDIR-aware pytest directory.
    with tempfile.TemporaryDirectory(prefix="ns-", dir=os.environ.get("TMPDIR")) as short:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as compositor:
            path = str(Path(short) / "niri.sock")
            compositor.bind(path)  # No listener, no requests, no real compositor.
            monkeypatch.setenv("NIRI_SOCKET", path)
            identity = probe.compositor_identity()
            store = Store(tmp_path / "state")
            key = store.put("snapshots", saved([]))
            report = tmp_path / "host-report"
            children, at_dispatch = [], []
            env = {
                "PATH": os.defpath,
                "HOME": str(tmp_path),
                "NIRI_SOCKET": path,
                "WAYLAND_DISPLAY": "fabricated-wayland",
                "XDG_RUNTIME_DIR": str(runtime),
                "NDC_TEST_REPORT": str(report),
                "NORMAL_USER_SETTING": "literal $HOME",
                "GDK_BACKEND": "x11",
                "WAYLAND_SOCKET": "77",
                "LISTEN_FDS": "2",
                "LISTEN_PID": "123",
                "NOTIFY_SOCKET": "fabricated",
            }

            def dispatch(argv, expected_identity, deadline):
                assert expected_identity == identity
                records = journal_records(identity, store)
                assert [r[0]["type"] for r in records] == ["prepared", "intent"]
                assert records[0][1]["snapshot_digest"] == key
                assert records[0][0]["origin"]["root"] == str(store.root)
                assert records[1][1]["action"] == "bootstrap"
                assert not any(p.get("action") == "exec" for _, p in records)
                at_dispatch.append(records)
                # Deliberately inherit an unrelated control descriptor; exec must close it.
                children.append(
                    subprocess.Popen(
                        argv,
                        env=env,
                        cwd=tmp_path,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        pass_fds=(compositor.fileno(),),
                    )
                )

            state = SimpleNamespace(
                store=store,
                key=key,
                identity=identity,
                report=report,
                children=children,
                dispatch=dispatch,
                at_dispatch=at_dispatch,
                runtime=runtime,
                recipe={
                    "kind": "command",
                    "argv": [str(fabricated_elf), "-e", "tool", "a b", "$HOME"],
                    "cwd": str(tmp_path),
                },
            )
            yield state
            for child in children:
                # The helper's absolute deadline and the fixture's own sleep bound their life.
                # No kill/terminate/context-manager timeout cleanup is permitted here.
                child.wait(timeout=10)
                child.stderr.close()


def launch(state, **kwargs):
    return producer.produce(
        state.store,
        state.key,
        state.recipe,
        state.identity,
        dispatch=state.dispatch,
        timeout=2,
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["shell", "command"])
def test_real_producer_same_process_exec_fd_closure_and_truthful_receipt(sandbox, kind):
    state = sandbox
    if kind == "shell":
        state.recipe = {**state.recipe, "kind": "shell", "argv": state.recipe["argv"][:1]}
    with launch(state) as proof:
        proof.validate()
        assert proof.process.pin["pid"] == state.children[0].pid
        deadline = time.monotonic() + 1
        while not state.report.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        lines = state.report.read_text().splitlines()
        assert f"pid={state.children[0].pid}" in lines
        assert f"cwd={state.recipe['cwd']}" in lines
        assert "backend=wayland" in lines and "normal=literal $HOME" in lines
        assert [line for line in lines if line.startswith("fd=")] == ["fd=0", "fd=1", "fd=2"]
        assert [line[4:] for line in lines if line.startswith("arg=")] == [
            state.recipe["argv"][0],
            "--config-default-files=false",
            "--gtk-single-instance=false",
            "--initial-window=true",
            f"--working-directory={state.recipe['cwd']}",
            *(["-e", "tool", "a b", "$HOME"] if kind == "command" else []),
        ]
        receipt = state.store.get("receipts", proof.receipt)
        assert receipt["phase"] == "process-observed" and receipt["ownership"] == "process-only"
        assert receipt["window_ownership"] == "not-proved"
        assert receipt["placement"] == "not-attempted" and receipt["native_session"] == "not-proved"
        assert receipt["settlement"] == "unresolved"
        assert "NORMAL_USER_SETTING" not in json.dumps(receipt)
        assert state.store.pointer("last-reopened") is None
        permits = [
            p for _, p in journal_records(state.identity, state.store) if p.get("action") == "exec"
        ]
        assert len(permits) == 1
        # Exited pidfd proof is permanently invalid, not restored by a recycled PID number.
        state.children[0].wait(timeout=5)
        with pytest.raises(ValueError):
            proof.validate()
        with pytest.raises(ValueError, match="invalidated"):
            proof.validate()


def test_cross_store_and_cross_snapshot_fence_but_dry_run_remains_zero_effect(sandbox, tmp_path):
    state = sandbox
    with launch(state):
        pass
    other = Store(tmp_path / "other")
    other_key = other.put("snapshots", {**saved([]), "fabricated": "different"})
    calls = []
    with pytest.raises(ValueError, match="unresolved restore"):
        producer.produce(
            other, other_key, state.recipe, state.identity, dispatch=lambda *a: calls.append(a)
        )
    assert calls == []
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(state.identity):
            pytest.fail("shared reconcile/recovery writer admission bypassed fence")
    desktop = FakeDesktop([])
    result = restore.restore(other, other_key, desktop, apply=False, observe=observation(desktop))
    assert result["status"] == "dry-run" and desktop.actions == []
    with operation_lock.operation_lock({**state.identity, "socket_inode": 999999}):
        pass  # A genuinely different compositor has a separate identity.


@pytest.mark.parametrize(
    "failure", ["partial", "wrong-binding", "after-delivery", "no-permit", "deadline"]
)
def test_permit_failure_is_never_automatic_settlement(sandbox, monkeypatch, failure):
    original = wire.send
    state = sandbox

    def send(connection, value, deadline, check=lambda: None):
        if value.get("type") != "exec":
            return original(connection, value, deadline, check)
        # Inspect durable accounting before ANY permit bytes, without producer helper expectations.
        marker = journal_records(state.identity, state.store)[-1][1]
        assert marker["action"] == "exec" and marker["details"]["binding"] == value["binding"]
        if failure == "partial":
            connection.sendall(b'\x00\x00\x00\x40{"type":"exec"')
        elif failure == "wrong-binding":
            original(connection, {**value, "binding": "wrong"}, deadline, check)
        elif failure == "after-delivery":
            original(connection, value, deadline, check)
        elif failure == "deadline":
            time.sleep(wire.remaining(deadline) + 0.02)
            original(connection, value, deadline, check)
        raise OSError("fabricated uncertain permit delivery")

    monkeypatch.setattr(wire, "send", send)
    with pytest.raises((OSError, ValueError)):
        launch(state)
    state.children[0].wait(timeout=5)
    if failure != "after-delivery":
        assert not state.report.exists()
    assert producer.fence_path(state.identity).exists()
    with pytest.raises(ValueError, match="unresolved restore"):
        launch(state)
    assert len(state.children) == 1
    assert state.store.pointer("last-reopened") is None


def test_intent_persistence_failure_prevents_dispatch(sandbox, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        raise OSError("fabricated persistence failure")

    monkeypatch.setattr(history, "durable_create", fail)
    with pytest.raises(OSError):
        producer.produce(
            sandbox.store,
            sandbox.key,
            sandbox.recipe,
            sandbox.identity,
            dispatch=lambda *a: calls.append(a),
        )
    assert calls == [] and not sandbox.report.exists()


def test_permit_persistence_failure_prevents_host_exec(sandbox, monkeypatch):
    original = history.durable_create

    def fail(path, record):
        if (
            record["type"] == "intent"
            and sandbox.store.get("receipts", record["receipt"]).get("action") == "exec"
        ):
            raise OSError("fabricated permit persistence failure")
        return original(path, record)

    monkeypatch.setattr(history, "durable_create", fail)
    with pytest.raises(OSError):
        launch(sandbox)
    sandbox.children[0].wait(timeout=5)
    assert not sandbox.report.exists()
    assert producer.fence_path(sandbox.identity).exists()


@pytest.mark.parametrize("content", [b"", b"{", b"null", b'{"status":"completed"}'])
def test_corrupt_or_unrecognized_fence_is_fail_closed(sandbox, content):
    path = producer.fence_path(sandbox.identity)
    with operation_lock.operation_lock(sandbox.identity):
        path.write_bytes(content)
        path.chmod(0o600)
    with pytest.raises(ValueError, match="unresolved restore"):
        launch(sandbox)
    assert sandbox.children == []


def test_running_image_substitution_invalidates_process_grant(sandbox):
    with launch(sandbox) as proof:
        proof.image = {**proof.image, "inode": proof.image["inode"] + 1}
        with pytest.raises(ValueError, match="running image"):
            proof.validate()
        assert proof.invalid


def test_bootstrap_route_change_refuses_before_host(sandbox, monkeypatch):
    state = sandbox
    real = state.dispatch

    def changed(argv, identity, deadline):
        real(argv, identity, deadline)
        # Replace the compositor socket path after dispatch; helper/parent pins must reject it.
        Path(identity["niri_socket"]).unlink()
        Path(identity["niri_socket"]).write_text("fabricated replacement, not a socket")

    state.dispatch = changed
    with pytest.raises((EOFError, ValueError, OSError)):
        launch(state)
    assert not state.report.exists()


def test_fsync_file_then_directory_precedes_each_effect(sandbox, monkeypatch):
    events = []
    sync = os.fsync
    send = wire.send
    dispatch = sandbox.dispatch
    directory = producer.fence_path(sandbox.identity)

    def observed_sync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        sync(fd)
        if path == directory:
            events.append("directory")
        elif path.parent == directory and path.suffix == ".json":
            events.append("record")

    def observed_dispatch(*args):
        assert events[-2:] == ["record", "directory"]
        dispatch(*args)

    def observed_send(connection, value, *args):
        if value["type"] == "exec":
            assert events[-2:] == ["record", "directory"]
        return send(connection, value, *args)

    monkeypatch.setattr(os, "fsync", observed_sync)
    monkeypatch.setattr(wire, "send", observed_send)
    sandbox.dispatch = observed_dispatch
    with launch(sandbox):
        pass


def test_fence_fsync_failure_leaves_blocking_partial_record_without_dispatch(sandbox, monkeypatch):
    sync = os.fsync

    def fail(fd):
        if os.readlink(f"/proc/self/fd/{fd}").endswith("00000000.json"):
            raise OSError("fabricated fsync failure")
        sync(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        launch(sandbox)
    assert sandbox.children == []
    assert producer.fence_path(sandbox.identity).exists()
    with pytest.raises(ValueError, match="unresolved restore"):
        launch(sandbox)


def test_orphan_permit_or_dangling_fence_never_admits_writer(sandbox):
    path = producer.fence_path(sandbox.identity)
    with operation_lock.operation_lock(sandbox.identity):
        path.with_suffix(".permit").write_text("{")
    with pytest.raises(ValueError, match="unresolved restore"):
        launch(sandbox)
    assert sandbox.children == []


def test_no_handshake_before_deadline_never_retries(sandbox):
    calls = []
    with pytest.raises(TimeoutError):
        producer.produce(
            sandbox.store,
            sandbox.key,
            sandbox.recipe,
            sandbox.identity,
            timeout=0.5,
            dispatch=lambda *a: calls.append(a),
        )
    assert len(calls) == 1
    assert producer.fence_path(sandbox.identity).exists()


@pytest.mark.parametrize("mutation", ["parent-start", "nonce", "ready-binding"])
def test_handshake_binding_tampering_never_reaches_host(sandbox, monkeypatch, mutation):
    if mutation == "parent-start":
        dispatch = sandbox.dispatch

        def changed(argv, *args):
            argv = list(argv)
            argv[8] = str(int(argv[8]) + 1)
            dispatch(argv, *args)

        sandbox.dispatch = changed
    elif mutation == "nonce":
        send = wire.send

        def wrong_nonce(connection, value, *args):
            if value["type"] == "prepare":
                value = {**value, "nonce": "wrong"}
            return send(connection, value, *args)

        monkeypatch.setattr(wire, "send", wrong_nonce)
    else:
        receive = wire.receive

        def wrong_binding(*args):
            value = receive(*args)
            return {**value, "binding": "wrong"} if value["type"] == "ready" else value

        monkeypatch.setattr(wire, "receive", wrong_binding)
    with pytest.raises((ValueError, OSError, EOFError)):
        launch(sandbox)
    sandbox.children[0].wait(timeout=5)
    assert not sandbox.report.exists()
    assert not any(
        p.get("action") == "exec" for _, p in journal_records(sandbox.identity, sandbox.store)
    )


def test_host_cwd_drift_with_same_pid_image_and_argv_refuses(sandbox):
    with launch(sandbox) as proof:
        original_pin = dict(proof.process.pin)
        original_argv = proof.process.argv()
        sandbox.report.with_suffix(".chdir").touch()
        deadline = time.monotonic() + 1
        while not sandbox.report.with_suffix(".changed").exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert proof.process.pin == original_pin
        assert proof.process.argv() == original_argv
        proof.process.validate(proof.image)
        with pytest.raises(ValueError, match="directory|cwd"):
            proof.validate()


def test_retained_cwd_descriptor_ownership_and_close_without_termination(sandbox):
    proof = launch(sandbox)
    fd = proof.cwd_fd
    assert not os.get_inheritable(fd)
    assert producer.directory_pin(fd) == proof.directory
    assert proof.directory == producer.directory_pin_for_path(sandbox.recipe["cwd"])
    proof.close()
    with pytest.raises(OSError):
        os.fstat(fd)
    assert sandbox.children[0].poll() is None
    proof.close()  # idempotent descriptor ownership, no close of recycled descriptor


def test_cwd_path_substitution_refuses_held_original_directory(sandbox, tmp_path):
    with launch(sandbox) as proof:
        old = dict(proof.directory)
        replacement = tmp_path / "replacement"
        replacement.mkdir()
        proof.spec = {**proof.spec, "cwd": str(replacement)}
        with pytest.raises(ValueError, match="pathname"):
            proof.validate()
        assert producer.directory_pin(proof.cwd_fd) == old
        assert proof.invalid


def test_failed_proof_closes_admitted_directory_fd_without_termination(sandbox, monkeypatch):
    held = []

    def refuse(self, deadline):
        held.append(self.cwd_fd)
        raise ValueError("fabricated cwd validation failure")

    monkeypatch.setattr(producer.LaunchProof, "validate_cwd", refuse)
    with pytest.raises(ValueError, match="cwd validation"):
        launch(sandbox)
    assert len(held) == 1
    with pytest.raises(OSError):
        os.fstat(held[0])
    assert sandbox.children[0].poll() is None


@pytest.mark.parametrize("fault", [OSError, KeyboardInterrupt, SystemExit])
def test_standalone_exit_failure_closes_orphan_proof_without_termination(
    sandbox, monkeypatch, fault
):
    from niri_desktop_continuity.restore_attempt import Attempt

    proofs = []
    init, exit_attempt = producer.LaunchProof.__init__, Attempt.__exit__

    def constructor(self, *args, **kwargs):
        init(self, *args, **kwargs)
        proofs.append(self)

    error = fault("fabricated exit failure")

    def failed(self, *args):
        exit_attempt(self, *args)
        raise error

    monkeypatch.setattr(producer.LaunchProof, "__init__", constructor)
    monkeypatch.setattr(Attempt, "__exit__", failed)
    with pytest.raises(fault) as raised:
        launch(sandbox)
    assert raised.value is error
    assert len(proofs) == 1 and proofs[0].cwd_fd is None and proofs[0].process.fd is None
    assert sandbox.children[0].poll() is None


def test_standalone_orphan_close_failure_surfaces_exit_error_as_context(sandbox, monkeypatch):
    from niri_desktop_continuity.restore_attempt import Attempt

    proofs = []
    init, exit_attempt = producer.LaunchProof.__init__, Attempt.__exit__
    error = KeyboardInterrupt("fabricated exit interruption")
    cleanup = OSError("fabricated orphan process close error")

    def constructor(self, *args, **kwargs):
        init(self, *args, **kwargs)
        proofs.append(self)

    def failed(self, *args):
        exit_attempt(self, *args)
        process = proofs[0].process
        close = process.close

        def faulty_close():
            close()
            raise cleanup

        monkeypatch.setattr(process, "close", faulty_close)
        raise error

    monkeypatch.setattr(producer.LaunchProof, "__init__", constructor)
    monkeypatch.setattr(Attempt, "__exit__", failed)
    with pytest.raises(OSError) as raised:
        launch(sandbox)
    assert raised.value is cleanup and cleanup.__context__ is error
    assert proofs[0].cwd_fd is None and proofs[0].process.fd is None
    assert sandbox.children[0].poll() is None
