"""Controlled Unix server/children only. No real compositor or application inventory."""

import errno
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_exited_transport import Transport


@contextmanager
def server(replies, *, delayed=0, connections=1):
    assert "NIRI_SOCKET" not in os.environ
    # AF_UNIX sun_path is 108 bytes. Test-owned socket directly under private TMPDIR.
    path = Path(os.environ["TMPDIR"]) / ("s" + os.urandom(3).hex())
    received, errors = [], []
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    path.chmod(0o600)
    listener.listen(1)
    listener.settimeout(3)
    info = path.stat()
    identity = {
        "boot_id": host.boot_id(),
        "niri_socket": str(path),
        "socket_device": info.st_dev,
        "socket_inode": info.st_ino,
    }

    def serve():
        try:
            for _ in range(connections):
                with listener.accept()[0] as stream:
                    stream.settimeout(10)
                    buffer = b""
                    ended = False
                    while not ended:
                        while b"\n" not in buffer:
                            block = stream.recv(128)
                            if not block:
                                ended = True
                                break
                            buffer += block
                        if ended:
                            break
                        line, buffer = buffer.split(b"\n", 1)
                        received.append(line + b"\n")
                        data = replies(json.loads(line), len(received))
                        if data is None:
                            break
                        if delayed:
                            for byte in data:
                                time.sleep(delayed)
                                stream.sendall(bytes([byte]))
                        else:
                            stream.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client refusal is expected; never reconnect.
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        yield identity, received
    finally:
        worker.join(5)  # Let a queued short-lived refused connection reach accept/EOF.
        listener.close()
        assert not worker.is_alive()
        assert not errors, errors
        path.unlink()  # Only this fixture's new, inactive socket; never retained runtime history.


def test_given_private_persistent_server_when_queried_then_exact_authenticated_wire():
    golden = {
        "Version": b'{"Ok":{"Version":"fixture-version"}}\n',
        "Windows": b'{"Ok":{"Windows":[]}}\n',
        "Workspaces": b'{"Ok":{"Workspaces":[]}}\n',
        "Outputs": b'{"Ok":{"Outputs":{}}}\n',
    }
    with server(lambda name, _: golden[name]) as (identity, requests):
        transport = Transport(identity, time.monotonic() + 2)
        try:
            for name in golden:
                transport.query(name)
            assert transport.credentials == {
                "pid": os.getpid(),
                "uid": os.getuid(),
                "gid": os.getgid(),
            }
            assert requests == [b'"Version"\n', b'"Windows"\n', b'"Workspaces"\n', b'"Outputs"\n']
        finally:
            transport.close()


@pytest.mark.parametrize(
    "reply",
    [
        b'{"Err":"fixture"}\n',
        b'{"Ok":{"Windows":[]}}\n',
        b'{"Ok":{"Version":"x"},"other":0}\n',
        b'{"Ok":{"Version":"x","Version":"x"}}\n',
        b'{"Ok":{"Version":NaN}}\n',
        b'{"Ok":{"Version":null}}\n',
        b'{"Ok":{"Version":true}}\n',
        b'{"Ok":{"Version":[]}}\n',
        b'{"Ok":{"Version":""}}\n',
        b'{"Ok":{"Version":"x\\u0000"}}\n',
        b'{"Ok":{"Version":"' + b"x" * 4097 + b'"}}\n',
        b'{"Ok":{"Version":1e999}}\n',
        b'{"Ok":{"Version":{"compositor":"x","cli":"x"}}}\n',
        b'{"Ok":{"Version":"x"}}\n{}\n',
        b"\xff\n",
        None,
    ],
)
def test_bad_reply_refuses_without_reconnect(reply):
    with server(lambda *_: reply) as (identity, requests):
        transport = Transport(identity, time.monotonic() + 2)
        try:
            with pytest.raises((ValueError, OSError)):
                transport.query("Version")
            assert requests == [b'"Version"\n']
        finally:
            transport.close()


@pytest.mark.parametrize("mismatch", ["uid", "peer-drift"])
def test_wrong_uid_or_changed_peer_refuses_on_reply_socket(monkeypatch, mismatch):
    original = socket.socket
    calls = []

    class Socket(original):
        def getsockopt(self, level, option, *args):
            result = super().getsockopt(level, option, *args)
            if level == socket.SOL_SOCKET and option == socket.SO_PEERCRED:
                pid, uid, gid = struct.unpack("3i", result)
                calls.append(self.fileno())
                if mismatch == "uid":
                    uid += 1
                elif len(calls) > 2:
                    pid += 1
                return struct.pack("3i", pid, uid, gid)
            return result

    monkeypatch.setattr(socket, "socket", Socket)
    with server(lambda *_: b'{"Ok":{"Version":"fixture"}}\n') as (identity, requests):
        transport = None
        try:
            with pytest.raises(ValueError):
                transport = Transport(identity, time.monotonic() + 2)
                transport.query("Version")
            assert requests == []
        finally:
            if transport is not None:
                transport.close()


