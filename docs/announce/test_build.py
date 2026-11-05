"""Offline timing regressions: python3 docs/announce/test_build.py."""

from __future__ import annotations

import re
import runpy
import unittest
from html.parser import HTMLParser
from pathlib import Path


def build_html() -> str:
    return runpy.run_path(str(Path(__file__).with_name("build.py")))["build"]()


class Timeline(HTMLParser):
    def __init__(self, source: str):
        super().__init__()
        self.scenes: dict[str, tuple[float, float]] = {}
        self.animations: dict[str, list[float]] = {}
        self.duration = 0.0
        self.current_scene = ""
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "film":
            self.duration = float(attrs["data-duration"])
        if "data-start" in attrs:
            self.current_scene = attrs["id"]
            self.scenes[self.current_scene] = (
                float(attrs["data-start"]),
                float(attrs["data-duration"]),
            )
        classes = attrs.get("class", "").split()
        if self.current_scene == "blackout" and any(c in classes for c in ("title", "blackout")):
            kind = "title" if "title" in classes else "cover"
            self.animations[kind] = [
                float(value) for value in re.findall(r"(\d*\.?\d+)s\b", attrs["style"])
            ]


class ReadingTimeTests(unittest.TestCase):
    def setUp(self):
        self.timeline = Timeline(build_html())

    def test_opening_desktop_has_five_seconds(self):
        self.assertEqual(self.timeline.scenes["desktop"], (0.0, 5.0))

    def test_snapshot_has_six_seconds_after_the_opening(self):
        self.assertEqual(self.timeline.scenes["snapshot"], (5.0, 6.0))

    def test_without_warning_holds_three_seconds_after_entrance(self):
        # Given a title that needs time to enter, then be read,
        # When the blackout covers it, at least three fully entered seconds elapsed.
        duration, delay = self.timeline.animations["title"]
        _, cover_delay = self.timeline.animations["cover"]
        self.assertGreaterEqual(cover_delay - (delay + duration), 3.0)

    def test_blackout_message_keeps_its_own_reading_time(self):
        # Extending the setup must not steal the blackout message's reading time.
        start, duration = self.timeline.scenes["blackout"]
        cover_duration, cover_delay = self.timeline.animations["cover"]
        self.assertGreaterEqual(start + duration - cover_delay - cover_duration, 3.5)

    def test_scenes_remain_contiguous_to_the_film_endpoint(self):
        end = 0.0
        for name, (start, duration) in self.timeline.scenes.items():
            with self.subTest(scene=name):
                self.assertEqual(start, end)
                self.assertGreater(duration, 0)
            end = start + duration
        self.assertEqual(end, self.timeline.duration)


if __name__ == "__main__":
    unittest.main()
