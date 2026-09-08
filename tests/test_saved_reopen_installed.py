"""Actual installed console scripts with a wholly fabricated native endpoint and desktop."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_recovery_backend import installation_hook
from test_saved_reopen_backend import REF, SAVED_SET, provision


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("saved-reopen-installed")
    env = dict(os.environ, UV_OFFLINE="1")
    built = root / "wheel"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(built)],
        check=True,
        capture_output=True,
        env=env,
    )
    venv = root / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv / "bin/python"),
            "--no-deps",
            str(next(built.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    site = subprocess.check_output(
        [str(venv / "bin/python"), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    ).strip()
    return root, venv, Path(site)


@pytest.mark.parametrize("present", [False, True])
def test_installed_capture_through_verify_and_noop(installed, present):
    root, venv, site = installed
    data = provision(root / ("present" if present else "missing"), present=present)
    private = data["root"]
    hook = site / "sitecustomize.py"
    hook.write_text(installation_hook(private))
    env = {
        key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def run(*args, expected=0):
        result = subprocess.run(
            [
                str(venv / "bin/niri-desktop-continuity"),
                "--state-root",
                str(private / "state"),
                *args,
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected, result.stderr
        return json.loads(result.stdout if expected == 0 else result.stderr)

    try:
        snapshot = run("capture")["snapshot_digest"]
        key = run(
            "plan",
            snapshot,
            "--intent",
            "reconstruct",
            "--mode",
            "additive",
            "--saved-set",
            SAVED_SET,
            "--adapter-config",
            str(private / "config.json"),
        )["plan_digest"]
        assert run("preview", key, "--kind", "plans")["runtime_effects"] == "none"
        approval = run(
            "approve", key, "--confirm", key, "--accept-losses", "saved-conversations-v1"
        )["approval_digest"]
        assert not (private / "effects.jsonl").exists()
        report = run("reconstruct", approval, "--apply", "--acknowledge-non-atomic-focus")
        assert report["status"] == "verified"
        assert report["saved_conversations_restored"] == int(not present)
        assert report["saved_conversations_already_present"] == int(present)
        if not present:
            events = [
                json.loads(line) for line in (private / "effects.jsonl").read_text().splitlines()
            ]
            assert [item["kind"] for item in events] == ["launch", "focus"]
            assert events[0]["target_ref"] == REF
        else:
            assert not (private / "effects.jsonl").exists()
        assert run("verify", approval, "--kind", "reconstruction")["status"] == "verified"
        assert run("inspect", approval, "--kind", "reconstruction")["status"] == "verified"
        run("reconstruct", approval, "--apply", "--acknowledge-non-atomic-focus", expected=2)
    finally:
        hook.unlink()
