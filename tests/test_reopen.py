"""Reopen recipes, placement plan and executor oracles. No test contacts a compositor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import autostart, launch, operation_lock, restore  # noqa: E402
from niri_desktop_continuity.model import normalized_snapshot  # noqa: E402
from niri_desktop_continuity.store import Store  # noqa: E402

IDENTITY = {"boot_id": "old", "niri_socket": "/old", "socket_inode": 1, "socket_device": 1}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(restore, "compositor_identity", lambda: {**IDENTITY, "boot_id": "new"})


def window(wid, workspace, column, *, app="com.mitchellh.ghostty", tile=1, reopen=None, **extra):
    return {
        "id": wid,
        "pid": 100 + wid,
        "app_id": app,
        "title": f"t{wid}",
        "workspace_id": workspace,
        "is_floating": False,
        "is_focused": False,
        "layout": {"pos_in_scrolling_layout": [column, tile], "tile_size": [900.0, 1000.0]},
        "reopen": reopen,
        **extra,
    }


def recipe(kind, *argv, extra=None):
    value = {"schema": launch.RECIPE_SCHEMA, "kind": kind, "argv": list(argv), "cwd": None}
    if extra:
        value["extra"] = extra
    return value


def saved(windows, workspaces=None):
    return normalized_snapshot(
        {
            "identity": IDENTITY,
            "coherent": True,
            "outputs": [{"name": "DP-1", "logical": {"w": 1}, "current_mode": 0}],
            "workspaces": workspaces
            or [
                {"id": 1, "idx": 1, "output": "DP-1", "is_focused": True},
                {"id": 2, "idx": 2, "output": "DP-1"},
                {"id": 9, "idx": 3, "name": "empty-named", "output": "DP-1"},
                {"id": 5, "idx": 4, "name": "lab", "output": "DP-1"},
            ],
            "windows": windows,
            "layers": [],
            "processes": [],
        },
        include_titles=True,
    )


# --- recipes -------------------------------------------------------------------------------


def test_terminal_base_argv_strips_previous_command_and_directory():
    argv = ["ghostty", "--gtk-single-instance=false", "--working-directory=/x", "-e", "btop", "-e"]
    assert launch.terminal_base_argv(argv) == ["ghostty", "--gtk-single-instance=false"]
    assert launch.terminal_recipe(
        argv, {"kind": "pi", "argv": ["pi", "--session", "s"], "cwd": "/w"}
    )["argv"] == [
        "ghostty",
        "--gtk-single-instance=false",
        "--working-directory=/w",
        "-e",
        "pi",
        "--session",
        "s",
    ]
    assert launch.terminal_recipe(argv, None) == {
        "schema": launch.RECIPE_SCHEMA,
        "kind": "shell",
        "argv": ["ghostty", "--gtk-single-instance=false"],
        "cwd": None,
        "label": None,
    }


def test_descendants_bounded_and_cycle_safe():
    children = {1: [2, 3], 2: [4], 4: [1]}
    assert launch.descendants(1, children) == [2, 3, 4]


def test_window_recipes_match_sessions_to_windows_by_title(monkeypatch):
    # One single-instance terminal process owns two windows; each runs a different session.
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty"},
        {"pid": 11, "ppid": 10, "comm": "bash"},
        {"pid": 12, "ppid": 11, "comm": "claude"},
        {"pid": 13, "ppid": 10, "comm": "bash"},
        {"pid": 14, "ppid": 13, "comm": "node"},
        {"pid": 15, "ppid": 10, "comm": "bash"},
        {"pid": 16, "ppid": 15, "comm": "btop"},
    ]
    monkeypatch.setattr(
        launch, "read_cmdline", lambda pid: {10: ["ghostty", "-e", "old"], 16: ["btop"]}[pid]
    )
    monkeypatch.setattr(launch, "read_cwd", lambda pid: f"/cwd/{pid}")
    monkeypatch.setattr(
        launch,
        "claude_session",
        lambda pid: (
            {"kind": "claude", "argv": ["claude", "--resume", "abc"], "cwd": "/c", "label": "Fix"}
            if pid == 12
            else None
        ),
    )
    monkeypatch.setattr(
        launch,
        "pi_session",
        lambda pid: (
            {
                "kind": "pi",
                "argv": ["pi", "--session", "f"],
                "cwd": "/p",
                "label": "tok",
                "labels": ["tok", "name"],
            }
            if pid == 14
            else None
        ),
    )
    windows = [
        {"id": 1, "pid": 10, "app_id": "com.mitchellh.ghostty"},
        {"id": 2, "pid": 10, "app_id": "com.mitchellh.ghostty"},
        {"id": 3, "pid": 99, "app_id": "x"},
    ]
    titles = {1: "π - repo · tok · 0", 2: "✳ Fix"}
    processes = [{"pid": 10, "comm": "ghostty"}]
    recipes = launch.window_recipes(windows, processes, inventory, titles)
    assert recipes[2]["kind"] == "claude"
    assert recipes[2]["argv"] == [
        "ghostty",
        "--working-directory=/c",
        "-e",
        "claude",
        "--resume",
        "abc",
    ]
    assert recipes[1]["kind"] == "pi"
    # The unmatched btop surface reopens as an extra window of the first window.
    assert [e["kind"] for e in recipes[1]["extra"]] == ["command"]
    assert recipes[1]["extra"][0]["argv"][-2:] == ["-e", "btop"]
    assert recipes[3] == launch.unknown_recipe("process-unavailable")
    assert "title" not in str(recipes)  # titles are matched, never stored


def test_direct_child_command_without_shell_is_a_command(monkeypatch):
    inventory = [{"pid": 10, "ppid": 1, "comm": "ghostty"}, {"pid": 11, "ppid": 10, "comm": "btop"}]
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: {10: ["ghostty"], 11: ["btop"]}[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/h")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    assert launch.terminal_sessions(10, inventory) == [
        {"kind": "command", "argv": ["btop"], "cwd": "/h", "label": None}
    ]


def test_app_windows_share_the_process_command(monkeypatch):
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: ["nautilus", "--new-window"])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/srv/x")
    windows = [
        {"id": 1, "pid": 5, "app_id": "org.gnome.Nautilus"},
        {"id": 2, "pid": 5, "app_id": "org.gnome.Nautilus"},
    ]
    recipes = launch.window_recipes(windows, [{"pid": 5, "comm": "nautilus"}], [], {})
    assert recipes[1] == recipes[2] == launch.app_recipe(["nautilus", "--new-window"], "/srv/x")


def test_claude_registry_and_title_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    sessions = tmp_path / ".claude" / "sessions"
    sessions.mkdir(parents=True)
    sid = "9f6031d6-a9ff-4b94-bdb5-a365989558f6"
    (sessions / "42.json").write_text(f'{{"pid": 42, "sessionId": "{sid}", "cwd": "/w/a.b"}}')
    project = tmp_path / ".claude" / "projects" / "-w-a-b"
    project.mkdir(parents=True)
    (project / f"{sid}.jsonl").write_text(
        '{"type":"user","message":"x"}\n{"type":"ai-title","aiTitle":"First"}\nnot json\n'
        '{"type":"ai-title","aiTitle":"Second"}\n'
    )
    assert launch.claude_session(42) == {
        "kind": "claude",
        "argv": ["claude", "--resume", sid],
        "cwd": "/w/a.b",
        "label": "Second",
    }
    assert launch.claude_session(43) is None
    (sessions / "44.json").write_text('{"pid": 45, "sessionId": "x", "cwd": "/"}')
    assert launch.claude_session(44) is None  # pid mismatch is not a session


def test_pi_presence_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_SESSION_PRESENCE_DIR", str(tmp_path))
    (tmp_path / "7.json").write_text(
        '{"pid": 7, "cwd": "/p", "resumeArgv": ["pi", "--session", "/s.jsonl"], "sessionIdentityToken": "tok"}'
    )
    (tmp_path / "8.json").write_text('{"pid": 8, "cwd": "/p", "resumeArgv": "pi"}')
    assert launch.pi_session(7)["argv"] == ["pi", "--session", "/s.jsonl"]
    assert launch.pi_session(7)["label"] == "tok"
    assert launch.pi_session(8) is None


# --- placement plan ------------------------------------------------------------------------


def test_plan_compacts_workspaces_and_sends_unknowns_last():
    snapshot = saved(
        [
            window(1, 1, 2, reopen=recipe("app", "brave")),
            window(2, 1, 1, reopen=recipe("unknown")),
            window(3, 5, 1, reopen=recipe("pi", "ghostty", "-e", "pi")),
            window(4, 2, 1, reopen=recipe("claude", "ghostty", "-e", "claude", "--resume", "id")),
            window(5, 2, 1, tile=2, reopen=recipe("app", "obsidian")),
        ]
    )
    current = [
        window(50, 1, 1, reopen=recipe("claude", "ghostty", "-e", "claude", "--resume", "id"))
    ]
    plan = restore.plan_restore(snapshot, current, [])
    by_id = {e["window_id"]: e for e in plan["entries"]}
    assert by_id[1]["target_workspace_idx"] == 1
    assert by_id[4]["target_workspace_idx"] == 2 and by_id[4]["status"] == "already-open"
    assert by_id[3]["target_workspace_idx"] == 3  # empty named workspace 3 is skipped
    assert by_id[2]["target_workspace_idx"] == 4 and by_id[2]["column"] is None
    assert plan["unknown_workspace_idx"] == 4
    assert plan["workspace_names"] == {3: "lab"}
    assert plan["protected_window_ids"] == [50]
    assert [e["window_id"] for e in plan["entries"]] == [1, 4, 5, 3, 2]


def test_plan_expands_extra_sessions_after_their_window():
    snapshot = saved(
        [
            window(
                1,
                1,
                1,
                reopen=recipe(
                    "pi",
                    "ghostty",
                    "-e",
                    "pi",
                    "a",
                    extra=[recipe("pi", "ghostty", "-e", "pi", "b")],
                ),
            )
        ]
    )
    plan = restore.plan_restore(snapshot, [], [])
    assert [(e["window_id"], e.get("extra_of"), e["column"]) for e in plan["entries"]] == [
        (1, None, 1),
        (None, 1, None),
    ]


# --- executor ------------------------------------------------------------------------------


class FakeDesktop:
    """Models spawn→new window on the focused workspace and records every action."""

    def __init__(self, live, *, fail_spawn=(), mismatched_app=()):
        self.live = list(live)
        self.next_id = 1000
        self.actions: list[tuple] = []
        self.fail_spawn = set(fail_spawn)
        self.mismatched_app = set(mismatched_app)
        self.clock = 0.0
        self.workspace_list = [{"id": 1, "idx": 1}, {"id": 2, "idx": 2}, {"id": 3, "idx": 3}]

    def windows(self):
        return [dict(w) for w in self.live]

    def workspaces(self):
        return list(self.workspace_list)

    def ready(self):
        return True

    def spawn(self, argv):
        self.actions.append(("spawn", tuple(argv)))
        if tuple(argv) in self.fail_spawn:
            return
        app = "other" if tuple(argv) in self.mismatched_app else argv[0]
        self.next_id += 1
        self.live.append(window(self.next_id, 1, len(self.live) + 1, app=app))

    def action(self, *args):
        self.actions.append(args)
        if args[0] == "move-window-to-workspace":
            wid, idx = int(args[2]), int(args[-1])
            for w in self.live:
                if w["id"] == wid:
                    w["workspace_id"] = next(
                        x["id"] for x in self.workspace_list if x["idx"] == idx
                    )

    def sleep(self, seconds):
        self.clock += seconds

    def monotonic(self):
        return self.clock


def observation(desktop):
    def observe():
        return saved(
            desktop.windows(),
            workspaces=[
                {"id": i, "idx": i, "output": "DP-1", "is_focused": i == 1} for i in (1, 2, 3)
            ],
        )

    return observe


def test_reopen_places_columns_after_protected_windows_and_restores_focus(tmp_path):
    store = Store(tmp_path / "state")
    key = store.put(
        "snapshots",
        saved(
            [
                window(1, 1, 1, app="brave", reopen=recipe("app", "brave")),
                window(2, 1, 2, app="ghostty", reopen=recipe("pi", "ghostty", "-e", "pi")),
                window(
                    3, 1, 2, app="ghostty", tile=2, reopen=recipe("pi", "ghostty", "-e", "pi", "2")
                ),
                window(4, 2, 1, app="obsidian", reopen=recipe("app", "obsidian")),
                window(5, 2, 1, reopen=recipe("unknown")),
            ]
        ),
    )
    live = [window(7, 1, 1, app="ghostty", is_focused=True), window(8, 1, 2, app="brave")]
    desktop = FakeDesktop(live)
    result = restore.restore(
        store, key, desktop, apply=True, observe=observation(desktop), spawn_timeout=2
    )
    assert result["status"] == "reopened-partially"  # the unknown window has no command
    statuses = {w["window_id"]: w["status"] for w in result["windows"]}
    assert statuses == {1: "placed", 2: "placed", 3: "placed", 4: "placed", 5: "no-launch-command"}
    assert ("spawn", ("brave",)) in desktop.actions
    moves = [a for a in desktop.actions if a[0] == "move-window-to-workspace"]
    assert [a[-1] for a in moves] == ["1", "1", "1", "2"]
    assert all(a[4] == "false" for a in moves)  # focus never follows a reopened window
    # Two protected tiled columns on workspace 1 → saved column 1 lands at index 3.
    assert ("move-column-to-index", "3") in desktop.actions
    assert ("set-column-width", "900") in desktop.actions
    assert ("consume-window-into-column",) in desktop.actions
    assert desktop.actions[-1] == ("focus-window", "--id", "7")
    assert store.pointer("last-reopened") == key
    assert not any(a[0] == "set-workspace-name" for a in desktop.actions)
    assert store.get("receipts", result["receipt_digest"])["protected_window_ids"] == [7, 8]


def test_reopen_records_undetected_spawn_and_never_moves_protected(tmp_path):
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved([window(1, 1, 1, app="x", reopen=recipe("app", "x"))]))
    desktop = FakeDesktop([window(7, 1, 1, app="x")], fail_spawn={("x",)})
    result = restore.restore(
        store, key, desktop, apply=True, observe=observation(desktop), spawn_timeout=1
    )
    assert result["windows"][0]["status"] == "spawned-window-not-detected"
    assert result["status"] == "reopened-partially"
    assert [a for a in desktop.actions if a[0] != "spawn"] == [("focus-workspace", "1")]


def test_mismatched_app_id_is_accepted_only_after_timeout(tmp_path):
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved([window(1, 1, 1, app="x", reopen=recipe("app", "x"))]))
    desktop = FakeDesktop([], mismatched_app={("x",)})
    result = restore.restore(
        store, key, desktop, apply=True, observe=observation(desktop), spawn_timeout=1
    )
    assert result["windows"][0]["status"] == "placed"
    assert desktop.clock >= 1


def test_self_restoring_app_is_launched_once_then_awaited(tmp_path):
    store = Store(tmp_path / "state")
    snapshot = saved(
        [
            window(1, 1, 1, app="brave-browser", reopen=recipe("app", "brave")),
            window(2, 1, 2, app="brave-browser", reopen=recipe("app", "brave")),
            window(3, 1, 3, app="brave-browser", reopen=recipe("app", "brave")),
        ]
    )
    key = store.put("snapshots", snapshot)

    class Browser(FakeDesktop):
        def spawn(self, argv):
            super().spawn(argv)
            # One launch restores two windows by itself.
            self.next_id += 1
            self.live.append(window(self.next_id, 1, len(self.live) + 1, app="brave-browser"))

    desktop = Browser([])
    result = restore.restore(
        store, key, desktop, apply=True, observe=observation(desktop), spawn_timeout=2
    )
    assert [a for a in desktop.actions if a[0] == "spawn"] == [
        ("spawn", ("brave",)),
        ("spawn", ("brave",)),
    ]
    assert [w["status"] for w in result["windows"]] == ["placed"] * 3
    assert result["windows"][1]["awaited_self_restore"] is True
    assert result["windows"][2]["awaited_self_restore"] is False


def test_dry_run_has_no_effects_and_refuses_headless_snapshot(tmp_path):
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved([window(1, 1, 1, reopen=recipe("app", "x"))]))
    desktop = FakeDesktop([])
    result = restore.restore(store, key, desktop, apply=False, observe=observation(desktop))
    assert result["status"] == "dry-run" and desktop.actions == []
    headless = saved([window(1, 1, 1, reopen=recipe("app", "x"))])
    headless["outputs"] = []
    with pytest.raises(ValueError, match="display-valid"):
        restore.restore(
            store,
            store.put("snapshots", headless),
            desktop,
            apply=True,
            observe=observation(desktop),
        )


# --- autostart units -----------------------------------------------------------------------


def test_autostart_units_are_ordered_and_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    calls = []
    result = autostart.enable(interval_minutes=20, control=lambda *a: calls.append(a))
    units = autostart.render(20, None)
    assert result["interval_minutes"] == 20 and len(result["written"]) == 3
    restore_unit = units["niri-desktop-continuity-restore.service"]
    assert "WantedBy=graphical-session.target" in restore_unit
    assert "restore --apply --at-login" in restore_unit
    assert (
        "After=graphical-session.target niri-desktop-continuity-restore.service"
        in units["niri-desktop-continuity-capture.service"]
    )
    assert "OnUnitActiveSec=20min" in units["niri-desktop-continuity-capture.timer"]
    assert calls[0] == ("daemon-reload",)
    assert (
        "enable",
        "niri-desktop-continuity-restore.service",
        "niri-desktop-continuity-capture.timer",
    ) in calls
    with pytest.raises(ValueError):
        autostart.enable(interval_minutes=0, control=lambda *a: None)
    removed = autostart.disable(control=lambda *a: calls.append(a))
    assert len(removed["removed"]) == 3
    assert autostart.status(runner=lambda *a, **k: None)["units"] == {
        name: "absent" for name in autostart.UNITS
    }
