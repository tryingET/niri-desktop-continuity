"""Offline map contracts: escaping, privacy, complete inventory and blocked restart."""

from __future__ import annotations

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_core import snapshot  # noqa: E402

from niri_desktop_continuity import cli  # noqa: E402
from niri_desktop_continuity.map_preview import render_html, render_svg  # noqa: E402
from niri_desktop_continuity.model import readiness  # noqa: E402
from niri_desktop_continuity.planner import build_plan  # noqa: E402
from niri_desktop_continuity.store import Store  # noqa: E402


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


def test_hostile_titles_escaped_both_formats_and_no_effect_surface():
    source = snapshot()
    source["privacy"]["titles_included"] = True
    source["windows"][0]["title"] = (
        '</style><script>alert(1)</script><img src="https://evil"> & \x01'
    )
    markup = render_html(source)
    elements = Elements()
    elements.feed(markup)
    assert not {"script", "img", "button", "form", "iframe"} & set(elements.tags)
    assert not any(name.startswith("on") or name in {"src", "href"} for name, _ in elements.attrs)
    assert "&lt;script&gt;" in markup
    svg = ET.fromstring(render_svg(source))
    assert len(svg.findall(".//{http://www.w3.org/2000/svg}rect")) == 4
    assert svg.find(".//{http://www.w3.org/2000/svg}script") is None


def test_renderer_redacts_even_if_raw_title_present():
    source = snapshot()
    source["windows"][0]["title"] = "PRIVATE DRAFT"
    assert "PRIVATE DRAFT" not in render_html(source)
    assert "PRIVATE DRAFT" not in render_svg(source)


def test_all_33_windows_no_silent_clipping_and_determinism():
    source = snapshot(33)
    first = render_svg(source)
    assert first == render_svg(source)
    assert render_html(source) == render_html(source)
    svg = ET.fromstring(first)
    assert (
        len(svg.findall(".//{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}title")) == 33
    )
    assert int(svg.attrib["width"]) > 33 * 236
    for window in source["windows"]:
        assert f"WINDOW {window['id']} /" in first


def test_missing_geometry_floating_orphan_and_process_version():
    source = snapshot()
    source["windows"][0]["layout"] = {}
    source["windows"][1]["is_floating"] = True
    source["windows"][2]["workspace_id"] = 999
    source["processes"][0]["version"] = None
    html = render_html(source)
    assert "Column Unknown" in html and "Column Floating" in html
    assert "Unresolved workspace" in html and "unknown" in html
    ET.fromstring(render_svg(source))


def test_restart_preview_is_blocked_and_desired_is_separate(tmp_path, capsys):
    store = Store(tmp_path / "private")
    source = snapshot()
    store.save_snapshot(source)
    desired = deepcopy(source)
    desired["windows"][0]["workspace_id"] = 999
    plan = build_plan(source, desired=desired, intent="restart", window_ids=[1])
    key = store.put("plans", plan)
    args = ["--state-root", str(store.root), "preview", key, "--kind", "plans"]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    markup = Path(result["html"]).read_text()
    assert "BLOCKED — NO RESTART AUTHORIZED" in markup
    assert key in markup and "Desired topology" in markup
    assert "Affected windows: [1, 2, 3]" in markup
    assert result["approval"] == "not-granted"
    assert not list((store.root / "approvals").iterdir())
    assert Path(result["html"]).stat().st_mode & 0o777 == 0o600


def recipe(kind, *argv, cwd=None, label=None, reason=None, extra=None):
    value = {"kind": kind, "argv": list(argv), "cwd": cwd, "label": label}
    if reason:
        value["reason"] = reason
    if extra:
        value["extra"] = extra
    return value


def reopen_desktop():
    """One window per recipe kind in columns 1..8, plus two sessions found in terminal tabs."""
    source = snapshot(8)
    recipes = {
        1: recipe(
            "claude",
            *("ghostty", "--working-directory=/w/api", "-e", "claude", "--resume", "0f3c"),
            cwd="/w/api",
            label="Fix login test",
            extra=[
                recipe("pi", "ghostty", "-e", "pi", "--session", "s-tab", cwd="/w/api"),
                recipe("unknown", reason="claude-session-unregistered"),
            ],
        ),
        2: recipe("pi", "ghostty", "-e", "pi", "--session", "s-2", cwd="/w/docs"),
        3: recipe(
            "declared", "ghostty", "-e", "claude", "Continue from handoff.md <b>now</b>", cwd="/w"
        ),
        4: recipe("app", "/usr/bin/obsidian"),
        5: recipe("command", "ghostty", "-e", "btop", cwd="/w"),
        6: recipe("shell", "ghostty", "--working-directory=/w", cwd="/w"),
        7: recipe("unknown", reason="xwayland-client"),
        # Window 8 was captured before reopen recipes existed.
    }
    for window in source["windows"]:
        if window["id"] in recipes:
            window["reopen"] = recipes[window["id"]]
    return source


