"""Bounded review regressions: pixel grids, dimensional evidence, columns and stale addresses."""

import math
from copy import deepcopy

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_history as history


def scaled(s, monkeypatch, scale):
    monkeypatch.setattr(
        s.desktop,
        "outputs",
        lambda *, deadline=None: [{"name": "DP-1", "logical": {"scale": scale}}],
        raising=False,
    )
    observe = s.desktop.observe

    def capture():
        value = observe()
        value["outputs"] = s.desktop.outputs()
        return value

    monkeypatch.setattr(s.desktop, "observe", capture)
    action = s.desktop.action

    def quantized(*args):
        action(*args)
        if args[0] == "move-window-to-floating":
            s.desktop.floats[int(args[2])][1][:] = [124.0, 92.0]
        if args[0] == "move-floating-window":
            pos = s.desktop.floats[int(args[2])][1]
            for i, x in enumerate(pos):
                physical = x * scale
                whole = math.floor(abs(physical))
                pos[i] = math.copysign(whole + (abs(physical) - whole >= 0.5), physical) / scale

    monkeypatch.setattr(s.desktop, "action", quantized)


@pytest.mark.parametrize(
    "scale,requested,expected",
    [
        (1.5, [-11 / 1.5, 49 / 1.5], [-11 / 1.5, 49 / 1.5]),
        (1.25, [-0.4, 0.4], [-0.8, 0.8]),
        (1.25, [-7.12, 32.72], [-7.2, 32.8]),
        (1.5, [-0.3, 1 / 3], [0.0, 2 / 3]),
    ],
)
def test_floating_observable_pixel_grid(integrated, monkeypatch, scale, requested, expected):
    s = integrated
    scaled(s, monkeypatch, scale)
    entry = s.entry(1, 1, is_floating=True)
    entry["layout"]["pos_in_scrolling_layout"] = None
    entry["layout"]["tile_pos_in_workspace_view"] = requested
    _, result = s.run([entry])
    assert s.desktop.floats[12000][1] == expected
    assert result["status"] == "reopened", result
    assert result["windows"][0]["geometry_coverage"]["position"] == (
        "requested-observed" if requested == expected else "requested-quantized-observed"
    )


def test_width_is_pending_when_decoration_preflight_refuses(integrated, monkeypatch):
    s = integrated
    windows = s.desktop.windows

    def unknown(*, deadline=None):
        result = windows()
        for w in result:
            if w["id"] == 12000:
                w["layout"]["window_size"] = None
        return result

    monkeypatch.setattr(s.desktop, "windows", unknown)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted" and not s.desktop.actions
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-pending"


def test_later_failure_does_not_upgrade_unobserved_position(integrated, monkeypatch):
    s = integrated
    action = s.desktop.action

    def fail(*args):
        if args[0] == "move-floating-window":
            raise OSError("fabricated ambiguous dispatch")
        action(*args)

    monkeypatch.setattr(s.desktop, "action", fail)
    entry = s.entry(1, 1, is_floating=True)
    entry["layout"]["pos_in_scrolling_layout"] = None
    entry["layout"]["tile_pos_in_workspace_view"] = [8.0, 12.0]
    _, result = s.run([entry])
    assert result["status"] == "interrupted"
    assert result["windows"][0]["geometry_coverage"] == {
        "width": "requested-observed",
        "position": "requested-pending",
    }


@pytest.mark.parametrize(
    "widths,fresh,expected,coverage",
    [
        ([None, 900.0], [800.0, 800.0], 900.0, ["inherited-column", "requested-observed"]),
        ([900.0, None], [800.0, 800.0], 900.0, ["requested-observed", "inherited-column"]),
        ([None, None], [800.0, 733.5], 800.0, ["not-recorded-preserved", "inherited-column"]),
    ],
)
def test_shared_column_width_policy(integrated, monkeypatch, widths, fresh, expected, coverage):
    s = integrated
    add = s.desktop.add

    def mapped(pid):
        wid = add(pid)
        s.desktop.widths[wid] = fresh[pid - 2000]
        return wid

    monkeypatch.setattr(s.desktop, "add", mapped)
    entries = [s.entry(1, 1), s.entry(2, 1, 2)]
    for entry, width in zip(entries, widths):
        entry["layout"]["tile_size"] = None if width is None else [width, 1000.0]
    _, result = s.run(entries)
    assert result["status"] == "reopened", result
    assert s.desktop.columns[1] == [[70, 71], [80], [12000, 12001]]
    assert [s.desktop.widths[i] for i in (12000, 12001)] == [expected, expected]
    assert [r["geometry_coverage"]["width"] for r in result["windows"]] == coverage


def test_conflicting_column_widths_refuse_before_launch(integrated):
    s = integrated
    entries = [s.entry(1, 1), s.entry(2, 1, 2)]
    entries[1]["layout"]["tile_size"][0] = 950.0
    with pytest.raises(ValueError, match="conflicting"):
        s.run(entries)
    assert not s.proofs and not s.desktop.actions
    assert not history.fence_path(s.identity).exists()


