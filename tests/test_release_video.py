"""Execute release shell steps with fabricated artifacts and a fake gh, never a network call."""

from __future__ import annotations

import hashlib
import os
import re
import runpy
import subprocess
import textwrap
import unittest
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="release workflow is checkout-only")


def test_announcement_timing_regressions_run_in_the_checkout_gate():
    tests = runpy.run_path(str(WORKFLOW.parents[2] / "docs/announce/test_build.py"))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests["ReadingTimeTests"])
    result = unittest.TestResult()
    suite.run(result)
    assert result.testsRun == 5
    assert result.wasSuccessful(), result.failures + result.errors


def step(name):
    pattern = rf"^      - name: {re.escape(name)}\n        run: \|\n((?:          .*\n)+)"
    found = re.search(pattern, WORKFLOW.read_text(), re.M)
    assert found, f"release workflow needs step: {name}"
    return textwrap.dedent(found[1])


def artifacts(root, video):
    dist = root / "dist"
    dist.mkdir()
    values = {"example.whl": b"fabricated wheel", "example.tar.gz": b"fabricated source"}
    for name, value in values.items():
        (dist / name).write_bytes(value)
    if video:
        source = root / "docs/announce/niri-desktop-continuity-9.8.7.mp4"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"fabricated video")
        values[source.name] = source.read_bytes()
    return values


def run(script, root, **extra):
    env = {**os.environ, "GITHUB_REF_NAME": "v9.8.7", **extra}
    subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", script], cwd=root, env=env, check=True, timeout=30
    )


@pytest.mark.parametrize("video", [False, True])
def test_optional_video_and_packages_are_all_checksummed(tmp_path, video):
    expected = artifacts(tmp_path, video)
    run(step("Copy the optional announcement video"), tmp_path)
    run(step("Checksum every release asset"), tmp_path)
    lines = (tmp_path / "dist/SHA256SUMS").read_text().splitlines()
    actual = {line.split()[-1]: line.split()[0] for line in lines}
    assert actual == {name: hashlib.sha256(value).hexdigest() for name, value in expected.items()}


@pytest.mark.parametrize("video", [False, True])
def test_pypi_receives_distributions_only(tmp_path, video):
    artifacts(tmp_path, video)
    run(step("Copy the optional announcement video"), tmp_path)
    for name in ("SHA256SUMS", "RELEASE_NOTES.md"):
        (tmp_path / "dist" / name).write_text("fabricated ancillary asset")
    run(step("Keep only distributions for PyPI"), tmp_path)
    assert {p.name for p in (tmp_path / "dist").iterdir()} == {"example.whl", "example.tar.gz"}


@pytest.mark.parametrize("video", [False, True])
def test_video_is_attached_at_immutable_release_creation(tmp_path, video):
    artifacts(tmp_path, video)
    run(step("Copy the optional announcement video"), tmp_path)
    for name in ("SHA256SUMS", "RELEASE_NOTES.md"):
        (tmp_path / "dist" / name).write_text("fabricated ancillary asset")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$GH_ARGUMENTS"\n')
    gh.chmod(0o755)
    arguments = tmp_path / "gh-arguments"
    run(
        step("Create the immutable release with all assets"),
        tmp_path,
        PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        GH_ARGUMENTS=str(arguments),
        GITHUB_REPOSITORY="example/project",
    )
    actual = arguments.read_text().splitlines()
    assert actual[:3] == ["release", "create", "v9.8.7"]
    assert {arg for arg in actual if arg.startswith("dist/")} == {
        "dist/example.whl",
        "dist/example.tar.gz",
        "dist/SHA256SUMS",
        "dist/RELEASE_NOTES.md",
        *(["dist/niri-desktop-continuity-9.8.7.mp4"] if video else []),
    }
    assert "--verify-tag" in actual and "--notes-file" in actual
    assert not any("*" in arg for arg in actual)
