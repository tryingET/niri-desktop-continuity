#!/usr/bin/env python3
"""Fail on home-specific paths, leaked runtime state, or nonportable runtime imports."""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_paths():
    if (ROOT / ".git").exists():
        return (
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
            )
            .decode()
            .split("\0")
        )
    # Source archives have no Git metadata. Exclude build/tool caches, not runtime-state leaks.
    excluded = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "build"}
    paths = []
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in excluded]
        paths.extend(str((Path(directory) / name).relative_to(ROOT)) for name in files)
    return paths


def check() -> list[str]:
    paths = source_paths()
    failures = []
    home_path = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        if path.is_symlink():
            failures.append(f"{name}: unreviewed source symlink")
            continue
        if not path.is_file():
            continue
        if any(
            part in {"snapshots", "previews", "receipts"} for part in path.relative_to(ROOT).parts
        ):
            failures.append(f"{name}: runtime state must not be distributed")
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
