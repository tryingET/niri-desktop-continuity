"""Independent Linux primitive/error oracles and the peer-credential handover limitation."""

import ctypes
import errno
import os
import socket
import struct
import subprocess
import sys

import pytest
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_exited_syscalls as calls
from niri_desktop_continuity import restore_host as host


def test_checked_libc_statfs_layout_matches_independent_c_headers(tmp_path):
    source = tmp_path / "abi.c"
    source.write_text("""#define _GNU_SOURCE
#include <sys/statfs.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <stddef.h>
_Static_assert(sizeof(struct ucred)==12, "ucred size");
_Static_assert(_Alignof(struct ucred)==4, "ucred alignment");
_Static_assert(offsetof(struct ucred,pid)==0, "pid offset");
_Static_assert(offsetof(struct ucred,uid)==4, "uid offset");
_Static_assert(offsetof(struct ucred,gid)==8, "gid offset");
_Static_assert(sizeof(pid_t)==4 && (pid_t)-1<0, "signed pid_t");
_Static_assert(sizeof(uid_t)==4 && (uid_t)-1>0, "unsigned uid_t");
_Static_assert(sizeof(gid_t)==4 && (gid_t)-1>0, "unsigned gid_t");
_Static_assert(sizeof(struct statfs)==120, "size");
_Static_assert(_Alignof(struct statfs)==8, "alignment");
_Static_assert(offsetof(struct statfs,f_type)==0, "type");
_Static_assert(offsetof(struct statfs,f_bsize)==8, "bsize");
_Static_assert(offsetof(struct statfs,f_blocks)==16, "blocks");
_Static_assert(offsetof(struct statfs,f_bfree)==24, "bfree");
_Static_assert(offsetof(struct statfs,f_bavail)==32, "bavail");
_Static_assert(offsetof(struct statfs,f_files)==40, "files");
_Static_assert(offsetof(struct statfs,f_ffree)==48, "ffree");
_Static_assert(offsetof(struct statfs,f_fsid)==56, "fsid");
_Static_assert(offsetof(struct statfs,f_namelen)==64, "namelen");
_Static_assert(offsetof(struct statfs,f_frsize)==72, "frsize");
_Static_assert(offsetof(struct statfs,f_flags)==80, "flags");
_Static_assert(offsetof(struct statfs,f_spare)==88, "spare");
int main(void){return 0;}
""")
    subprocess.run(["cc", "-c", str(source), "-o", str(tmp_path / "abi.o")], check=True)
    assert ctypes.sizeof(calls.Statfs) == 120
    assert ctypes.alignment(calls.Statfs) == 8


