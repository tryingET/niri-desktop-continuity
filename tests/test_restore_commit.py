"""Crash boundaries distinguish historical commit from pointer projection and uncertainty."""

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize(
    "boundary", ["intent", "observation", "final-receipt", "terminal", "after-terminal", "pointer"]
)
def test_crash_boundaries_never_repeat_effects(integrated, monkeypatch, boundary):
    s = integrated
    put = s.store.put
    create = history.durable_create
    pointer = s.store.pointer

    def crash_put(kind, value):
        if boundary == "final-receipt" and "final_observation" in value and "error" not in value:
            raise OSError("fabricated final receipt failure")
        return put(kind, value)

    def crash_create(path, record):
        if record["type"] == {
            "intent": "intent",
            "observation": "observed",
            "terminal": "terminal",
        }.get(boundary):
            raise OSError("fabricated canonical record failure")
        create(path, record)
        if record["type"] == "terminal" and boundary == "after-terminal":
            raise OSError("fabricated return interruption after durable terminal")

    def crash_pointer(name, key=None):
        if key is not None and boundary == "pointer":
            raise OSError("fabricated pointer failure")
        return pointer(name, key)

    monkeypatch.setattr(s.store, "put", crash_put)
    monkeypatch.setattr(history, "durable_create", crash_create)
    monkeypatch.setattr(s.store, "pointer", crash_pointer)
    key, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    count = len(s.desktop.actions)
    assert s.store.pointer("last-reopened") is None
    if boundary in {"pointer", "after-terminal"}:
        if boundary == "pointer":
            assert result["status"] == "reopened" and result["pointer_projected"] is False
        replay = restore.restore(
            s.store, key, s.desktop, apply=True, observe=lambda: pytest.fail("historical only")
        )
        assert replay["historical"] and replay["status"] == "reopened"
        with operation_lock.operation_lock(s.identity):
            pass
    else:
        assert result["status"] == "interrupted"
        with pytest.raises(ValueError, match="unresolved restore"):
            restore.restore(s.store, key, s.desktop, apply=True)
    assert len(s.desktop.actions) == count


def test_unknown_decoration_does_not_claim_layout_complete(integrated, monkeypatch):
    s = integrated
    read = s.desktop.windows

    def unknown(*, deadline=None):
        windows = read()
        for w in windows:
            if w["id"] >= 12000:
                w["layout"]["window_size"] = None
        return windows

    monkeypatch.setattr(s.desktop, "windows", unknown)
    entry = s.entry(1, 1)
    _, result = s.run([entry])
    assert result["status"] == "interrupted"
    assert s.store.pointer("last-reopened") is None
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)
    assert s.desktop.focus != 70  # no cleanup after failure


@pytest.mark.parametrize("mutation", ["arrival", "focus", "protected-height", "no-op"])
def test_postdispatch_drift_stops_without_corrective_actions(integrated, monkeypatch, mutation):
    s = integrated
    original = s.desktop.action

    def changed(*args):
        if mutation != "no-op":
            original(*args)
        else:
            s.desktop.actions.append(args)
        if mutation == "arrival":
            s.desktop.add(9000)
        elif mutation == "focus":
            s.desktop.focus = 80
        elif mutation == "protected-height":
            read = s.desktop.windows

            def taller(*, deadline=None):
                windows = read()
                next(w for w in windows if w["id"] == 70)["layout"]["tile_size"][1] += 1
                return windows

            monkeypatch.setattr(s.desktop, "windows", taller)

    monkeypatch.setattr(s.desktop, "action", changed)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted"
    assert len(s.desktop.actions) == 1
    assert s.store.pointer("last-reopened") is None


def test_per_output_indices_and_actual_destination_identity(integrated):
    s = integrated
    s.desktop.ws.append({"id": 99, "idx": 1, "output": "DP-2", "is_focused": False})
    s.desktop.columns[99] = []
    s.desktop.initialize()
    a, b = s.entry(1, 1), s.entry(2, 1)
    b["workspace_id"] = 2
    _, result = s.run([a, b])
    assert result["status"] == "reopened", result
    assert s.desktop.columns == {1: [[70, 71], [80], [12000]], 2: [[12001]], 99: [], 508: []}
    assert s.desktop.focus == 70
