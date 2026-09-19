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
BRAVE, FIREFOX, X11_BRIDGE = 1874, 1902, 1702
WORKSPACES = ("garden-api", "web", "notes", "chat", "ops")


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


def pi(cwd, session, title):
    return terminal("pi", cwd, "pi", "--session", session, label=title)


def app(*argv):
    return recipe("app", argv)


# workspace -> columns -> tiles of (pid, app id, title, reopen recipe)
DESKTOP = {
    "garden-api": [
        [
            (
                GHOSTTY,
                TERMINAL,
                "✳ Fix flaky login test",
                claude(API, "7c1e2f0a-3b5d-4e8f-9a61-2d4c8b7e5f13", "Fix flaky login test"),
            ),
            # Started from inside the Claude session above: no registry entry, so never replayed.
            (
                GHOSTTY,
                TERMINAL,
                "✳ Draft release notes",
                recipe("unknown", reason="claude-session-unregistered"),
            ),
        ],
        [
            (
                GHOSTTY,
                TERMINAL,
                "pi · rate-limiter refactor",
                pi(API, "3f9a1c7e", "rate-limiter refactor"),
            ),
            (GHOSTTY, TERMINAL, API, terminal("shell", API)),
        ],
        [
            (GHOSTTY, TERMINAL, "npm run dev", terminal("command", API, "npm", "run", "dev")),
            (
                GHOSTTY,
                TERMINAL,
                "✳ Audit-log migration",
                claude(API, "5d2b8e41-0c7a-4f96-8e13-b4a9c6d2f071", "Audit-log migration"),
            ),
        ],
        # Niri reports only the xwayland-satellite bridge as the owner of an X11 window.
        [
            (
                X11_BRIDGE,
                "jetbrains-idea",
                "garden-api – IntelliJ IDEA",
                recipe("unknown", reason="xwayland-client"),
            )
        ],
    ],
    "web": [
        [(BRAVE, "brave-browser", "Niri wiki: Configuration — Brave", app("brave"))],
        [(BRAVE, "brave-browser", "Pull requests · garden-api — Brave", app("brave"))],
        [(BRAVE, "brave-browser", "Grafana: API latency — Brave", app("brave"))],
        [(FIREFOX, "org.mozilla.firefox", "structuredClone() — MDN — Firefox", app("firefox"))],
    ],
    "notes": [
        [
            (
                1990,
                "md.Obsidian",
                "Weekly review - notes - Obsidian",
                app("/opt/obsidian/Obsidian.AppImage"),
            )
        ],
        [
            (
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
            )
        ],
        [
            (
                GHOSTTY,
                TERMINAL,
                "✳ Review PR 142",
                claude(NOTES, "0b8d4a6e-91f2-4c37-b5e0-6a2f9d1c8e74", "Review PR 142"),
            ),
            (GHOSTTY, TERMINAL, "pi · restore guide", pi(NOTES, "c07e5a19", "restore guide")),
        ],
    ],
    "chat": [
        [(1920, "org.mozilla.Thunderbird", "Inbox — Thunderbird", app("thunderbird"))],
        # Electron rewrote its command line into one title; capture split it at the program.
        [
            (
                2044,
                "signal",
                "Signal",
                {
                    **app("/usr/lib/signal-desktop/signal-desktop", "--use-tray-icon"),
                    "argv_from_process_title": True,
                },
            )
        ],
        [(2101, "org.gnome.Nautilus", "garden-api — Files", app("nautilus", "--new-window"))],
    ],
    "ops": [
        [(GHOSTTY, TERMINAL, "btop", terminal("command", INFRA, "btop"))],
        [
            (GHOSTTY, TERMINAL, "pi · deploy checklist", pi(INFRA, "a41d0b92", "deploy checklist")),
            (
                GHOSTTY,
                TERMINAL,
                "✳ Investigate 502s on staging",
                claude(
                    INFRA, "9e4f7a20-6b1d-4c58-a3e2-17d0c5b8f936", "Investigate 502s on staging"
                ),
            ),
        ],
        [(GHOSTTY, TERMINAL, "ssh staging-1", terminal("command", INFRA, "ssh", "staging-1"))],
    ],
}
FLOATING = {"ops": (2305, "org.gnome.Calculator", "Calculator", app("gnome-calculator"))}
EXECUTABLES = {
    BRAVE: "/opt/brave-bin/brave",
    FIREFOX: "/usr/lib/firefox/firefox",
    1920: "/usr/lib/thunderbird/thunderbird",
    1990: "/opt/obsidian/Obsidian.AppImage",
    2044: "/usr/lib/signal-desktop/signal-desktop",
    2101: "/usr/bin/nautilus",
    GHOSTTY: "/usr/bin/ghostty",
    X11_BRIDGE: "/usr/bin/xwayland-satellite",
    2305: "/usr/bin/gnome-calculator",
}


TILED = {"tile_size": [1264.0, 1384.0], "window_size": [1264, 1384]}
FLOATED = {"tile_pos_in_workspace_view": [1840.0, 96.0], "tile_size": [420.0, 560.0]}


def windows() -> list[dict]:
    rows = []
    for workspace, name in enumerate(WORKSPACES, 1):
        placed = [
            (tile, {**TILED, "pos_in_scrolling_layout": [column, index]})
            for column, tiles in enumerate(DESKTOP[name], 1)
            for index, tile in enumerate(tiles, 1)
        ]
        if name in FLOATING:
            placed.append((FLOATING[name], FLOATED))
        for (pid, app_id, title, reopen), layout in placed:
            rows.append(
                {
                    "id": len(rows) + 1,
                    "pid": pid,
                    "app_id": app_id,
                    "title": title,
                    "workspace_id": workspace,
                    "is_floating": layout is FLOATED,
                    "is_focused": not rows,
                    "layout": layout,
                    "reopen": reopen,
                }
            )
    return rows


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
                for ws, name in enumerate(WORKSPACES, 1)
            ],
            "windows": windows(),
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
