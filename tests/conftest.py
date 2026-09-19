"""Fail closed: no test may reach the operator's compositor or owner recovery profile."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import recovery_profile  # noqa: E402


@pytest.fixture(autouse=True)
def no_live_desktop_or_owner_profile(tmp_path_factory, monkeypatch):
    # Tests that need either provide a fabricated one; anything else now fails the same way on
    # a developer desktop as on a runner, instead of touching the real socket or ~/.config.
    monkeypatch.delenv("NIRI_SOCKET", raising=False)
    absent = tmp_path_factory.mktemp("no-owner-profile") / "absent" / "recovery-profile.json"
    monkeypatch.setattr(recovery_profile, "profile_path", lambda: absent)
