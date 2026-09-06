#!/usr/bin/env python3
"""Install the built wheel into an isolated environment and exercise offline rendering."""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    wheels = list((ROOT / "dist").glob("niri_desktop_continuity-*.whl"))
    if len(wheels) != 1:
        raise ValueError("package smoke requires exactly one built wheel")
    wheel = wheels[0]
    sdists = list((ROOT / "dist").glob("niri_desktop_continuity-*.tar.gz"))
    if len(sdists) != 1:
        raise ValueError("package smoke requires exactly one source archive")
    with tarfile.open(sdists[0]) as source:
        paths = {"/".join(Path(name).parts[1:]) for name in source.getnames()}
        required = {
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
        }
        assert required <= paths, f"source archive missing required files: {required - paths}"
        assert not any(
            path.startswith(("docs/_core/", "snapshots/", "previews/", "receipts/"))
            for path in paths
        )
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "niri_desktop_continuity/assets/tokens.css" in names
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
    print(
        "installed-wheel smoke passed: isolated imports/assets, offline rendering, no runtime dependencies"
    )


if __name__ == "__main__":
    main()
