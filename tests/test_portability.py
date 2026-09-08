"""Standalone source/export safety without private infrastructure or live IPC."""

from __future__ import annotations

import errno
import importlib.util
import os
import runpy
import subprocess
from pathlib import Path

import pytest

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


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    # Only fabricated scratch repositories may have their index changed by these tests.
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    subprocess.run(["git", "init", "--quiet", "--template=", str(tmp_path)], check=True)
    ignore = Path(__file__).resolve().parents[1] / ".gitignore"
    (tmp_path / ".gitignore").write_text(ignore.read_text())
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module, tmp_path


def put(root, name, content=b"fabricated"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def track(root, name):
    subprocess.run(["git", "add", "--force", "--", name], cwd=root, check=True)


def forbid_devstate_reads(monkeypatch):
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert ".ontology" not in path.parts, "development state payload must not be read"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)


def test_only_ignored_root_development_state_is_excluded(source_repo, monkeypatch):
    module, root = source_repo
    ignore_lines = (root / ".gitignore").read_text().splitlines()
    assert [line for line in ignore_lines if ".ontology" in line] == ["/.ontology/"]
    put(root, ".ontology/private.bin", b"\xff\xfe")
    forbid_devstate_reads(monkeypatch)
    assert module.check() == []
    put(root, "nested/.ontology/private.bin", b"\xff\xfe")
    assert any("nested/.ontology" in error for error in module.check())


def test_force_tracked_ignored_development_state_is_refused(source_repo, monkeypatch):
    module, root = source_repo
    put(root, ".ontology/private.bin", b"\xff\xfe")
    track(root, ".ontology/private.bin")
    forbid_devstate_reads(monkeypatch)
    assert module.check() == [
        ".ontology/private.bin: optional development state must not be tracked or distributed"
    ]


def test_force_tracked_development_state_symlink_is_refused(source_repo):
    module, root = source_repo
    target = root / "fabricated-target"
    target.mkdir()
    (root / ".ontology").symlink_to(target)
    track(root, ".ontology")
    assert any("development state" in error for error in module.check())


def test_unignored_development_state_is_refused(source_repo, monkeypatch):
    module, root = source_repo
    (root / ".gitignore").write_text("")
    put(root, ".ontology/private.bin", b"\xff\xfe")
    forbid_devstate_reads(monkeypatch)
    assert any("development state" in error for error in module.check())


@pytest.mark.parametrize(
    "name",
    [
        ".ontology",
        ".ontology/private.bin",
        "nested/.ontology/x",
        ".venv/.ontology/x",
        "dist/.ontology/x",
    ],
)
def test_export_development_state_is_refused(tmp_path, monkeypatch, name):
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / ".gitignore").write_text("/.ontology/\n")
    put(tmp_path, name, b"\xff\xfe")
    forbid_devstate_reads(monkeypatch)
    assert any("development state" in error for error in module.check())


@pytest.mark.parametrize("tracked", [False, True])
@pytest.mark.parametrize("kind", ["snapshots", "previews", "receipts", "artifacts", "state"])
def test_runtime_leaks_refused_even_when_ignored(source_repo, kind, tracked):
    module, root = source_repo
    name = f"{kind}/fabricated.json"
    put(root, name, b"{}")
    if tracked:
        track(root, name)
    assert any("runtime state" in error for error in module.check())


@pytest.mark.parametrize("tracked", [False, True])
@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xfe", "binary artifact"),
        ("/".join(["", "home", "fabricated", "private"]).encode(), "home path"),
    ],
)
def test_other_private_inputs_still_checked(source_repo, tracked, content, message):
    module, root = source_repo
    name = ".other-private/input"
    put(root, name, content)
    # An arbitrary additional ignore must not become another private-state exemption.
    with (root / ".gitignore").open("a") as ignore:
        ignore.write("/.other-private/\n")
    if tracked:
        track(root, name)
    assert any(message in error for error in module.check())


@pytest.mark.parametrize("git", [False, True])
@pytest.mark.parametrize("name", [".ontology", ".venv", "link", "dangling"])
def test_source_directory_symlinks_never_bypassed(source_repo, tmp_path, monkeypatch, git, name):
    module, repo = source_repo
    root = repo if git else tmp_path / "export"
    root.mkdir(exist_ok=True)
    monkeypatch.setattr(module, "ROOT", root)
    target = tmp_path / "external"
    target.mkdir()
    (root / name).symlink_to(target if name != "dangling" else target / "absent")
    assert module.check()


@pytest.fixture(params=[False, True], ids=["export", "git"])
def traversal_source(request, source_repo, monkeypatch):
    module, repo = source_repo
    root = repo if request.param else repo / "export"
    root.mkdir(exist_ok=True)
    monkeypatch.setattr(module, "ROOT", root)
    return module, root


def test_unreadable_ordinary_directory_fails_closed(traversal_source):
    module, root = traversal_source
    secret = put(
        root, "ordinary/fabricated.txt", "/".join(["", "home", "example", "private"]).encode()
    )
    directory = secret.parent
    original_mode = directory.stat().st_mode
    directory.chmod(0)
    try:
        try:
            with os.scandir(directory):
                pass
        except PermissionError:
            pass
        else:
            pytest.skip("test process bypasses directory permissions; injected errors cover this")
        assert module.check() == ["source traversal failed: unable to enumerate source inputs"]
    finally:
        directory.chmod(original_mode)
    assert module.check() == ["ordinary/fabricated.txt: hardcoded user home path"]


@pytest.mark.parametrize("directory", ["ordinary", ".hidden", "."])
@pytest.mark.parametrize("code", [errno.EACCES, errno.ENOENT, errno.ENOTDIR])
def test_scandir_errors_fail_closed(traversal_source, monkeypatch, directory, code):
    module, root = traversal_source
    target = root / directory
    target.mkdir(exist_ok=True)
    put(target, "fabricated.txt", b"fabricated")
    original = os.scandir
    attempted = []

    def failing(path):
        if Path(path) == target:
            attempted.append(path)
            # Simulates permission loss or disappearance/replacement after parent enumeration.
            raise OSError(code, "fabricated private diagnostic", str(target))
        return original(path)

    monkeypatch.setattr(os, "scandir", failing)
    assert module.check() == ["source traversal failed: unable to enumerate source inputs"]
    assert len(attempted) == 1  # no retry or permission-dependent passing proxy


def test_ignored_root_development_state_is_not_scanned(source_repo, monkeypatch):
    module, root = source_repo
    put(root, ".ontology/private.bin", b"\xff\xfe")
    original = os.scandir

    def guarded(path):
        assert ".ontology" not in Path(path).parts, "must prune before directory enumeration"
        return original(path)

    monkeypatch.setattr(os, "scandir", guarded)
    forbid_devstate_reads(monkeypatch)
    assert module.check() == []


def test_traversal_failure_cli_is_static_and_nonzero(traversal_source, monkeypatch, capsys):
    _, root = traversal_source
    source = Path(__file__).resolve().parents[1] / "scripts/check-portability.py"
    script = put(root, "scripts/check-portability.py", source.read_bytes())
    original = os.scandir

    def failing(path):
        if Path(path) == root:
            raise PermissionError(errno.EACCES, "fabricated private diagnostic", str(root))
        return original(path)

    monkeypatch.setattr(os, "scandir", failing)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(script), run_name="__main__")
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == "source traversal failed: unable to enumerate source inputs\n"
    assert output.err == ""


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
