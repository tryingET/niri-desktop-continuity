"""Real same-UID capability-bearing ancestor: no namespace-permission substitute."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from test_restore_exited_history import scene
from test_restore_exited_measurements import PEER, cooperative, wait
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host

SETUP = r"""
import ctypes, errno, fcntl, json, os, sys, time, traceback
libc = ctypes.CDLL(None, use_errno=True)
class Header(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint), ("pid", ctypes.c_int)]
class Caps(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint), ("permitted", ctypes.c_uint),
                ("inheritable", ctypes.c_uint)]
def caps(value):
    h = Header(0x20080522, 0)
    rows = (Caps * 2)()
    for i in range(2):
        rows[i].effective = rows[i].permitted = (value >> (32*i)) & 0xffffffff
    assert libc.capset(ctypes.byref(h), rows) == 0, ctypes.get_errno()
    assert libc.capget(ctypes.byref(h), rows) == 0
    assert sum(r.effective << (32*i) for i,r in enumerate(rows)) == value
    assert sum(r.permitted << (32*i) for i,r in enumerate(rows)) == value
    assert all(r.inheritable == 0 for r in rows)
def facts(role):
    status = dict(line.split(":",1) for line in open("/proc/self/status"))
    result = {k:status[k].strip() for k in ("Pid","Tgid","PPid","Uid","NSpid","NStgid","CapEff","CapPrm","CapInh")}
    result.update(role=role, dumpable=libc.prctl(3,0,0,0,0),
                  pidns=os.stat("/proc/self/ns/pid").st_ino,
                  userns=os.stat("/proc/self/ns/user").st_ino)
    print(json.dumps(result), flush=True)
    return result
assert os.getppid() == 1 and os.getpid() != 1
# Prevent UID0 exec from reacquiring capabilities in these test-owned descendants.
assert libc.prctl(28, 1, 0, 0, 0) == 0, ctypes.get_errno()
caps((1 << 35) if denied else 0)  # CAP_WAKE_ALARM retained, never exercised.
assert libc.prctl(4,1,0,0,0) == 0
manager = facts("manager")
if role == "peer":
    import socket
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind("/e/manager.sock")
    os.chmod("/e/manager.sock", 0o600)
    listener.listen(1)
child = os.fork()
if child:
    _, status = os.waitpid(child, 0)
    raise SystemExit(os.waitstatus_to_exitcode(status))
try:
    caps(0)
    assert libc.prctl(4,1,0,0,0) == 0
    caller = facts("caller")
    assert caller["PPid"] == manager["Pid"]
    assert caller["pidns"] == manager["pidns"]
    assert caller["userns"] == manager["userns"]
    assert caller["Uid"].split() == manager["Uid"].split() == ["0"]*4
    assert manager["dumpable"] == caller["dumpable"] == 1
    if hasattr(os, "pidfd_open"):
        fd = os.pidfd_open(int(manager["Pid"]), 0)
    else:
        pidfd_open = libc.pidfd_open
        pidfd_open.argtypes = [ctypes.c_int, ctypes.c_uint]
        pidfd_open.restype = ctypes.c_int
        fd = pidfd_open(int(manager["Pid"]), 0)
        if fd < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    try:
        try:
            ns = fcntl.ioctl(fd, 0xff05, 0)
        except OSError as exc:
            assert denied and exc.errno == errno.EACCES, repr(exc)
            print("CONTROL: actual manager ioctl 0xff05 EACCES", flush=True)
        else:
            os.close(ns)
            assert not denied, "required manager capability denial missing"
            print("CONTROL: manager ioctl readable", flush=True)
    finally:
        os.close(fd)
    sys.path.insert(0,"/candidate/tests")
    exec(action)
except BaseException:
    traceback.print_exc()
    os._exit(1)