def ledger(markup):
    start = markup.index('id="after-reboot"')
    return markup[start : markup.index("</section>", start)]


def test_after_reboot_ledger_counts_every_window_and_explains_each_miss():
    markup = render_html(reopen_desktop())
    after = ledger(markup)
    # Handwritten oracle: 8 windows + 2 tab sessions; windows 7, 8 and one tab session stay closed.
    assert "7 of 10 reopen after a reboot" in after and "3 will not" in after
    assert "8 windows + 2 sessions found in terminal tabs" in after
    assert "claude 1 · pi 2 · declared 1 · app 1 · command 1 · shell 1" in after
    assert after.count("<tr>") == 1 + 10  # header + one row per window or tab session
    assert after.count("Not reopened") == 3
    for reason in ("xwayland-client", "no-recipe", "claude-session-unregistered"):
        assert f"<code>{reason}</code>" in after
    assert "X11" in after  # the reason is explained, not only coded
    assert "claude --resume 0f3c" in after and "in /w/api" in after
    assert "&lt;b&gt;now&lt;/b&gt;" in after
    elements = Elements()
    elements.feed(markup)
    assert "b" not in elements.tags and "script" not in elements.tags
    rows = [after.index(f"WINDOW {wid}<") for wid in range(1, 9)]
    assert rows == sorted(rows)  # map order: workspace, column, tile
    assert rows[0] < after.index("pi --session s-tab") < rows[1]  # tab sessions follow their window


def test_map_tiles_state_what_comes_back():
    current = ledger_free_map(render_html(reopen_desktop()))
    assert current.count("reopens as ") == 6
    assert current.count("not reopened (") == 2
    assert "not reopened (xwayland-client)" in current and "reopens as declared" in current


def ledger_free_map(markup):
    return markup[markup.index("01 / Current observation") : markup.index('id="after-reboot"')]


def test_after_reboot_labels_follow_title_privacy():
    source = reopen_desktop()
    assert "Fix login test" not in render_html(source)
    source["privacy"]["titles_included"] = True
    assert "Fix login test" in ledger(render_html(source))


def test_plan_preview_has_no_reboot_ledger():
    source = reopen_desktop()
    markup = render_html(source, plan=build_plan(source, intent="inspect"), plan_digest="0" * 64)
    assert 'id="after-reboot"' not in markup and "reopens as " not in markup


def test_preview_defaults_to_the_latest_capture(tmp_path, capsys):
    store = Store(tmp_path / "private")
    older = store.save_snapshot(snapshot(2))
    latest = store.save_snapshot(reopen_desktop())
    assert cli.main(["--state-root", str(store.root), "preview"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["html"]).name == f"{latest}.html" != f"{older}.html"
    assert "7 of 10 reopen after a reboot" in Path(result["html"]).read_text()
    assert cli.main(["--state-root", str(store.root), "preview", "--kind", "plans"]) == 2
    assert "digest required" in capsys.readouterr().err


def test_documentation_demo_desktop_is_fabricated_and_display_valid(tmp_path):
    # The README screenshots are rendered from this fixture, never from a real capture.
    path = Path(__file__).resolve().parents[1] / "scripts/demo-desktop.py"
    spec = importlib.util.spec_from_file_location("demo_desktop", path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    source = demo.demo_snapshot()
    assert readiness(source)["ready"] and source["identity"]["boot_id"] == "demo"
    after = ledger(render_html(source))
    assert "13 of 15 reopen after a reboot" in after and "2 will not" in after
    for reason in ("claude-session-unregistered", "xwayland-client"):
        assert f"<code>{reason}</code>" in after
    assert "reopens as declared" in render_html(source)
    directories = {w["reopen"]["cwd"] for w in source["windows"]} - {None}
    assert directories == {"/work/garden-api", "/work/notes", "/work/infra"}


def test_ledger_flags_commands_rebuilt_from_a_process_title():
    source = snapshot(2)
    source["windows"][0]["reopen"] = {
        **recipe("app", "/opt/agnt/electron", "--ozone-platform=wayland", ".", cwd="/srv/agnt"),
        "argv_from_process_title": True,
    }
    source["windows"][1]["reopen"] = recipe("unknown", reason="process-title-unresolved")
    after = ledger(render_html(source))
    assert after.count("split from the process title") == 1
    assert "no program file matches" in after
