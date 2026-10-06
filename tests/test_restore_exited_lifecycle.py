"""Full real v3 proof in test-owned Linux namespaces, with handwritten fake Niri IPC."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_restore_exited_history import FAMILY, fabricate, scene
from test_restore_exited_native import isolated_namespace, server

from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host


def exercise(root):
    from niri_desktop_continuity import operation_lock, restore
    from niri_desktop_continuity import restore_history as history

    assert "NIRI_SOCKET" not in os.environ
    root = Path(root)
    with pytest.MonkeyPatch.context() as patch:
        exited = subprocess.Popen(
            [sys.executable, "-I", "-c", "import sys; sys.stdin.buffer.read()"],
            stdin=subprocess.PIPE,
        )
        launched = host.process_pin(exited.pid)
        exited.stdin.close()
        assert exited.wait(timeout=5) == 0
        scope = native.Scope(time.monotonic() + 3)
        try:
            own = scope.info(os.getpid())
        finally:
            scope.close()
        state = scene(0)
        for w in state["windows"]:
            w["pid"] = os.getpid()
        output = {"FIXTURE-1": {"name": "FIXTURE-1", "logical": {"scale": 1.0}}}
        values = {
            "Version": "fixture-version",
            "Windows": state["windows"],
            "Workspaces": state["workspaces"],
            "Outputs": output,
        }
        with server(
            lambda name, _: (json.dumps({"Ok": {name: values[name]}}) + "\n").encode(),
            connections=3,
        ) as (identity, requests):
            peer = {
                "pid": os.getpid(),
                "start_ticks": own["process"]["start_ticks"],
                "ppid": own["ppid"],
                "comm": "not-selected-by-name",
                "cgroup": None,
            }
            s = fabricate(root, patch, identity=identity, process=launched, peer=peer)
            original = {p: p.read_bytes() for p in s.directory.iterdir()}
            witness = s.result.read_bytes()
            runtime = root / "runtime"
            package = str(Path(native.__file__).parents[1])

            def cli(args, expected_code=0):
                code = f"""
import sys,json
from pathlib import Path
sys.path.insert(0, {package!r})
from niri_desktop_continuity import cli, operation_lock
operation_lock.runtime_root = lambda: Path({str(runtime)!r})
value, status = cli.run(cli.parser().parse_args({["--state-root", str(s.store.root), "restore-disposition", *args]!r}))
print(json.dumps(value))
raise SystemExit(status)
"""
                p = subprocess.run(
                    [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=15
                )
                assert p.returncode == expected_code, p.stderr
                return json.loads(p.stdout)

            arguments = [
                s.attempt,
                "--family",
                FAMILY,
                "--interrupted-receipt",
                s.interrupted,
                "--client-result",
                str(s.result),
                "--client-exit",
                str(s.exit_file),
            ]
            assert cli(["inspect", *arguments])["current_proof"] == "not-performed"
            proposed = cli(["propose", *arguments])
            plan_key = proposed["plan_digest"]
            approved = cli(
                [
                    "approve",
                    plan_key,
                    "--confirm",
                    plan_key,
                    "--accept",
                    "operator-accepted-partial",
                    "--attest-client-returned",
                    "--ack-platform",
                    proposed["platform_digest"],
                ]
            )
            approval_key = approved["approval_digest"]
            result = cli(["apply", approval_key], 2)
            assert result["effects"] == [] and result["historical_effects"] == s.actions
            assert result["historical_completion"] == "unproved"
            plan = s.store.get("plans", plan_key)
            approval = s.store.get("approvals", approval_key)
            receipt = s.store.get("receipts", result["receipt_digest"])
            assert (
                len(
                    {
                        plan["current"]["caller"]["process"]["pid"],
                        approval["caller"]["process"]["pid"],
                        receipt["caller"]["process"]["pid"],
                    }
                )
                == 3
            )
            before = len(requests)
            assert cli(["apply", approval_key], 2)["historical"] is True
            assert cli(["inspect", *arguments], 2)["canonical"] == "validated"
            assert len(requests) == before
            assert {p: p.read_bytes() for p in original} == original
            assert s.result.read_bytes() == witness
            assert s.store.pointer("last-reopened") is None
            with operation_lock.operation_lock(identity):
                assert history.admit(identity)[1] is None
            replay = restore.restore(
                s.store,
                s.source,
                object(),
                apply=True,
                observe=lambda: pytest.fail("historical replay must not observe"),
            )
            assert replay["effects"] == [] and replay["historical_effects"] == s.actions
            assert len(requests) == before
            from test_restore_exited_executor import continuation_then_diagnostic

            outcomes = continuation_then_diagnostic(s, root, patch)
            print(
                json.dumps(
                    {
                        "requests": len(requests),
                        "status": result["status"],
                        "records": 11,
                        **outcomes,
                    }
                )
            )


def test_given_legacy_ten_when_real_stage_callers_account_then_historical_replay(tmp_path):
    # Test code may establish an isolated namespace. Production proof NEVER changes namespace.
    code = f"""
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_restore_exited_lifecycle import exercise
exercise({str(tmp_path)!r})
"""
    result = isolated_namespace(code, data_root=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "operator-accepted-partial"
