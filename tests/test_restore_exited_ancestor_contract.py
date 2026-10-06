"""Exclusion-only generations: handwritten drift, route and lineage oracles."""

import os
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_restore_exited_measurements import cooperative
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import restore_exited_scope as native


def negative(case):
    child = cooperative()
    scope = native.Scope(time.monotonic() + 10)
    generation = native.AncestorGeneration(scope, child.pid)
    fired = []
    original_info, original_directory, original_leaf = scope.info, scope.directory, scope.read_leaf
    directory_inode = os.fstat(generation.directory[0]).st_ino

    def info(pid, **kw):
        row = original_info(pid, **kw)
        if pid == child.pid and case in ("start", "parent", "boot"):
            fired.append(case)
            row = deepcopy(row)
            if case == "parent":
                row["ppid"] += 1
            elif case == "start":
                row["process"]["start_ticks"] += 1
            else:
                row["process"]["boot_id"] = "other"
        return row

    def directory(stack, pid):
        fd, identity = original_directory(stack, pid)
        if pid == child.pid and case == "same-tick-reuse":
            fired.append(case)
            # Independent adversarial oracle: tuple and live pidfd stay identical,
            # but the fresh numeric route belongs to another retained struct pid.
            changed = list(identity)
            changed[1] += 1
            return fd, tuple(changed)
        return fd, identity

    def leaf(parent, name, uid=None):
        raw = original_leaf(parent, name, uid)
        if os.fstat(parent).st_ino != directory_inode or name != "status":
            return raw
        fields = {
            "aliases": b"NSpid: " + str(child.pid).encode() + b" " + str(child.pid).encode(),
            "tid": b"Tgid: 999999",
            "uid": b"Uid: 999 999 999 999",
            "missing": b"",
            "duplicate": b"NStgid: "
            + str(child.pid).encode()
            + b"\nNStgid: "
            + str(child.pid).encode(),
        }
        if case == "unreadable":
            fired.append(case)
            raise PermissionError("ancestor metadata unreadable")
        if case in fields:
            fired.append(case)
            field = {"aliases": b"NSpid:", "tid": b"Tgid:", "uid": b"Uid:"}.get(case, b"NStgid:")
            return (
                b"\n".join(
                    fields[case] if line.startswith(field) else line for line in raw.splitlines()
                )
                + b"\n"
            )
        return raw

    try:
        if case in ("death", "zombie"):
            child.stdin.close()
            if case == "zombie":
                os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
            else:
                assert child.wait(timeout=5) == 0
            fired.append(case)
        if case in ("directory-graft", "stat-graft", "status-graft"):
            path = (
                f"/proc/{child.pid}"
                + {"directory-graft": "", "stat-graft": "/stat", "status-graft": "/status"}[case]
            )
            subprocess.run(["mount", "--bind", path, path], check=True)
            fired.append(case)
        with (
            patch.object(scope, "info", info),
            patch.object(scope, "directory", directory),
            patch.object(scope, "read_leaf", leaf),
        ):
            with pytest.raises((ValueError, OSError)) as error:
                generation.check()
        assert fired, "intended ancestor fault never fired"
        text = str(error.value)
        if case in ("death", "zombie"):
            assert "process generation exited" in text, text
        elif case == "same-tick-reuse":
            assert "directory generation changed" in text, text
            assert original_info(child.pid) == generation.row  # Equal tuple is insufficient.
        elif case.endswith("-graft"):
            assert "foreign proc mount" in text, text
        elif case in ("start", "parent", "boot"):
            assert "ancestor generation/parent/UID changed" in text, text
        elif case == "unreadable":
            assert "ancestor metadata unreadable" in text
        else:
            assert "status" in text or "inconsistent proc" in text, text
    finally:
        generation.close()
        scope.close()
        if not child.stdin.closed:
            child.stdin.close()
        assert child.wait(timeout=5) == 0