def test_missing_python_and_libc_pidfd_facilities_refuses(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delattr(os, "pidfd_open", raising=False)
    monkeypatch.setattr(host.ctypes, "CDLL", lambda *_a, **_kw: SimpleNamespace())
    with pytest.raises(ValueError, match="pidfd support required"):
        native.absence({"pid": 12, "boot_id": "fixture", "start_ticks": 1})


def test_later_process_lookup_exception_cannot_supply_absence(monkeypatch):
    def forbidden(*_):
        raise ProcessLookupError(errno.ESRCH, "later lookup, not primitive")

    monkeypatch.setattr(host.Process, "live", forbidden)
    with pytest.raises(ValueError, match="occupied"):
        native.absence(host.process_pin(os.getpid()))


def test_active_namespace_is_not_pid_for_children():
    code = """
import ctypes,os,time
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_exited_syscalls as calls
libc=ctypes.CDLL(None,use_errno=True)
libc.unshare.argtypes=[ctypes.c_int];libc.unshare.restype=ctypes.c_int
assert libc.unshare(0x20000000)==0,ctypes.get_errno() # CLONE_NEWPID; current task stays in active ns.
scope=native.Scope(time.monotonic()+3)
try:
    active=os.stat("/proc/self/ns/pid")
    assert scope.value["pid_namespace"]=={"device":active.st_dev,"inode":active.st_ino}
    try:
        children=os.stat("/proc/self/ns/pid_for_children")
    except FileNotFoundError:
        pass # No child/init exists there yet; never treat its absence as active scope.
    else:
        assert (children.st_dev,children.st_ino)!=(active.st_dev,active.st_ino)
    scope.check()
finally:
    scope.close()
"""
    result = isolated_namespace(code)
    assert result.returncode == 0, result.stderr


def test_nested_active_namespace_with_outer_proc_mount_refuses():
    check = """
import errno,os,time
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_exited_syscalls as calls
assert os.getpid()!=1 and os.readlink("/proc/self")!=str(os.getpid())
try:
    native.Scope(time.monotonic()+3)
except ValueError as exc:
    assert "genuine proc self coordinate mismatch" in str(exc),str(exc)
except OSError as exc:
    assert exc.errno==errno.ENOENT # The aliased outer numeric namespace entry may already be absent.
else:
    raise AssertionError("outer proc coordinates accepted for nested caller")
"""
    supervisor = f"import subprocess,sys;raise SystemExit(subprocess.call([sys.executable,'-I','-B','-c',{check!r}]))"
    code = f"""
import ctypes,subprocess,sys
libc=ctypes.CDLL(None,use_errno=True)
libc.unshare.argtypes=[ctypes.c_int];libc.unshare.restype=ctypes.c_int
assert libc.unshare(0x20000000)==0,ctypes.get_errno()
# Spawn namespace init, then a non-init caller. Deliberately retain this fixture's outer proc mount.
p=subprocess.run([sys.executable,"-I","-B","-c",{supervisor!r}],capture_output=True,text=True)
assert p.returncode==0,p.stderr
"""
    result = isolated_namespace(code)
    assert result.returncode == 0, result.stderr


def test_unverified_abi_refuses_before_libc(monkeypatch):
    monkeypatch.setattr(sys.implementation, "_multiarch", "aarch64-linux-gnu")
    monkeypatch.setattr(
        ctypes, "CDLL", lambda *_a, **_k: pytest.fail("unverified ABI reached libc")
    )
    with pytest.raises(ValueError, match="unverified"):
        native.procfs(0)


def test_non_proc_filesystem_is_not_a_procfs_marker(tmp_path):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        with pytest.raises(ValueError, match="not procfs"):
            native.procfs(fd)
    finally:
        os.close(fd)


@pytest.mark.parametrize("error", sorted(set(errno.errorcode) - {errno.ESRCH}))
def test_every_other_named_errno_refuses_at_exact_primitive(error, monkeypatch):
    def fail(_):
        raise OSError(error, "fixture")

    monkeypatch.setattr(host, "open_pidfd", fail)
    with pytest.raises(OSError) as observed:
        native.absence({"pid": 12, "boot_id": "fixture", "start_ticks": 1})
    assert observed.value.errno == error


def test_cooperative_zombie_returns_fd_and_is_not_esrch():
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys;sys.stdin.buffer.read(1)"], stdin=subprocess.PIPE
    )
    pin = host.process_pin(child.pid)
    try:
        child.stdin.write(b"q")
        child.stdin.close()
        os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
        with pytest.raises(ValueError, match="occupied"):
            native.absence(pin)
    finally:
        if not child.stdin.closed:
            child.stdin.close()
        assert child.wait(timeout=5) == 0


def test_inherited_serving_fd_does_not_change_connection_peer_credentials():
    # Counterexample, NOT a detectable production RED. The accepted no-handover trust is needed.
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        expected = struct.unpack("3i", left.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        code = "import os,socket,sys;s=socket.socket(fileno=int(sys.argv[1]));s.sendall(str(os.getpid()).encode());s.close()"
        child = subprocess.Popen(
            [sys.executable, "-I", "-c", code, str(right.fileno())], pass_fds=[right.fileno()]
        )
        right.close()
        left.settimeout(3)
        serving_pid = int(left.recv(32))
        assert child.wait(timeout=3) == 0
        after = struct.unpack("3i", left.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        assert serving_pid == child.pid != os.getpid()
        assert after == expected and after[0] == os.getpid()
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize(
    "case",
    ["self-pid", "user-namespace", "uid", "own-stat-pid", "namespace-replaced", "parent-drift"],
)
def test_scope_drift_refuses_in_real_controlled_scope(case):
    code = f"""
import os,time
from unittest.mock import patch
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_exited_syscalls as calls
scope = native.Scope(time.monotonic()+5)
try:
    original = scope.read_leaf
    def read(parent, path, uid=None):
        data = original(parent, path, uid)
        if {case!r} == "uid" and path == "status":
            lines = data.splitlines()
            data = b"\\n".join(b"Uid:\\t99\\t99\\t99\\t99" if line.startswith(b"Uid:") else line for line in lines)+b"\\n"
        if {case!r} == "own-stat-pid" and path == "stat":
            data = b"999 " + data.split(b" ",1)[1]
        if {case!r} == "parent-drift" and path == "stat":
            head, rest = data.rsplit(b")",1)
            fields = rest.split()
            fields[1] = b"999"
            data = head+b") "+b" ".join(fields)
        return data
    with patch.object(scope, "read_leaf", read):
        if {case!r} == "user-namespace":
            scope.userns = (scope.userns[0], {{"device": 0,"inode": 0}})
        if {case!r} == "namespace-replaced":
            scope.pidns = (scope.pidns[0], {{"device": 0,"inode": 0}})
        with patch.object(native.os, "readlink", return_value="999") if {case!r} == "self-pid" else patch.object(scope, "deadline", scope.deadline):
            try:
                scope.check()
            except (ValueError, OSError):
                pass
            else:
                raise AssertionError("scope drift accepted")
finally:
    scope.close()
"""
    result = isolated_namespace(code)
    assert result.returncode == 0, result.stderr