os._exit(0)
"""


def capability(root, action, *, denied=True, role="ancestor"):
    code = f"denied={denied!r}\nrole={role!r}\naction={action!r}\n" + SETUP
    return isolated_namespace(code, data_root=root)


def roles(root, manager, role):
    root = Path(root)
    old, protected = cooperative(), cooperative()
    original = host.process_pin(old.pid)
    old.stdin.close()
    assert old.wait(timeout=5) == 0
    state = scene(0)
    for w in state["windows"]:
        w["pid"] = manager if role == "protected" else protected.pid
    values = {
        "Version": "fixture-version",
        "Windows": state["windows"],
        "Workspaces": state["workspaces"],
        "Outputs": {"FIXTURE-1": {"name": "FIXTURE-1", "logical": {"scale": 1.0}}},
    }
    (root / "values.json").write_text(json.dumps(values))
    (root / "peer.py").write_text(PEER)
    peer = None
    try:
        if role == "peer":
            pid, socket_path = manager, root / "manager.sock"
        else:
            peer = subprocess.Popen(
                [sys.executable, "-I", str(root / "peer.py"), str(root)], stdin=subprocess.PIPE
            )
            wait(root / "ready")
            pid, socket_path = peer.pid, root / "peer.sock"
        pin = host.process_pin(pid)
        info = socket_path.stat()
        source = {
            "identity": {
                "boot_id": pin["boot_id"],
                "niri_socket": str(socket_path),
                "socket_device": info.st_dev,
                "socket_inode": info.st_ino,
            },
            "inventory_complete": True,
            "niri_version": {"compositor": "fixture-version", "cli": "fixture-client"},
            "process_inventory": [
                {
                    "pid": pid,
                    "ppid": 1 if role == "peer" else os.getpid(),
                    "start_ticks": pin["start_ticks"],
                    "comm": "fixture",
                    "cgroup": None,
                }
            ],
        }
        opened, ns, cohorts, weak = {}, [], [], []
        real_pidfd, real_ns = native.Scope.pidfd, native.Scope.namespaces
        real_cohort, real_weak = native.Cohort.__init__, native.AncestorGeneration.__init__

        def pidfd(s, stack, p):
            fd = real_pidfd(s, stack, p)
            opened[fd] = p
            return fd

        def namespaces(s, stack, fd):
            ns.append((opened[fd], fd))
            return real_ns(s, stack, fd)  # Actual ioctl result, never patched to success.

        def cohort(c, *a):
            real_cohort(c, *a)
            cohorts.append(c)

        def ancestor(g, *a):
            assert cohorts, "weak acquisition preceded full cohort"
            assert all(
                isinstance(cohorts[0].generations[p], native.Generation)
                for p in cohorts[0].full_pids
            )
            real_weak(g, *a)
            weak.append(g)

        with (
            patch.object(native.Scope, "pidfd", pidfd),
            patch.object(native.Scope, "namespaces", namespaces),
            patch.object(native.Cohort, "__init__", cohort),
            patch.object(native.AncestorGeneration, "__init__", ancestor),
        ):
            if role in ("peer", "protected"):
                with pytest.raises(PermissionError) as error:
                    with proof.current(source, original, 12000, expires=int(time.time()) + 60):
                        raise AssertionError("denied full role admitted")
                assert error.value.errno == 13
                assert manager in [p for p, _ in ns], "manager full acquisition never reached"
                assert not weak, "failed full acquisition fell back to weak"
            else:
                with proof.current(source, original, 12000, expires=int(time.time()) + 60) as (
                    v,
                    check,
                ):
                    assert v["method"] == "native-niri-continuing-peer-procfs-self-pidfd-esrch.v2"
                    assert [r["process"]["pid"] for r in v["caller"]["ancestry"]] == [
                        os.getpid(),
                        manager,
                    ]
                    c = cohorts[0]
                    assert c.full_pids == {os.getpid(), pid, protected.pid}
                    assert len(weak) == 1 and type(weak[0]) is native.AncestorGeneration
                    assert not isinstance(weak[0], native.Generation)
                    assert not hasattr(weak[0], "pidns") and not hasattr(weak[0], "userns")
                    check()
                    assert manager not in [p for p, _ in ns]
                    for p in c.full_pids:
                        calls = [fd for n, fd in ns if n == p]
                        assert len(calls) >= 3, (p, calls)
                        # Scope has its independent caller pidfd; all generations retain theirs.
                        assert len(set(calls)) == (2 if p == os.getpid() else 1)
                    assert c.ancestor(pid) is c.full(pid)  # Strong then ancestor: reuse.
                    with pytest.raises(ValueError, match="ancestor-only"):
                        c.full(manager)  # Weak then strong: refuse, never promote.
                    assert c.generations[manager] is weak[0]
                    for get in (c.full, c.ancestor):
                        with pytest.raises(ValueError, match="absent PID"):
                            get(original["pid"])
                assert weak[0].fd is None
        assert protected.poll() is None
        if peer is not None:
            assert peer.poll() is None
    finally:
        for child in (peer, protected):
            if child is not None:
                child.stdin.close()
                assert child.wait(timeout=5) == 0


@pytest.mark.parametrize("role", ["ancestor", "peer", "protected"])
def test_capability_denial_is_ancestor_only(tmp_path, role):
    action = (
        "from test_restore_exited_ancestor_native import roles; "
        f"roles('/e',int(manager['Pid']),{role!r})"
    )
    result = capability(tmp_path, action, role=role)
    print(result.stdout, result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROL: actual manager ioctl 0xff05 EACCES" in result.stdout


def test_readable_manager_control(tmp_path):
    result = capability(
        tmp_path,
        "from test_restore_exited_ancestor_native import roles; "
        "roles('/e',int(manager['Pid']),'ancestor')",
        denied=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROL: manager ioctl readable" in result.stdout


@pytest.mark.parametrize("phase", ["capacity", "prepublish"])
@pytest.mark.parametrize("drift", ["ancestor", "ancestor-window"])
def test_weak_ancestor_late_veto_preserves_fences(tmp_path, phase, drift):
    action = (
        f"from test_restore_exited_late_native import exercise; exercise('/e',{drift!r},{phase!r})"
    )
    result = capability(tmp_path, action)
    assert result.returncode == 0, result.stdout + result.stderr