@pytest.mark.parametrize(
    "case",
    [
        "aliases",
        "tid",
        "uid",
        "missing",
        "duplicate",
        "unreadable",
        "start",
        "parent",
        "boot",
        "same-tick-reuse",
        "death",
        "zombie",
        "directory-graft",
        "stat-graft",
        "status-graft",
    ],
)
def test_weak_generation_negatives_reach_intended_predicate(case):
    result = isolated_namespace(f"""
sys.path.insert(0,{str(Path(__file__).parent)!r})
from test_restore_exited_ancestor_contract import negative
negative({case!r})
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("case", ["gap", "cycle", "overlong", "zero"])
def test_handwritten_incomplete_chain_never_becomes_authority(case):
    scope = SimpleNamespace(caller_pid=42, boot="fixture")
    called = []

    def acquire(pid):
        called.append(pid)
        if case == "gap" and len(called) == 2:
            raise ValueError("missing ancestor")
        if case == "zero" and pid == 0:
            raise ValueError("invalid bounded integer")
        parent = {"cycle": 42, "zero": 0}.get(case, pid + 1)
        row = {"process": {"boot_id": "fixture", "pid": pid, "start_ticks": 1}, "ppid": parent}
        return SimpleNamespace(row=row, check=lambda: None)

    with pytest.raises(ValueError) as error:
        native.ancestry(scope, acquire)
    assert called[0] == 42
    if case == "overlong":
        assert len(called) == 128 and "cyclic caller ancestry" in str(error.value)
    elif case == "cycle":
        assert called == [42] and "cyclic caller ancestry" in str(error.value)
    elif case == "gap":
        assert called == [42, 43] and str(error.value) == "missing ancestor"
    else:
        assert called == [42, 0] and str(error.value) == "invalid bounded integer"


def test_real_reparenting_retains_pidfd_but_vetoes_parent():
    result = isolated_namespace(r"""
import os,subprocess,time
from niri_desktop_continuity.restore_exited_scope import Scope,AncestorGeneration
readfd, writefd = os.pipe()
child_code = "import os,sys;os.read(int(sys.argv[1]),1)"
manager_code = ("import subprocess,sys; p=subprocess.Popen([sys.executable,'-I','-c',"+
                repr(child_code)+",sys.argv[1]],pass_fds=[int(sys.argv[1])]); "
                "print(p.pid,flush=True);sys.stdin.buffer.read()")
manager = subprocess.Popen([sys.executable,'-I','-c',manager_code,str(readfd)],
                           pass_fds=[readfd],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
os.close(readfd)
pid = int(manager.stdout.readline())
scope = Scope(time.monotonic()+10)
generation = AncestorGeneration(scope,pid)
try:
    assert generation.row['ppid'] == manager.pid
    manager.stdin.close()
    assert manager.wait(timeout=5) == 0
    scope.live(generation.fd)  # Still exactly the held live generation.
    assert scope.info(pid)['ppid'] == 1
    try:
        generation.check()
    except ValueError as error:
        assert 'ancestor generation/parent/UID changed' in str(error),str(error)
    else:
        raise AssertionError('real reparenting accepted')
finally:
    os.close(writefd)  # Cooperative EOF only, not product process cleanup.
    generation.close();scope.close();manager.stdout.close()
""")
    assert result.returncode == 0, result.stderr


def test_ancestor_pidfd_zero_has_explicit_owned_lifetime():
    result = isolated_namespace(r"""
import os,time
from unittest.mock import patch
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_exited_scope import Scope,AncestorGeneration
scope=Scope(time.monotonic()+10)
real=host.open_pidfd
fired=[]
def pidfd(pid):
    fd=real(pid)
    os.dup2(fd,0,inheritable=False);os.close(fd)
    fired.append(pid)
    return 0
try:
    with patch.object(host,'open_pidfd',pidfd):
        ancestor=AncestorGeneration(scope,os.getpid())
    assert ancestor.fd == 0 and fired == [os.getpid()]
    ancestor.check();ancestor.close()
    try:os.fstat(0)
    except OSError:pass
    else:raise AssertionError('ancestor pidfd zero leaked')
finally:scope.close()
""")
    assert result.returncode == 0, result.stderr


def test_weak_owned_teardown_attempts_all_closes_preserving_primary():
    result = isolated_namespace(r"""
import os,time
from unittest.mock import patch
from niri_desktop_continuity.restore_exited_scope import Scope,AncestorGeneration
from niri_desktop_continuity.restore_exited_resources import resources
scope=Scope(time.monotonic()+10)
generation=AncestorGeneration(scope,os.getpid())
owned={generation.fd,generation.directory[0]}
closed=[]
real=os.close
def close(fd):
    assert fd in owned and fd not in closed, 'unexpected close/retry'
    real(fd);closed.append(fd)
    raise OSError('weak-close-'+str(fd))
try:
    try:
        with patch('os.close',close), resources() as stack:
            stack.callback(generation.close)
            raise KeyboardInterrupt('weak-primary')
    except KeyboardInterrupt as error:
        pending,seen,messages=[error],set(),[]
        while pending:
            item=pending.pop()
            if id(item) in seen:continue
            seen.add(id(item));messages.append(str(item))
            pending.extend(getattr(item,'exceptions',()))
            pending.extend(x for x in (item.__cause__,item.__context__) if x is not None)
        assert 'weak-primary' in messages
        assert {m for m in messages if m.startswith('weak-close-')} == {'weak-close-'+str(fd) for fd in owned}
    else:raise AssertionError('primary swallowed')
    assert set(closed)==owned and len(closed)==2
    generation.close()  # Already retired ownership, never retry the integers.
    assert len(closed)==2
finally:scope.close()
""")
    assert result.returncode == 0, result.stderr
