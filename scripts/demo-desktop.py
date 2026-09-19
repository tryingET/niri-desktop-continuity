#!/usr/bin/env python3
"""Fabricated demo desktop for documentation screenshots. Never render a real capture for docs.

Usage: demo-desktop.py OUTPUT_DIRECTORY
Writes preview.html (the page `preview` writes) and after-reboot.html (only its reopen ledger).
"""

from __future__ import annotations

import sys
from pathlib import Path

from niri_desktop_continuity.launch import RECIPE_SCHEMA
from niri_desktop_continuity.map_preview import render_html
from niri_desktop_continuity.model import normalized_snapshot

GHOSTTY = 2210  # one single-instance terminal process owns every terminal window
TERMINAL = "com.mitchellh.ghostty"
API, NOTES, INFRA = "/work/garden-api", "/work/notes", "/work/infra"


def recipe(kind, argv=(), cwd=None, label=None, reason=None):
    value = {"schema": RECIPE_SCHEMA, "kind": kind, "argv": list(argv), "cwd": cwd, "label": label}
    if reason:
        value["reason"] = reason
    return value


def terminal(kind, cwd, *command, label=None):
    argv = ["ghostty", f"--working-directory={cwd}", *(["-e", *command] if command else [])]
    return recipe(kind, argv, cwd, label)


def claude(cwd, session_id, title):
    return terminal("claude", cwd, "claude", "--resume", session_id, label=title)


# (workspace id, column, tile, pid, app id, title, reopen recipe)
WINDOWS = [
    (
        1,
        1,
        1,
        GHOSTTY,
        TERMINAL,
        "✳ Fix flaky login test",
        claude(API, "7c1e2f0a-3b5d-4e8f-9a61-2d4c8b7e5f13", "Fix flaky login test"),
    ),
    (
        1,
        2,
        1,
        GHOSTTY,
        TERMINAL,
        "pi · rate-limiter refactor",
        terminal("pi", API, "pi", "--session", "3f9a1c7e", label="rate-limiter refactor"),
    ),
    (1, 2, 2, GHOSTTY, TERMINAL, API, terminal("shell", API)),
    (1, 3, 1, GHOSTTY, TERMINAL, "npm run dev", terminal("command", API, "npm", "run", "dev")),
    # Started from inside another Claude session's shell: no registry entry, so never replayed.
    (
        1,
        4,
        1,
        GHOSTTY,
        TERMINAL,
        "✳ Draft release notes",
        recipe("unknown", reason="claude-session-unregistered"),
    ),
    (
        2,
        1,
        1,
        1990,
        "md.Obsidian",
        "Weekly review - notes - Obsidian",
        recipe("app", ["/opt/obsidian/Obsidian.AppImage"]),
    ),
    (
        2,
        2,
        1,
        GHOSTTY,
        TERMINAL,
        "✳ Search index handoff",
        terminal(
            "declared",
            NOTES,
            "claude",
            "Continue from docs/handoff.md",
            label="search index, fresh session",
        ),
    ),
    (
        2,
        3,
        1,
        GHOSTTY,
        TERMINAL,
        "✳ Review PR 142",
        claude(NOTES, "0b8d4a6e-91f2-4c37-b5e0-6a2f9d1c8e74", "Review PR 142"),
    ),
    # Niri reports only the xwayland-satellite bridge as the owner of an X11 window.
    (
        2,
        4,
        1,
        1702,
        "jetbrains-idea",
        "garden-api – IntelliJ IDEA",
        recipe("unknown", reason="xwayland-client"),
    ),
    (3, 1, 1, 1874, "brave-browser", "Niri wiki: Configuration — Brave", recipe("app", ["brave"])),
    (
        3,
        2,
        1,
        1874,
        "brave-browser",
        "Pull requests · garden-api — Brave",
        recipe("app", ["brave"]),
    ),
    (
        3,
        3,
        1,
        1920,
        "org.mozilla.Thunderbird",
        "Inbox — Thunderbird",
        recipe("app", ["thunderbird"]),
    ),
    (4, 1, 1, GHOSTTY, TERMINAL, "btop", terminal("command", INFRA, "btop")),
    (
        4,
        2,
        1,
        GHOSTTY,
        TERMINAL,
        "pi · deploy checklist",
        terminal("pi", INFRA, "pi", "--session", "a41d0b92", label="deploy checklist"),
    ),
    (
        4,
        None,
        None,
        2305,
        "org.gnome.Calculator",
        "Calculator",
        recipe("app", ["gnome-calculator"]),
    ),
]
EXECUTABLES = {
    1874: "/opt/brave-bin/brave",
    1920: "/usr/lib/thunderbird/thunderbird",
    1990: "/opt/obsidian/Obsidian.AppImage",
    GHOSTTY: "/usr/bin/ghostty",
    1702: "/usr/bin/xwayland-satellite",
    2305: "/usr/bin/gnome-calculator",
}


def window(wid, workspace, column, tile, pid, app_id, title, reopen):
    layout = {"tile_size": [1264.0, 1384.0], "window_size": [1264, 1384]}
    if column is None:
        layout = {"tile_pos_in_workspace_view": [1840.0, 96.0], "tile_size": [420.0, 560.0]}
    else:
        layout["pos_in_scrolling_layout"] = [column, tile]
    return {
        "id": wid,
        "pid": pid,
        "app_id": app_id,
        "title": title,
        "workspace_id": workspace,
        "is_floating": column is None,
        "is_focused": wid == 1,
        "layout": layout,
        "reopen": reopen,
    }


def demo_snapshot() -> dict:
    return normalized_snapshot(
        {
            "captured_at": "2026-09-18T18:30:00+00:00",
            "identity": {
                "boot_id": "demo",
                "niri_socket": "/run/niri-demo.sock",
                "socket_inode": 1,
                "socket_device": 1,
            },
            "coherent": True,
            "outputs": [
                {"name": "DP-1", "logical": {"width": 2560, "height": 1440}, "current_mode": 0}
            ],
            "workspaces": [
                {"id": ws, "idx": ws, "name": name, "output": "DP-1", "is_focused": ws == 1}
                for ws, name in enumerate(("garden-api", "notes", "web", "ops"), 1)
            ],
            "windows": [window(wid, *row) for wid, row in enumerate(WINDOWS, 1)],
            "processes": [
                {
                    "pid": pid,
                    "ppid": 1,
                    "start_ticks": 4000 + pid,
                    "exe": exe,
                    "exe_sha256": f"{pid:04x}" * 16,
                    "cgroup": "/user.slice/app.slice",
                    "version": None,
                }
                for pid, exe in sorted(EXECUTABLES.items())
            ],
            "layers": [{"namespace": "waybar", "output": "DP-1", "layer": "Top"}],
        },
        include_titles=True,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    markup = render_html(demo_snapshot())
    (out / "preview.html").write_text(markup)
    # The same page with every other section hidden, so a viewport screenshot shows the ledger.
    only = "main>:not(#after-reboot){display:none}#after-reboot{border-top:0;padding-top:0}"
    (out / "after-reboot.html").write_text(markup.replace("</style>", only + "</style>", 1))
    print(out / "preview.html")
