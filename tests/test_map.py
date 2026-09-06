"""Offline map contracts: escaping, privacy, complete inventory and blocked restart."""

from __future__ import annotations

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
