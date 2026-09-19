"""Actual installed console scripts with a wholly fabricated native endpoint and desktop."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_recovery_backend import install_hook, install_startup_code
from test_recovery_review_regressions import repin
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
@pytest.mark.parametrize("projected", [False, True])
def test_installed_capture_through_verify_and_noop(installed, present, projected):
    root, venv, site = installed
    name = ("present" if present else "missing") + ("-projected" if projected else "")
    data = provision(root / name, present=present)
    private = data["root"]
    projection = {}
    if projected:
        projection = {
            "grouping": {
                "schema": "desktop-continuity.saved-grouping.v1",
                "saved_set": SAVED_SET,
                "groups": [
                    {
                        "session_refs": [REF],
                        "provenance": "requested",
                        "reviewed": True,
                        "sequence": "desired-creation",
                    }
                ],
            },
            "diagnostics": {
                "schema": "desktop-continuity.saved-diagnostics.v1",
                "reasons": [],
                "capacity": "available",
            },
        }
        settings = json.loads((private / "settings.json").read_text())
        settings["observation"].update(projection)
        repin(data, settings)
    hooks = install_hook(site, private)
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
        preview = run("preview", key, "--kind", "plans")
        assert preview["runtime_effects"] == "none"
        rendered = Path(preview["html"]).read_text()
        assert ("Desired shared-window groups" in rendered) is projected
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
        verified = run("verify", approval, "--kind", "reconstruction")
        inspected = run("inspect", approval, "--kind", "reconstruction")
        assert verified["status"] == inspected["status"] == "verified"
        for field in ("grouping", "diagnostics"):
            for output in (report, verified, inspected):
                assert (field in output) is projected
                if projected:
                    assert output[field] == projection[field]
        assert "failed does not mean zero effects" in inspected["recovery_guidance"][0]
        run("reconstruct", approval, "--apply", "--acknowledge-non-atomic-focus", expected=2)
    finally:
        for path in hooks:
            path.unlink()


def test_injected_fixtures_load_even_behind_a_system_sitecustomize(tmp_path):
    # Debian/Ubuntu Pythons ship /usr/lib/python3.x/sitecustomize.py; PYTHONPATH reproduces it.
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True
    )
    python = str(venv / "bin/python")
    site = Path(
        subprocess.check_output(
            [python, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True
        ).strip()
    )
    system = tmp_path / "system"
    system.mkdir()
    (system / "sitecustomize.py").write_text("")
    probe = "import builtins; print(getattr(builtins, 'NDC_HOOK', 'missing'))"
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(system)}

    def loaded():
        return subprocess.run(
            [python, "-c", probe], env=env, capture_output=True, text=True, check=True
        ).stdout

    code = "import builtins\nbuiltins.NDC_HOOK = 'loaded'\n"
    (site / "sitecustomize.py").write_text(code)
    assert loaded() == "missing\n"  # the old injection: shadowed, the CLI would run for real
    (site / "sitecustomize.py").unlink()
    install_startup_code(site, code)
    assert loaded() == "loaded\n"
