#!/usr/bin/env python3
"""Fail on home-specific paths, leaked runtime state, or nonportable runtime imports."""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PARTS = {"state", "snapshots", "plans", "approvals", "previews", "receipts", "artifacts"}


def source_paths():
    git = (ROOT / ".git").exists()
    paths = []
    ignore_devstate = False
    if git:
        # The index is independent of ignore rules, including forced additions and missing files.
        paths.extend(
            subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
        )
        ignore_devstate = (
            subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", ".ontology/"], cwd=ROOT, check=False
            ).returncode
            == 0
        )
    # Walk untracked inputs too: arbitrary ignore rules must not hide runtime leaks.
    # Never descend into private state, even when it is a rejected input.
    excluded = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "build"}

    def fail_walk(error: OSError) -> None:
        # os.walk otherwise suppresses scandir failures and yields an incomplete inventory.
        raise error

    for directory, dirs, files in os.walk(ROOT, followlinks=False, onerror=fail_walk):
        for name in list(dirs):
            path = Path(directory) / name
            relative = path.relative_to(ROOT)
            if path.is_symlink():
                paths.append(str(relative))
            elif relative == Path(".ontology") and ignore_devstate:
                pass
            elif name == ".ontology" or name in RUNTIME_PARTS:
                paths.append(str(relative))
            elif git and (name in excluded or relative == Path("docs/_core")):
                pass
            else:
                continue
            dirs.remove(name)
        paths.extend(str((Path(directory) / name).relative_to(ROOT)) for name in files)
    return paths


def check() -> list[str]:
    try:
        paths = source_paths()
    except OSError:
        # Do not expose OS exception text, absolute paths or a partial-scan success.
        return ["source traversal failed: unable to enumerate source inputs"]
    failures = []
    home_path = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        parts = Path(name).parts
        if ".ontology" in parts:
            failures.append(
                f"{name}: optional development state must not be tracked or distributed"
            )
            continue
        if any(part in RUNTIME_PARTS for part in parts):
            failures.append(f"{name}: runtime state must not be distributed")
            continue
        if any(ROOT.joinpath(*parts[:end]).is_symlink() for end in range(1, len(parts) + 1)):
            failures.append(f"{name}: unreviewed source symlink")
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{name}: unreviewed binary artifact")
            continue
        if home_path.search(content):
            failures.append(f"{name}: hardcoded user home path")
        if name.startswith("src/") and path.suffix == ".py":
            try:
                tree = ast.parse(content, feature_version=(3, 11))
            except SyntaxError:
                failures.append(f"{name}: not Python 3.11 syntax")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    module = (node.module or "").split(".")[0]
                    if module.startswith("workstation_"):
                        failures.append(f"{name}: external machine-integration dependency")
    return failures


if __name__ == "__main__":
    errors = check()
    print("\n".join(errors) if errors else "portable-source check passed")
    raise SystemExit(bool(errors))
