"""Standalone source/export safety without private infrastructure or live IPC."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from niri_desktop_continuity import probe
from niri_desktop_continuity.store import default_root


def checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check-portability.py"
    spec = importlib.util.spec_from_file_location("portability_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_without_git_and_private_path_detection(tmp_path, monkeypatch):
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "README.md").write_text("A portable tool.")
    assert module.check() == []
    (tmp_path / "README.md").write_text("/".join(["", "home", "example", "private"]))
    assert any("home path" in error for error in module.check())
    (tmp_path / "README.md").write_text("A portable tool.")
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots/example.json").write_text("{}")
    assert any("runtime state" in error for error in module.check())


def test_private_root_is_independent(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_root() == tmp_path / "niri-desktop-continuity"


def test_discovered_binary_is_never_executed(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("a discovered application must not be executed")

    monkeypatch.setattr(probe.subprocess, "run", forbidden)
    metadata = probe.executable_info(os.getpid(), {})
    assert metadata["version"] is None
    assert len(metadata["exe_sha256"]) == 64


def test_export_rejects_symlinks_and_binary_payload(tmp_path, monkeypatch):
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "binary").write_bytes(b"\xff\xfe")
    (tmp_path / "link").symlink_to(tmp_path / "binary")
    errors = module.check()
    assert any("binary artifact" in error for error in errors)
    assert any("symlink" in error for error in errors)
