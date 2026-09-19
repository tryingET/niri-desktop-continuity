#!/usr/bin/env python3
"""Install the built wheel into an isolated environment and exercise offline rendering."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDIST_REQUIRED = {
    "scripts/check-portability.py",
    "scripts/ci/package-smoke.py",
    "scripts/ci/smoke.sh",
    "scripts/ci/fast.sh",
    "scripts/ci/full.sh",
    "Justfile",
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
    "src/niri_desktop_continuity/assets/tokens.css",
    "docs/project/2026-09-06-integrated-reconstruction-design.md",
    "docs/project/2026-09-06-integrated-reconstruction-plan.md",
    "docs/project/2026-09-06-integrated-reconstruction-protocol.md",
}
PRIVATE_PARTS = {
    ".ontology",
    "_core",
    "diary",
    "state",
    "snapshots",
    "plans",
    "approvals",
    "previews",
    "receipts",
    "artifacts",
}


def distribution_paths(path):
    """Inspect archive metadata without extracting or opening private payloads."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            entries = [
                (
                    item.filename,
                    stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG, stat.S_IFDIR},
                )
                for item in archive.infolist()
            ]
    else:
        with tarfile.open(path) as archive:
            entries = [(item.name, not (item.isfile() or item.isdir())) for item in archive]
    paths = set()
    for name, unsafe_type in entries:
        parts = Path(name).parts
        assert not unsafe_type, f"unreviewed archive link/special entry: {name}"
        assert not Path(name).is_absolute() and ".." not in parts, f"unsafe archive path: {name}"
        assert not PRIVATE_PARTS.intersection(parts), f"private state in distribution: {name}"
        paths.add(name if path.suffix == ".whl" else "/".join(parts[1:]))
    if path.suffix != ".whl":
        assert SDIST_REQUIRED <= paths, (
            f"source archive missing required files: {SDIST_REQUIRED - paths}"
        )
    return paths


