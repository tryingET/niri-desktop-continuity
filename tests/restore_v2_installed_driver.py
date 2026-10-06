"""Copied outside checkout by the installed-wheel test; no test-package or source imports."""

import contextlib
import io
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import niri_desktop_continuity
from niri_desktop_continuity import restore
from niri_desktop_continuity import restore_disposition_cli as disposition_cli
from niri_desktop_continuity import restore_disposition_evidence as e
from niri_desktop_continuity import restore_host as host

assert Path(niri_desktop_continuity.__file__).is_relative_to(Path(sys.prefix))
assert "NIRI_SOCKET" not in os.environ
root, fixture, console = map(Path, sys.argv[1:])
binary, cwd = root / "ghostty", root / "host-cwd"
cwd.mkdir(mode=0o700)
directory_pin = {"device": cwd.stat().st_dev, "inode": cwd.stat().st_ino}
argv = [
    str(binary),
    "--config-default-files=false",
    "--gtk-single-instance=false",
    "--initial-window=true",
    "--working-directory=" + str(cwd),
]
# ubs:ignore[py.security.command-injection,python.taint.command] -- Locally built test ELF.
child = subprocess.Popen(
    argv,
    cwd=cwd,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    close_fds=True,
)


def fail(*_):
    raise AssertionError("installed accounting invoked an effect")


pytest = SimpleNamespace(fail=fail)
patch = SimpleNamespace(setattr=setattr)
original = host.Process, host.Image, e.Directory, e.controller_pids


def independent_process_pin():
    fields = Path(f"/proc/{child.pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "pid": child.pid,
        "start_ticks": int(fields[19]),
    }


try:
    exec(compile(fixture.read_text(), str(fixture), "exec"), globals())  # ubs:ignore[py.security.eval-exec-usage,python.taint.eval,py.eval-exec] -- Test-owned fixture.  # fmt: skip
    s = globals()["make_unassociated"](globals()["handwritten"](root, patch))
    assert (host.Process, host.Image, e.Directory, e.controller_pids) == original
    assert s.store.get("receipts", s.interrupted)["windows"][0]["status"] == "launch-indeterminate"
    disposition_cli.compositor_identity = lambda: s.identity
    restore.compositor_identity = lambda: s.identity
    e.observe = s.observe  # ONLY fabricated IPC; actual ELF/proc/argv/cwd/pidfd proofs remain.
    restore.LiveDesktop.spawn = fail
    restore.LiveDesktop.action = fail
    subprocess.Popen = fail
    before = {p: p.read_bytes() for p in s.directory.iterdir()}
    exits = []

    def command(args, expected):
        sys.argv = [str(console), "--state-root", str(s.store.root), *args]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                runpy.run_path(str(console), run_name="__main__")
            except SystemExit as exc:
                assert exc.code == expected, (exc.code, out.getvalue())
                exits.append(exc.code)
            else:
                raise AssertionError("console did not return an exit status")
        return json.loads(out.getvalue())

    common = [
        s.attempt,
        "--family",
        "exec-observed-unassociated",
        "--interrupted-receipt",
        s.interrupted,
        "--client-result",
        str(s.result),
        "--client-exit",
        str(s.exit_file),
    ]
    inspected = command(["restore-disposition", "inspect", *common], 0)
    assert inspected["approval"] == "not-granted"
    plan = command(["restore-disposition", "propose", *common], 0)["plan_digest"]
    body = s.store.get("plans", plan)
    records = [json.loads((s.directory / f"{i:08d}.json").read_text()) for i in range(5)]
    prepared = s.store.get("receipts", records[0]["receipt"])
    exec_observed = s.store.get("receipts", records[4]["receipt"])
    assert body["segment"] == {
        "start": 0,
        "count": 5,
        "previous": None,
        "exec_intent": records[3]["receipt"],
        "exec_observed": records[4]["receipt"],
        "process_receipt": globals()["sha"](exec_observed["evidence"]),
        "baseline_digest": globals()["sha"](prepared["plan"]["baseline"]),
    }
    assert body["limits"]["historical_association"] == "not-recorded"
    assert body["limits"]["outcome"] == "unresolved"
    approval = command(
        [
            "restore-disposition",
            "approve",
            plan,
            "--confirm",
            plan,
            "--accept",
            "operator-accepted-partial",
            "--attest-client-returned",
        ],
        0,
    )["approval_digest"]
    result = command(["restore-disposition", "apply", approval], 2)
    assert result["historical_association"] == "not-recorded" and result["effects"] == []
    assert result["outcome"] == "unresolved"
    e.observe = fail
    assert command(["restore-disposition", "apply", approval], 2)["historical"]
    assert command(["restore-disposition", "inspect", *common], 2)["admission"] == "not-granted"
    replay = command(["restore", "--apply", s.source], 2)
    assert replay["historical"] and replay["effects"] == []
    assert {p: p.read_bytes() for p in before} == before
    assert len(list(s.directory.iterdir())) == 6
    assert s.store.pointer("last-reopened") is None
    assert child.poll() is None
    (root / "outcome.json").write_text(
        json.dumps(
            {
                "installed": True,
                "native_desktop": False,
                "default_process_proofs": True,
                "exits": exits,
                "records": 6,
                "status": result["status"],
            }
        )
    )
finally:
    child.stdin.close()  # Fixture-only cooperative EOF, never a product termination action.
    assert child.wait(timeout=10) == 0
