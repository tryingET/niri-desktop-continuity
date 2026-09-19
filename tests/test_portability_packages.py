"""Fabricated package sentinels; no native payloads or installed machine integration."""

from __future__ import annotations

import importlib.util
import io
import stat
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

CONTRACTS = {
    "docs/project/2026-09-06-integrated-reconstruction-design.md",
    "docs/project/2026-09-06-integrated-reconstruction-plan.md",
    "docs/project/2026-09-06-integrated-reconstruction-protocol.md",
}
BASE = {
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


def smoke():
    path = Path(__file__).resolve().parents[1] / "scripts/ci/package-smoke.py"
    spec = importlib.util.spec_from_file_location("package_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package(tmp_path, kind, extra=(), omitted=(), link=None):
    names = (BASE | CONTRACTS) - set(omitted) if kind == "sdist" else {"example/module.py"}
    names |= set(extra)
    path = tmp_path / ("fabricated.tar.gz" if kind == "sdist" else "fabricated.whl")
    if kind == "sdist":
        with tarfile.open(path, "w:gz") as archive:
            for name in sorted(names):
                entry = tarfile.TarInfo(f"fabricated-0.0/{name}")
                entry.size = len(b"fabricated")
                archive.addfile(entry, io.BytesIO(b"fabricated"))
            if link is not None:
                entry = tarfile.TarInfo("fabricated-0.0/link")
                entry.type = link
                entry.linkname = "outside"
                archive.addfile(entry)
    else:
        with zipfile.ZipFile(path, "w") as archive:
            for name in sorted(names):
                archive.writestr(name, "fabricated")
            if link is not None:
                entry = zipfile.ZipInfo("link")
                entry.create_system = 3
                mode = stat.S_IFIFO if link == tarfile.FIFOTYPE else stat.S_IFLNK
                entry.external_attr = (mode | 0o777) << 16
                archive.writestr(entry, "outside")
    return path


def test_sdist_uses_exact_portable_paths_not_recursive_basename_patterns():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert set(sdist["only-include"]) == CONTRACTS | {
        "src/",
        "tests/",
        "scripts/",
        "README.md",
        "LICENSE",
        "DESIGN.md",
        "Justfile",
        "pyproject.toml",
        "uv.lock",
        "docs/usage.md",
        "docs/architecture.md",
        "docs/recovery.md",
    }
    assert "include" not in sdist


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_portable_distribution_accepted(tmp_path, kind):
    paths = smoke().distribution_paths(package(tmp_path, kind))
    if kind == "sdist":
        assert CONTRACTS <= paths


@pytest.mark.parametrize("missing", sorted(CONTRACTS))
def test_each_linked_contract_is_required(tmp_path, missing):
    with pytest.raises(AssertionError, match="missing required files"):
        smoke().distribution_paths(package(tmp_path, "sdist", omitted=[missing]))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "name",
    [
        ".ontology",
        ".ontology/fabricated.bin",
        "nested/.ontology/fabricated.bin",
        "snapshots/fabricated.json",
        "nested/receipts/fabricated.json",
        "previews/preview.html",
        "artifacts/fabricated.bin",
        "nested/state/fabricated.json",
        "docs/_core/private.md",
        "diary/private.md",
    ],
)
def test_private_distribution_entries_rejected_without_payload_reads(
    tmp_path, monkeypatch, kind, name
):
    path = package(tmp_path, kind, extra=[name])

    def forbidden(*args, **kwargs):
        raise AssertionError("private payload must not be opened")

    monkeypatch.setattr(tarfile.TarFile, "extractfile", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    with pytest.raises(AssertionError, match="private state in distribution"):
        smoke().distribution_paths(path)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize("link", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_distribution_links_and_special_entries_rejected(tmp_path, kind, link):
    with pytest.raises(AssertionError, match="link/special entry"):
        smoke().distribution_paths(package(tmp_path, kind, link=link))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_archive_parent_escape_rejected(tmp_path, kind):
    with pytest.raises(AssertionError, match="unsafe archive path"):
        smoke().distribution_paths(package(tmp_path, kind, extra=["../escape"]))
