"""Installed wheel console outside checkout: real proof, no CLI/env test factory."""

import inspect
import json
import os
import shutil

import pytest
from test_restore_exited_ancestor_native import SETUP
from test_restore_exited_contract import recorded, recorded_new, recorded_self_v2
from test_restore_exited_dual_method import golden
from test_restore_exited_history import fabricate, scene, sha
from test_restore_exited_native import isolated_namespace, server

DRIVER = """
import hashlib,json,os,socket,subprocess,sys,threading,time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.store import Store
from niri_desktop_continuity import restore_exited as lifecycle
from niri_desktop_continuity import restore_exited_history as historical
from niri_desktop_continuity import restore_exited_values as v
from niri_desktop_continuity.restore_reader import ReaderStore
OLD = "native-niri-continuing-peer-pidfd-esrch.v1"
NEW = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v1"
SELF_V2 = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v2"
assert Path(native.__file__).is_relative_to(Path(sys.prefix))
assert "NIRI_SOCKET" not in os.environ
FAMILY = "associated-shell-protected-dimensions-interrupted"
"""

BODY = """
class NoNativeInjection:
    def setattr(self, obj, name, value):
        # Fabricated history uses the genuinely private canonical lock root inside this
        # test-owned namespace. No CLI/runtime proof implementation is substituted.
        assert obj is operation_lock and name == "runtime_root"
        assert operation_lock.runtime_root() == Path("/run/user/0")

root = Path("/e")
old = subprocess.Popen([sys.executable,"-I","-c","import sys;sys.stdin.buffer.read()"],stdin=subprocess.PIPE)
launched = host.process_pin(old.pid)
old.stdin.close()
assert old.wait(timeout=5) == 0
scope = native.Scope(time.monotonic()+3)
try:
    own = scope.info(os.getpid())
finally:
    scope.close()
state = scene(0)
for w in state["windows"]:
    w["pid"] = os.getpid()
values = {"Version":"fixture-version","Windows":state["windows"],"Workspaces":state["workspaces"],
          "Outputs":{"FIXTURE-1":{"name":"FIXTURE-1","logical":{"scale":1.0}}}}
with server(lambda name, _: (json.dumps({"Ok":{name:values[name]}})+"\\n").encode(), connections=3) as (identity, requests):
    peer = {"pid":os.getpid(),"start_ticks":own["process"]["start_ticks"],"ppid":own["ppid"],
            "comm":"fixture-peer","cgroup":None}
    s = fabricate(root, NoNativeInjection(), identity=identity, process=launched, peer=peer)
    console = str(Path(sys.executable).parent/"niri-desktop-continuity")
    exits = []
    def cli(args, expected=0):
        p = subprocess.run([console,"--state-root",str(s.store.root),"restore-disposition",*args],
                           cwd="/e",capture_output=True,text=True,timeout=15)
        exits.append(p.returncode)
        assert p.returncode == expected, p.stderr+p.stdout
        return json.loads(p.stdout) if p.stdout.strip() else None
    args = [s.attempt,"--family",FAMILY,"--interrupted-receipt",s.interrupted,
            "--client-result",str(s.result),"--client-exit",str(s.exit_file)]
    from niri_desktop_continuity import restore_exited
    restore_exited.inspect(s.store, s.attempt, s.interrupted, s.result, s.exit_file)
    cli(["inspect",args[0],*args[3:]], 2) # Omission is v1, never an implicit v3 selector.
    assert cli(["inspect",*args])["current_proof"] == "not-performed"
    proposed = cli(["propose",*args])
    key = proposed["plan_digest"]
    approval_args = ["approve",key,"--confirm",key,"--accept","operator-accepted-partial","--attest-client-returned"]
    before = len(requests)
    cli(approval_args, 2)
    cli([*approval_args,"--ack-platform","f"*64], 2)
    assert len(requests) == before
    approval = cli([*approval_args,"--ack-platform",proposed["platform_digest"]])["approval_digest"]
    result = cli(["apply",approval], 2)
    assert result["status"] == "operator-accepted-partial" and result["effects"] == []
    assert result["historical_effects"] == s.actions
    plan = s.store.get("plans", key)
    approved = s.store.get("approvals", approval)
    receipt = s.store.get("receipts", result["receipt_digest"])
    assert len({plan["current"]["caller"]["process"]["pid"],
                approved["caller"]["process"]["pid"], receipt["caller"]["process"]["pid"]}) == 3
    assert plan["current"]["method"] == receipt["proof_method"] == SELF_V2
    for stage in (plan["current"], approved, receipt):
        rows = stage["caller"]["ancestry"]
        assert [r["process"]["pid"] for r in rows[1:]] == [os.getpid(), os.getppid()]
        assert rows[-1]["ppid"] == 1
    # Success has exercised production's exact stable-field comparison at both stages;
    # the caller is the only excluded field, not a replaced current contextmanager.
    before = len(requests)
    assert cli(["apply",approval], 2)["historical"]
    assert cli(["inspect",*args], 2)["canonical"] == "validated"
    assert len(requests) == before
    assert s.store.pointer("last-reopened") is None
    # Separate handwritten old-method history, never generated by live admission.
    legacy_root = root/"historical-only"
    legacy_root.mkdir()
    s = fabricate(legacy_root, NoNativeInjection())
    _, old_approval, old_receipt = golden(s, method=OLD, expired=True)
    original = {p:p.read_bytes() for p in s.directory.iterdir()}
    replay = cli(["apply", old_approval], 2)
    assert replay["historical"] and replay["proof_method"] == OLD
    assert s.store.get("receipts", replay["receipt_digest"]) == old_receipt
    assert {p:p.read_bytes() for p in original} == original
    assert len(requests) == before
    print(json.dumps({"installed":True,"exits":exits,"records":11,"requests":len(requests)}), flush=True)
"""