@pytest.mark.parametrize("operation", ["move-window-to-workspace", "set-workspace-name"])
def test_reference_is_bound_to_caller_target_not_newly_resolved_neighbor(
    integrated, monkeypatch, operation
):
    from test_reopen import saved

    from niri_desktop_continuity import restore
    from niri_desktop_continuity.restore_layout import Layout

    s = integrated
    d = s.desktop
    d.columns = {1: [], 2: [], 3: [], 4: [[70, 71], [80]], 5: []}
    d.ws = [{"id": i, "idx": i, "output": "DP-1", "is_focused": i == 4} for i in range(1, 6)]
    matched, target = s.entry(1, 1), s.entry(2, 1)
    matched["reopen"].update(kind="pi", argv=["ghostty", "-e", "pi", "--session", "fabricated"])
    d.windows_by_id[70]["reopen"] = deepcopy(matched["reopen"])
    target["workspace_id"] = 2 if operation == "move-window-to-workspace" else 5
    entries = [matched, target]
    source_workspaces = deepcopy(saved([])["workspaces"])
    cleanup = d.lifecycle
    if operation == "move-window-to-workspace":
        d.ws[1]["name"] = "retained"
        d.ws[2]["name"] = "other"
    else:
        extra = s.entry(3, 1)
        extra["workspace_id"] = 6
        entries.append(extra)
        source_workspaces.append({"id": 6, "idx": 6, "output": "DP-1", "is_focused": False})
        monkeypatch.setattr(d, "lifecycle", lambda **_kwargs: cleanup(cleanup=False))
    d.initialize()
    effect = Layout.effect
    changed = []

    def drift(self, args, **kwargs):
        if args[0] == operation and not changed:
            changed.append(len(d.actions))
            cleanup(cleanup=True)
            assert next(w["idx"] for w in d.ws if w["id"] == 2) == 1
            assert next(w["idx"] for w in d.ws if w["id"] == 3) == 2
        return effect(self, args, **kwargs)

    monkeypatch.setattr(Layout, "effect", drift)
    key = s.store.put("snapshots", saved(entries, source_workspaces))
    result = restore.restore(s.store, key, d, apply=True, observe=d.observe, spawn_timeout=0.1)
    assert result["status"] == "interrupted", result
    assert changed == [len(d.actions)], (
        "caller target was silently rebound to another stable workspace"
    )
    assert next(w for w in d.ws if w["id"] == 3).get("name") == (
        "other" if operation == "move-window-to-workspace" else None
    )


@pytest.mark.parametrize("operation", ["move-window-to-workspace", "set-workspace-name"])
@pytest.mark.parametrize("change", ["reindex", "duplicate", "foreign-output"])
@pytest.mark.parametrize("phase", ["after-intent", "before-intent"])
def test_observed_address_drift_never_dispatches_stale_reference(
    integrated, monkeypatch, operation, change, phase
):
    s = integrated
    d = s.desktop
    d.columns = {1: [], 2: [], 3: [[70, 71], [80]]}
    d.ws = [
        {"id": 1, "idx": 1, "output": "DP-1", "is_focused": False},
        {"id": 2, "idx": 2, "output": "DP-1", "is_focused": False},
        {"id": 3, "idx": 3, "output": "DP-1", "is_focused": True},
    ]
    if operation == "move-window-to-workspace":
        d.ws[1]["name"] = "retained"
    d.initialize()
    matched, target = s.entry(1, 1), s.entry(2, 1)
    matched["reopen"].update(kind="pi", argv=["ghostty", "-e", "pi", "--session", "fabricated"])
    d.windows_by_id[70]["reopen"] = deepcopy(matched["reopen"])
    target["workspace_id"] = 2 if operation == "move-window-to-workspace" else 5
    cleanup = d.lifecycle
    if operation == "set-workspace-name":
        # Niri defers cleanup while workspace switching; settle it only at the named interleaving.
        monkeypatch.setattr(d, "lifecycle", lambda **_kwargs: cleanup(cleanup=False))

    create = history.durable_create
    at_intent = []

    def change_address():
        at_intent.append(len(d.actions))
        if change == "reindex":
            cleanup(cleanup=True)
            assert next(w["idx"] for w in d.ws if w["id"] == 2) == 1
        elif change == "duplicate":
            d.ws[0]["idx"] = 2
        else:
            d.ws[1].update(output="DP-2", idx=1)
            d.ws[2]["idx"] = 2

    def drift(path, record):
        create(path, record)
        payload = s.store.get("receipts", record["receipt"])
        if (
            record["type"] == "intent"
            and payload.get("details", {}).get("argv", [None])[0] == operation
        ):
            assert payload["details"]["target"] == {"workspace_id": 2, "output": "DP-1", "index": 2}
            change_address()

    if phase == "after-intent":
        monkeypatch.setattr(history, "durable_create", drift)
    else:
        from niri_desktop_continuity.restore_layout import Layout

        effect = Layout.effect

        def earlier(self, args, **kwargs):
            if args[0] == operation and not at_intent:
                change_address()
            return effect(self, args, **kwargs)

        monkeypatch.setattr(Layout, "effect", earlier)
    _, result = s.run([matched, target])
    assert len(at_intent) == 1, result
    assert result["status"] == "interrupted"
    assert len(d.actions) == at_intent[0], "observed stale numeric reference was dispatched"
    assert next(w for w in d.ws if w["id"] == 3).get("name") is None
    assert s.store.pointer("last-reopened") is None
    assert result["effects"] == [list(a) for a in d.actions]
    assert result["windows"][1]["geometry_coverage"]["width"] == (
        "requested-pending" if operation == "move-window-to-workspace" else "requested-observed"
    )
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass
