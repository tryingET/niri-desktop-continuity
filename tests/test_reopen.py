"""Reopen recipes, placement plan and executor oracles. No test contacts a compositor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import (  # noqa: E402
    autostart,
    cli,
    launch,
    operation_lock,
    probe,
    restore,
)
from niri_desktop_continuity.model import normalized_snapshot  # noqa: E402
from niri_desktop_continuity.store import Store  # noqa: E402

IDENTITY = {"boot_id": "old", "niri_socket": "/old", "socket_inode": 1, "socket_device": 1}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(launch, "declaration_root", lambda: runtime / "declared")
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


def test_unregistered_claude_session_is_never_replayed_from_its_prompt(monkeypatch):
    # A Claude process with no registry entry (e.g. one started with its prompt as argv) cannot
    # be resumed; replaying its command line would start the same task over as a new session.
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty"},
        {"pid": 11, "ppid": 10, "comm": "claude"},
        {"pid": 20, "ppid": 1, "comm": "ghostty"},
        {"pid": 21, "ppid": 20, "comm": "bash"},
        {"pid": 22, "ppid": 21, "comm": "claude"},
        {"pid": 23, "ppid": 22, "comm": "node"},
    ]
    cmdlines = {
        10: ["ghostty", "-e", "/opt/claude-code/bin/claude", "Work task 7. Claim it first."],
        11: ["/opt/claude-code/bin/claude", "Work task 7. Claim it first."],
        20: ["ghostty"],
        23: ["node", "/srv/mcp-server.js"],
    }
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/w")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    windows = [
        {"id": 1, "pid": 10, "app_id": "com.mitchellh.ghostty"},
        {"id": 2, "pid": 20, "app_id": "com.mitchellh.ghostty"},
    ]
    processes = [{"pid": 10, "comm": "ghostty"}, {"pid": 20, "comm": "ghostty"}]
    recipes = launch.window_recipes(windows, processes, inventory, {})
    unresumable = {
        "schema": launch.RECIPE_SCHEMA,
        "kind": "unknown",
        "argv": [],
        "cwd": None,
        "label": None,
        "reason": "claude-session-unregistered",
    }
    # Directly under the terminal, and under a shell with a child of its own (whose command
    # line is not the session either).
    assert recipes == {1: unresumable, 2: unresumable}


def test_unregistered_claude_tab_is_an_unknown_extra(monkeypatch):
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty"},
        {"pid": 11, "ppid": 10, "comm": "bash"},
        {"pid": 12, "ppid": 11, "comm": "btop"},
        {"pid": 13, "ppid": 10, "comm": "claude"},
    ]
    cmdlines = {10: ["ghostty"], 12: ["btop"], 13: ["claude", "do it"]}
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/w")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    windows = [{"id": 1, "pid": 10, "app_id": "com.mitchellh.ghostty"}]
    recipes = launch.window_recipes(windows, [{"pid": 10, "comm": "ghostty"}], inventory, {})
    assert recipes[1]["kind"] == "command"
    assert recipes[1]["argv"] == ["ghostty", "--working-directory=/w", "-e", "btop"]
    assert recipes[1]["extra"] == [launch.unknown_recipe("claude-session-unregistered")]


def unresumable_claude_tree(monkeypatch):
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty", "start_ticks": 100},
        {"pid": 11, "ppid": 10, "comm": "claude", "start_ticks": 500},
    ]
    cmdlines = {10: ["ghostty", "--working-directory=/w", "-e", "claude", "Work task 7."]}
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/w")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)

    def proc_stat(pid):
        match = next((item for item in inventory if item["pid"] == pid), None)
        if match is None:
            raise FileNotFoundError(pid)  # like /proc for a process that is gone
        return dict(match)

    monkeypatch.setattr(probe, "proc_stat", proc_stat)
    windows = [{"id": 1, "pid": 10, "app_id": "com.mitchellh.ghostty"}]
    return windows, [{"pid": 10, "comm": "ghostty"}], inventory


def test_declared_reopen_starts_a_fresh_session_from_a_handoff(monkeypatch):
    windows, processes, inventory = unresumable_claude_tree(monkeypatch)
    written = launch.declare(
        11, ["claude", "Resume task 7. Read /w/docs/handoff.md first."], cwd="/w", label="task 7"
    )
    path = launch.declaration_root() / "11.json"
    assert written == {
        "pid": 11,
        "start_ticks": 500,
        "argv": ["claude", "Resume task 7. Read /w/docs/handoff.md first."],
        "cwd": "/w",
        "label": "task 7",
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert launch.declaration_root().stat().st_mode & 0o777 == 0o700
    recipes = launch.window_recipes(windows, processes, inventory, {})
    assert recipes == {
        1: {
            "schema": launch.RECIPE_SCHEMA,
            "kind": "declared",
            "argv": [
                "ghostty",
                "--working-directory=/w",
                "-e",
                "claude",
                "Resume task 7. Read /w/docs/handoff.md first.",
            ],
            "cwd": "/w",
            "label": "task 7",
        }
    }
    # A declared recipe reopens on its saved workspace like any other known recipe.
    plan = restore.plan_restore(saved([window(1, 2, 1, reopen=recipes[1])]), [], [])
    assert plan["entries"][0]["target_workspace_idx"] == 1
    assert plan["unknown_workspace_idx"] is None
    assert launch.clear_declaration(11) is True
    assert not path.exists()
    assert launch.clear_declaration(11) is False


def test_declaration_for_a_reused_pid_is_ignored(monkeypatch):
    windows, processes, inventory = unresumable_claude_tree(monkeypatch)
    launch.declare(11, ["claude", "Resume task 7."], cwd="/w")
    inventory[1]["start_ticks"] = 501  # same pid, another process
    recipes = launch.window_recipes(windows, processes, inventory, {})
    assert recipes[1] == launch.unknown_recipe("claude-session-unregistered")


def test_declare_refuses_what_it_could_not_reopen(monkeypatch):
    unresumable_claude_tree(monkeypatch)
    with pytest.raises(ValueError, match="command"):
        launch.declare(11, [], cwd="/w")
    with pytest.raises(ValueError, match="absolute"):
        launch.declare(11, ["claude"], cwd="relative/dir")
    with pytest.raises(OSError):
        launch.declare(12, ["claude"], cwd="/w")  # no such same-user process
    assert not (launch.declaration_root() / "11.json").exists()


def test_declare_cli_defaults_the_directory_to_the_process(monkeypatch, capsys):
    unresumable_claude_tree(monkeypatch)
    assert cli.main(["declare", "--pid", "11", "--", "claude", "Resume task 7."]) == 0
    assert json.loads(capsys.readouterr().out)["declared"] == {
        "pid": 11,
        "start_ticks": 500,
        "argv": ["claude", "Resume task 7."],
        "cwd": "/w",
        "label": None,
    }
    assert cli.main(["declare", "--pid", "11", "--clear"]) == 0
    assert json.loads(capsys.readouterr().out) == {"cleared": True, "pid": 11}


def test_mountinfo_parser_reads_point_type_and_source(tmp_path):
    table = tmp_path / "mountinfo"
    table.write_text(
        "22 1 0:21 / /proc rw,nosuid shared:5 - proc proc rw\n"
        "111 61 0:189 / /var/tmp/.mount_Obsid\\040X ro,nosuid shared:752 - "
        "fuse.Obsidian-1.13.4.AppImage Obsidian-1.13.4.AppImage ro,user_id=1000\n"
        "garbage line\n"
    )
    assert launch.mount_table(table) == [
        ("/proc", "proc", "proc"),
        (
            "/var/tmp/.mount_Obsid X",
            "fuse.Obsidian-1.13.4.AppImage",
            "Obsidian-1.13.4.AppImage",
        ),
    ]


def appimage_fixture(monkeypatch, *, runtime_argv0="/opt/o/Obsidian.AppImage"):
    mounts = [
        ("/", "ext4", "/dev/nvme0n1p2"),
        (
            "/var/tmp/.mount_ObsidiqoUV",
            "fuse.Obsidian-1.13.4.AppImage",
            "Obsidian-1.13.4.AppImage",
        ),
    ]
    monkeypatch.setattr(launch, "mount_table", lambda path=None: mounts)
    cmdlines = {5: ["/var/tmp/.mount_ObsidiqoUV/obsidian", "--flag"], 40: [runtime_argv0]}
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/srv/work")
    exes = {
        5: "/var/tmp/.mount_ObsidiqoUV/obsidian",
        40: "/opt/o/Obsidian-1.13.4.AppImage",
        41: "/usr/bin/bash",
    }
    monkeypatch.setattr(launch, "read_exe", lambda pid: exes.get(pid))  # None, like a gone pid
    windows = [{"id": 1, "pid": 5, "app_id": "md.Obsidian"}]
    processes = [{"pid": 5, "comm": "obsidian"}]
    return windows, processes


def test_appimage_app_reopens_from_its_image_not_its_temporary_mount(monkeypatch):
    windows, processes = appimage_fixture(monkeypatch)
    inventory = [
        {"pid": 5, "ppid": 1, "comm": "obsidian"},
        {"pid": 40, "ppid": 1, "comm": "Obsidian.AppIma"},
        {"pid": 41, "ppid": 1, "comm": "bash"},
    ]
    recipes = launch.window_recipes(windows, processes, inventory, {})
    # The runtime's own argv[0] is the path the operator launched (a stable symlink here).
    assert recipes[1] == launch.app_recipe(["/opt/o/Obsidian.AppImage", "--flag"], "/srv/work")


def test_appimage_relative_launch_falls_back_to_the_image_file(monkeypatch):
    windows, processes = appimage_fixture(monkeypatch, runtime_argv0="./Obsidian.AppImage")
    inventory = [{"pid": 5, "ppid": 1, "comm": "obsidian"}, {"pid": 40, "ppid": 1, "comm": "x"}]
    recipes = launch.window_recipes(windows, processes, inventory, {})
    assert recipes[1]["argv"] == ["/opt/o/Obsidian-1.13.4.AppImage", "--flag"]


def test_appimage_without_its_runtime_process_is_unknown(monkeypatch):
    windows, processes = appimage_fixture(monkeypatch)
    inventory = [{"pid": 5, "ppid": 1, "comm": "obsidian"}, {"pid": 41, "ppid": 1, "comm": "bash"}]
    recipes = launch.window_recipes(windows, processes, inventory, {})
    assert recipes[1] == launch.unknown_recipe("appimage-mount-unresolved")


def test_xwayland_bridge_is_not_the_application(monkeypatch):
    # Niri reports the X11 bridge as the owner of every X11 window; relaunching it opens nothing.
    monkeypatch.setattr(
        launch, "read_cmdline", lambda pid: ["xwayland-satellite", ":0", "-listenfd", "102"]
    )
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/")
    windows = [{"id": 1, "pid": 6, "app_id": "AGNT"}, {"id": 2, "pid": 6, "app_id": "xterm"}]
    processes = [{"pid": 6, "comm": "xwayland-satell"}]
    recipes = launch.window_recipes(windows, processes, [], {})
    assert recipes == {
        1: launch.unknown_recipe("xwayland-client"),
        2: launch.unknown_recipe("xwayland-client"),
    }


def test_app_windows_share_the_process_command(monkeypatch):
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: ["nautilus", "--new-window"])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/srv/x")
    windows = [
        {"id": 1, "pid": 5, "app_id": "org.gnome.Nautilus"},
        {"id": 2, "pid": 5, "app_id": "org.gnome.Nautilus"},
    ]
    recipes = launch.window_recipes(windows, [{"pid": 5, "comm": "nautilus"}], [], {})
    assert recipes[1] == recipes[2] == launch.app_recipe(["nautilus", "--new-window"], "/srv/x")


def program(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


def test_rewritten_process_title_is_split_at_a_real_program(tmp_path, monkeypatch):
    # Chromium/Electron overwrite /proc/PID/cmdline with one space-joined title.
    electron = program(tmp_path / "agnt/node_modules/electron/dist/electron")
    spaced = program(tmp_path / "My Apps/tool")
    titles = {
        1: [f"{electron} --ozone-platform=wayland ."],
        2: [f"{spaced} --silent"],
        3: [f"{tmp_path}/missing --silent"],
        4: [spaced],  # a real path that contains a space is not a title
        5: ["nautilus", "--new-window"],  # an intact argv is left alone
    }
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: titles[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/srv/agnt")
    windows = [{"id": pid, "pid": pid, "app_id": f"app{pid}"} for pid in titles]
    processes = [{"pid": pid, "comm": "electron"} for pid in titles]
    recipes = launch.window_recipes(windows, processes, [], {})
    assert recipes[1]["argv"] == [electron, "--ozone-platform=wayland", "."]
    assert recipes[1]["argv_from_process_title"] is True and recipes[1]["cwd"] == "/srv/agnt"
    assert recipes[2]["argv"] == [spaced, "--silent"]
    assert recipes[3] == launch.unknown_recipe("process-title-unresolved")
    assert recipes[4] == launch.app_recipe([spaced], "/srv/agnt")
    assert recipes[5] == launch.app_recipe(["nautilus", "--new-window"], "/srv/agnt")


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


def test_recipe_labels_are_redacted_with_titles():
    # A Claude label is the session's AI title, which is also its terminal's window title.
    labelled = dict(
        recipe("claude", "ghostty", "-e", "claude", "--resume", "id"),
        label="Fix the private billing bug",
        extra=[dict(recipe("pi", "ghostty", "-e", "pi"), label="private pi session")],
    )
    raw = {
        "identity": IDENTITY,
        "coherent": True,
        "outputs": [{"name": "DP-1", "logical": {"w": 1}, "current_mode": 0}],
        "workspaces": [{"id": 1, "idx": 1, "output": "DP-1", "is_focused": True}],
        "windows": [window(1, 1, 1, reopen=labelled), window(2, 1, 2, reopen=None)],
    }
    redacted = normalized_snapshot(raw)
    assert "private" not in json.dumps(redacted)
    reopen = redacted["windows"][0]["reopen"]
    assert reopen["label"] is None and reopen["extra"][0]["label"] is None
    assert reopen["argv"] == ["ghostty", "-e", "claude", "--resume", "id"]
    assert redacted["windows"][1]["reopen"] is None
    kept = normalized_snapshot(raw, include_titles=True)["windows"][0]["reopen"]
    assert kept["label"] == "Fix the private billing bug"
    assert kept["extra"][0]["label"] == "private pi session"
    assert raw["windows"][0]["reopen"]["label"] == "Fix the private billing bug"  # input unchanged


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


def test_app_reopens_in_its_saved_directory(tmp_path):
    # niri spawns from its own directory; `electron .` must start where it was captured.
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    electron = ("/opt/agnt/electron", "--ozone-platform=wayland", ".")
    store = Store(tmp_path / "state")
    snapshot = saved(
        [
            window(1, 1, 1, app="AGNT", reopen={**recipe("app", *electron), "cwd": str(checkout)}),
            window(
                2, 1, 2, app="gone", reopen={**recipe("app", "gone", "."), "cwd": "/no/such/dir"}
            ),
            window(3, 1, 3, reopen={**recipe("pi", "ghostty", "-e", "pi"), "cwd": str(checkout)}),
        ]
    )
    key = store.put("snapshots", snapshot)
    desktop = FakeDesktop([])
    restore.restore(store, key, desktop, apply=True, observe=observation(desktop), spawn_timeout=1)
    chdir = 'cd -- "$1" && shift && exec "$@"'
    assert [a[1] for a in desktop.actions if a[0] == "spawn"] == [
        ("sh", "-c", chdir, "sh", str(checkout), *electron),
        ("gone", "."),  # a vanished directory falls back to niri's, as before
        ("ghostty", "-e", "pi"),  # terminals carry their directory in their own argv
    ]


def test_saved_directory_wrapper_changes_directory_without_reinterpreting_arguments(tmp_path):
    argv = ["printf", "%s|", "a b", "$HOME", "`id`", "."]
    wrapped = restore.spawn_argv({"kind": "app", "argv": argv, "cwd": str(tmp_path)})
    shown = subprocess.run(wrapped, capture_output=True, text=True, check=True).stdout
    assert shown == "a b|$HOME|`id`|.|"
    wrapped = restore.spawn_argv({"kind": "app", "argv": ["pwd", "-P"], "cwd": str(tmp_path)})
    assert subprocess.run(wrapped, capture_output=True, text=True, check=True).stdout == (
        f"{tmp_path.resolve()}\n"
    )


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
