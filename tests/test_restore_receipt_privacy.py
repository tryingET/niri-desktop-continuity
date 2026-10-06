"""Interrupted diagnostics retain bounded geometry, never raw window-title payloads."""

import json

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_execute
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize("malformed", [False, True], ids=["projected", "unavailable"])
def test_given_private_titles_when_interrupted_then_no_raw_observation_is_persisted(
    integrated, monkeypatch, malformed
):
    s = integrated
    marker = "FABRICATED-PRIVATE-WINDOW-TITLE"
    for window in s.desktop.windows_by_id.values():
        window["title"] = marker
        window["foreign_payload"] = {"title": marker}
    original_windows = s.desktop.windows
    interrupted = False

    def windows(*, deadline=None):
        result = original_windows()
        if interrupted and malformed:
            result.append(dict(result[0]))  # Invalid duplicate IDs cannot authorize a raw fallback.
        return result

    def fail_before_dispatch(*args, **kwargs):
        nonlocal interrupted
        interrupted = True
        raise OSError("fabricated launch interruption")

    monkeypatch.setattr(s.desktop, "windows", windows)
    monkeypatch.setattr(restore_execute, "launch", fail_before_dispatch)
    _, result = s.run([s.entry(1, 1)])

    assert result["status"] == "interrupted"
    assert not s.desktop.actions
    assert result["effects"] == []
    assert marker not in json.dumps(result)
    stored = s.store.get("receipts", result["receipt_digest"])
    assert marker not in json.dumps(stored)
    assert stored["final_observation"] == result["final_observation"]
    if malformed:
        assert result["final_observation"] == {"unavailable": True}
    else:
        observation = result["final_observation"]
        assert set(observation) == {"windows", "workspaces", "outputs"}
        assert [w["id"] for w in observation["windows"]] == [70, 71, 80]
        assert all("title" not in w and "foreign_payload" not in w for w in observation["windows"])
    with pytest.raises(ValueError, match="unresolved"):
        history.require_clear(s.identity)