def test_unsigned_ucred_uid_gid_have_independent_little_endian_golden(monkeypatch):
    from types import SimpleNamespace

    raw = b"\x7b\x00\x00\x00\x01\x00\x00\x80\x02\x00\x00\x80"
    monkeypatch.setattr(os, "getuid", lambda: 2147483649)
    monkeypatch.setattr(os, "geteuid", lambda: 2147483649)

    def credentials(level, option, size):
        assert (level, option, size) == (socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return raw

    transport = object.__new__(Transport)
    transport.socket = SimpleNamespace(getsockopt=credentials)
    assert transport.peer() == {"pid": 123, "uid": 2147483649, "gid": 2147483650}


def test_every_accepted_reply_authenticates_its_own_fd(monkeypatch):
    calls = []
    original = socket.socket

    class MeasuredSocket(original):
        def getsockopt(self, level, option, *args):
            if level == socket.SOL_SOCKET and option == socket.SO_PEERCRED:
                calls.append(self.fileno())
            return super().getsockopt(level, option, *args)

    monkeypatch.setattr(socket, "socket", MeasuredSocket)
    with server(lambda *_: b'{"Ok":{"Version":"fixture"}}\n') as (identity, _):
        transport = Transport(identity, time.monotonic() + 2)
        try:
            before = len(calls)
            for _ in range(4):
                transport.query("Version")
            assert len(calls) - before == 8
            assert set(calls) == {transport.socket.fileno()}
        finally:
            transport.close()


def test_oversized_reply_refuses_without_unbounded_read():
    with server(lambda *_: b"x" * (8 * 1024**2 + 1)) as (identity, _):
        transport = Transport(identity, time.monotonic() + 3)
        try:
            with pytest.raises(ValueError, match="exceeds bound"):
                transport.query("Version")
        finally:
            transport.close()


def test_group_writable_endpoint_refuses_before_connection():
    with server(lambda *_: None, connections=0) as (identity, requests):
        Path(identity["niri_socket"]).chmod(0o620)
        with pytest.raises(ValueError, match="unsafe"):
            Transport(identity, time.monotonic() + 2)
        assert requests == []


def test_trickle_cannot_renew_complete_frame_deadline():
    with server(lambda *_: b'{"Ok":{"Version":"fixture"}}\n', delayed=0.015) as (identity, _):
        transport = Transport(identity, time.monotonic() + 0.1)
        try:
            with pytest.raises((ValueError, TimeoutError)):
                transport.query("Version")
        finally:
            transport.close()


def isolated_namespace(code, data_root=None):
    """Test-owned namespace/root; no unmapped host-root ancestor is silently trusted.

    All mounts are confined to a new private mount namespace and die with its init.
    System libraries and candidate are read-only; only this fixture's private evidence
    tree is writable. Production has no unshare, chroot, mount or injection path.
    """
    candidate = Path(native.__file__).parents[2]
    import sysconfig

    editable = Path(sysconfig.get_path("purelib")) / "_editable_impl_niri_desktop_continuity.pth"
    alias = Path(editable.read_text().strip()).parent if editable.exists() else candidate
    assert alias.is_absolute() and ".." not in alias.parts
    evidence = (
        Path(data_root)
        if data_root is not None
        else Path(tempfile.mkdtemp(prefix="proof-", dir=os.environ.get("TMPDIR")))
    )
    for name in ("home", "state", "cache", "runtime", "config", "data", "tmp"):
        (evidence / name).mkdir(mode=0o700, exist_ok=True)
    jail = evidence / "namespace-root"
    jail.mkdir(mode=0o700)
    for name in ("usr", "lib", "lib64", "proc", "dev", "candidate", "e", "old-root"):
        (jail / name).mkdir(mode=0o755)
    (jail / "dev/null").touch()
    (jail / "dev/urandom").touch(mode=0o600, exist_ok=False)
    (jail / "bin").symlink_to("usr/bin")
    (jail / "run/user/0").mkdir(mode=0o700, parents=True)
    code = code.replace(str(candidate), "/candidate").replace(str(evidence), "/e")
    prefix = "import sys; sys.path.insert(0, '/candidate/src'); "
    python = "/candidate/.venv/bin/python"
    child = [python, "-I", "-B", "-c", prefix + code]
    init = f"import subprocess; raise SystemExit(subprocess.call({child!r}))"
    script = """set -eu
jail=$1; candidate=$2; evidence=$3; alias=$4; shift 4
mount --make-rprivate /
mount --bind "$jail" "$jail"
for dir in usr lib lib64; do
    mount --rbind /$dir "$jail/$dir"
    mount -o remount,bind,ro "$jail/$dir"
done
mount --bind "$candidate" "$jail/candidate"
mount -o remount,bind,ro "$jail/candidate"
if [ "$alias" != /candidate ]; then
    mkdir -p "$jail$alias"
    mount --bind "$candidate" "$jail$alias"
    mount -o remount,bind,ro "$jail$alias"
fi
mount --bind "$evidence" "$jail/e"
mount --bind "$evidence/runtime" "$jail/run/user/0"
mount --bind /dev/null "$jail/dev/null"
# The donor is the admitted genuine device in the detached outer fixture.
test ! -L /dev/urandom
test "$(stat -c '%F:%t:%T' /dev/urandom)" = 'character special file:1:9'
mount --bind /dev/urandom "$jail/dev/urandom"
mount -o remount,bind,ro "$jail/dev/urandom"
test ! -L "$jail/dev/urandom"
test "$(stat -c '%F:%t:%T' "$jail/dev/urandom")" = 'character special file:1:9'
mount -t proc proc "$jail/proc"
export HOME=/e/home XDG_STATE_HOME=/e/state XDG_CACHE_HOME=/e/cache
export XDG_RUNTIME_DIR=/e/runtime XDG_CONFIG_HOME=/e/config XDG_DATA_HOME=/e/data TMPDIR=/e/tmp
cd "$jail"
pivot_root . old-root
cd /
exec chroot / "$@"
"""
    return subprocess.run(
        [
            "unshare",
            *([] if os.getuid() == 0 else ["--user", "--map-root-user"]),
            "--mount",
            "--pid",
            "--fork",
            "--",
            "/bin/sh",
            "-c",
            script,
            "fixture",
            str(jail),
            str(candidate),
            str(evidence),
            str(alias),
            python,
            "-I",
            "-B",
            "-c",
            init,
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )


def test_real_procfs_active_scope_and_self():
    result = isolated_namespace("""
import os, time
from niri_desktop_continuity import restore_exited_scope as native
scope = native.Scope(time.monotonic() + 3)
try:
    assert scope.value["pid_namespace"] == scope.value["procfs"]["pid_namespace"]
    assert scope.info(os.getpid())["process"]["pid"] == os.getpid()
    fd = os.open("/proc", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        native.procfs(fd)
        assert scope.root == {"device": os.fstat(fd).st_dev, "inode": os.fstat(fd).st_ino}
    finally:
        os.close(fd)
    scope.check()
finally:
    scope.close()
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("fallback", [False, True])
def test_actual_pidfd_occupied_then_cooperative_exit_and_reap(fallback, monkeypatch):
    if fallback:
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys; sys.stdin.buffer.read(1)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pin = host.process_pin(child.pid)
    try:
        with pytest.raises(ValueError, match="occupied"):
            native.absence(pin)
        child.stdin.write(b"q")
        child.stdin.close()
        assert child.wait(timeout=5) == 0
        assert native.absence(pin) == {
            "process": pin,
            "primitive": "linux-pidfd-open",
            "flags": 0,
            "errno": "ESRCH",
        }
    finally:
        if not child.stdin.closed:
            child.stdin.close()
        child.wait(timeout=5)  # Cooperative EOF, never signal/kill.


@pytest.mark.parametrize("pid", [True, False, 0, -1, 1.0, 2147483648, 2**100])
def test_invalid_pid_refuses_before_primitive(pid, monkeypatch):
    monkeypatch.setattr(host, "open_pidfd", lambda _: pytest.fail("invalid PID reached syscall"))
    with pytest.raises(ValueError):
        native.absence({"boot_id": "fixture", "pid": pid, "start_ticks": 1})


@pytest.mark.parametrize(
    "error", [errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EINVAL, errno.EMFILE, None]
)
def test_only_exact_primitive_esrch_is_evidence(error, monkeypatch):
    def denied(_):
        raise OSError(error, "fixture")

    monkeypatch.setattr(host, "open_pidfd", denied)
    with pytest.raises(OSError):
        native.absence({"boot_id": "fixture", "pid": 12, "start_ticks": 1})