@pytest.mark.parametrize("denied_manager", [False, True])
def test_installed_wheel_v3_default_console_and_exact_platform_ack(tmp_path, denied_manager):
    # Copy only fabricated fixture definitions, not checkout runtime or a proof factory.
    driver = (
        DRIVER
        + "\n".join(
            inspect.getsource(f)
            for f in (
                sha,
                scene,
                fabricate,
                server,
                recorded,
                recorded_new,
                recorded_self_v2,
                golden,
            )
        )
        + f"\ndenied={denied_manager!r}\nrole='ancestor'\naction={BODY!r}\n"
        + SETUP.replace('    sys.path.insert(0,"/candidate/tests")\n', "")
    )
    (tmp_path / "driver.py").write_text(driver)
    cache = os.environ.get("UV_CACHE_DIR")
    assert cache, "explicit private offline build cache required"
    shutil.copytree(cache, tmp_path / "build-cache", symlinks=True)
    code = """
import os, subprocess, sys
from pathlib import Path
os.environ["UV_CACHE_DIR"] = "/e/build-cache"
os.environ["UV_OFFLINE"] = "1"
os.environ["UV_PYTHON_DOWNLOADS"] = "never"
os.environ["UV_LINK_MODE"] = "copy"
def run(args, cwd="/e"):
    p = subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=90)
    assert p.returncode == 0, p.stderr+p.stdout
    return p
run(["uv","build","--wheel","--out-dir","/e/dist"],"/candidate")
run(["uv","venv","--python",sys.executable,"/e/installed"])
wheel = str(next(Path("/e/dist").glob("*.whl")))
run(["uv","pip","install","--python","/e/installed/bin/python","--no-deps","--offline",wheel])
# Keep this test-owned direct child as the capability-bearing manager below PID1.
os.execv("/e/installed/bin/python", ["/e/installed/bin/python","-I","-B","/e/driver.py"])
"""
    result = isolated_namespace(code, data_root=tmp_path)
    assert result.returncode == 0, result.stderr
    if denied_manager:
        assert "CONTROL: actual manager ioctl 0xff05 EACCES" in result.stdout
    outcome = json.loads(result.stdout.splitlines()[-1])
    assert outcome["installed"] is True
    assert outcome["exits"] == [2, 0, 0, 2, 2, 0, 2, 2, 2, 2]
    assert outcome["records"] == 11