def reconstruction_smoke(scratch, python, env):
    spec = importlib.util.spec_from_file_location(
        "fabricated_recovery", ROOT / "tests/test_recovery_backend.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    site = Path(
        subprocess.check_output(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            cwd=scratch,
            env=env,
            text=True,
        ).strip()
    )
    console = python.parent / "niri-desktop-continuity"
    # Opaque already-scoped references, not a synthetic claim of native app support.
    three_refs = ("1" * 64, "2" * 64, "3" * 64)
    cases = (
        (False, None, False, ("c" * 64,)),
        (True, None, False, ("c" * 64,)),
        (False, "observed-image", False, ("c" * 64,)),
        (True, "capability-btop", False, ("c" * 64,)),
        (False, "capability-btop", True, ("c" * 64,)),
        (False, None, False, three_refs),
        (False, "observed-image", False, three_refs),
        (True, "capability-btop", False, three_refs),
    )
    for index, (omitted, utility, utility_only, saved_refs) in enumerate(cases):
        fake = fixture.provision(
            scratch / f"recovery-{index}",
            missing=omitted,
            utility=utility,
            utility_only=utility_only,
            saved_refs=saved_refs,
        )
        root = fake["root"]
        hooks = fixture.install_hook(site, root)  # .pth: a system sitecustomize shadows one

        def invoke(*args, status=0):
            result = subprocess.run(
                [str(console), "--state-root", str(root / "state"), *args],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == status, (args, result.stdout, result.stderr)
            return json.loads(result.stdout or result.stderr)

        source = invoke("capture")["snapshot_digest"]
        assert source == fake["snapshot_digest"]
        extra = ["--omit-association", fake["omission"]] if omitted else []
        planned = invoke(
            "plan",
            source,
            "--intent",
            "reconstruct",
            "--adapter-config",
            str(root / "config.json"),
            *extra,
        )
        key = planned["plan_digest"]
        rendered = invoke("preview", key, "--kind", "plans")
        assert "original target topology" in Path(rendered["html"]).read_text()
        accepted = ["--accept-omission", fake["omission"]] if omitted else []
        limits = []
        if utility == "capability-btop":
            utility_ref = json.loads((root / "settings.json").read_text())["observation"][
                "utilities"
            ][0]["utility_ref"]
            invoke(
                "approve",
                key,
                "--confirm",
                key,
                "--accept-losses",
                "saved-conversations-v1",
                *accepted,
                status=2,
            )
            limits = ["--accept-utility-limit", utility_ref]
        approval = invoke(
            "approve",
            key,
            "--confirm",
            key,
            "--accept-losses",
            "saved-conversations-v1",
            *accepted,
            *limits,
        )["approval_digest"]
        assert not (root / "effects.jsonl").exists()
        expected = "verified-with-accepted-omissions" if omitted else "verified"
        if limits:
            expected = "verified-with-accepted-limitations"
        result = invoke("reconstruct", approval, "--apply", "--acknowledge-non-atomic-focus")
        assert result["status"] == expected
        native_count = 0 if utility_only else len(saved_refs)
        expected_refs = [] if utility_only else sorted(saved_refs)
        assert result["coverage"]["owned_native_processes"] == native_count + int(omitted)
        assert result["coverage"]["associated_processes"] == native_count
        assert result["coverage"]["unique_saved_conversations"] == len(expected_refs)
        assert result["coverage"]["omitted_associations"] == int(omitted)
        assert [item["session_ref"] for item in result["proof"]["native"]] == expected_refs
        assert [item["process_pin_digest"] for item in result["accepted_omissions"]] == (
            [fake["omission"]] if omitted else []
        )
        assert result["overall_native_coverage_complete"] == (not omitted and not limits)
        assert result["schema"] == (
            "desktop-continuity.recovery.v2" if utility else "desktop-continuity.recovery.v1"
        )
        if utility:
            assert result["coverage"]["owned_utilities"] == 1
            assert result["overall_image_coverage_complete"] == (not limits)
            assert result["saved_conversations_recovered"] == len(expected_refs)
            assert result["accepted_utility_limits"] == ([utility_ref] if limits else [])
        assert invoke("verify", approval, "--kind", "reconstruction")["status"] == expected
        assert invoke("inspect", approval, "--kind", "reconstruction")["status"] == expected
        assert invoke("history", "--kind", "receipts")["digests"]
        invoke("reconstruct", approval, "--apply", "--acknowledge-non-atomic-focus", status=2)
        phases = [json.loads(line) for line in (root / "phases.jsonl").read_text().splitlines()]
        assert phases == ["observe", "admit", "admit", "execute", "verify", "inspect", "admit"]
        for intent in ("restart", "migrate"):
            assert invoke("plan", source, "--intent", intent)["admission"]["status"] == "blocked"
        assert [json.loads(line) for line in (root / "effects.jsonl").read_text().splitlines()] == [
            "shutdown",
            "launch",
            "layout",
        ]
        if utility:
            # Installed CLI must refuse damaged v2 accounting, retaining independent intent.
            event = fixture.address({"attempt_digest": approval, "sequence": 0, "event": "result"})
            damaged = root / "ledger/recovery-events" / (event + ".json")
            damaged.write_text("{")
            inspected = invoke("inspect", approval, "--kind", "reconstruction", status=2)
            assert inspected["interruption_evidence"][0]["outcome"] == "unresolved"
            assert inspected["interruption_evidence"][0]["intent"]["kind"] == "shutdown"
            invoke("verify", approval, "--kind", "reconstruction", status=2)
            assert damaged.read_text() == "{"

    for path in hooks:
        path.unlink()


def main():
    wheels = list((ROOT / "dist").glob("niri_desktop_continuity-*.whl"))
    if len(wheels) != 1:
        raise ValueError("package smoke requires exactly one built wheel")
    wheel = wheels[0]
    sdists = list((ROOT / "dist").glob("niri_desktop_continuity-*.tar.gz"))
    if len(sdists) != 1:
        raise ValueError("package smoke requires exactly one source archive")
    distribution_paths(sdists[0])
    names = distribution_paths(wheel)
    with zipfile.ZipFile(wheel) as archive:
        if "niri_desktop_continuity/assets/tokens.css" not in names:
            raise SystemExit("wheel is missing the packaged map stylesheet")
        metadata = archive.read(
            next(n for n in names if n.endswith(".dist-info/METADATA"))
        ).decode()
        assert "Requires-Dist:" not in metadata, "runtime must have no Python dependencies"
        assert "License-Expression: Apache-2.0" in metadata
        assert not any("snapshot" in n or "preview.html" in n for n in names)
    with tempfile.TemporaryDirectory(prefix="niri-continuity-wheel-") as temporary:
        scratch = Path(temporary)
        venv = scratch / "venv"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True)
        python = venv / "bin/python"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", "--offline", str(wheel)],
            check=True,
        )
        home = scratch / "home"
        home.mkdir(mode=0o700)
        # No compositor, company tools, user config, PYTHONPATH or agent environment in the child.
        env = {"HOME": str(home), "PATH": str(venv / "bin"), "LANG": "C.UTF-8"}
        code = """
import json
from niri_desktop_continuity.model import normalized_snapshot
from niri_desktop_continuity.store import Store
snapshot = normalized_snapshot({
    "identity": {"boot_id": "synthetic", "niri_socket": "/synthetic", "socket_inode": 1, "socket_device": 1},
    "coherent": True,
    "outputs": [{"name": "DISPLAY", "logical": {"width": 1200, "height": 800}, "current_mode": 0}],
    "workspaces": [{"id": 1, "idx": 1, "output": "DISPLAY", "is_focused": True}],
    "windows": [{"id": 1, "pid": 101, "app_id": "example-terminal", "workspace_id": 1,
                 "is_floating": False, "is_focused": True,
                 "layout": {"pos_in_scrolling_layout": [1,1], "tile_size": [800,600], "window_size": [800,600]}}],
    "processes": [], "layers": []})
print(json.dumps({"digest": Store().save_snapshot(snapshot)}))
"""
        made = subprocess.check_output(
            [str(python), "-I", "-c", code], cwd=home, env=env, text=True
        )
        digest = json.loads(made)["digest"]
        rendered = subprocess.check_output(
            [str(python), "-I", "-m", "niri_desktop_continuity", "preview", digest],
            cwd=home,
            env=env,
            text=True,
        )
        result = json.loads(rendered)
        assert "WINDOW 1" in Path(result["html"]).read_text()
        assert "<svg" in Path(result["svg"]).read_text()
        assert result["approval"] == "not-granted"
        failed = subprocess.run(
            [str(python), "-I", "-m", "niri_desktop_continuity", "capture"],
            cwd=home,
            env=env,
            capture_output=True,
            text=True,
        )
        assert failed.returncode == 2 and json.loads(failed.stderr)["status"] == "error"
        assert not list((home / ".local/state/niri-desktop-continuity/approvals").iterdir())
        reconstruction_smoke(scratch, python, env)
    print(
        "installed-wheel smoke passed: console-script v1/v2 multi-conversation/omission/utility workflows, isolated imports/assets, offline rendering, no runtime dependencies"
    )


if __name__ == "__main__":
    main()
