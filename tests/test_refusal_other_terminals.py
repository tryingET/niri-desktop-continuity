"""A coding agent on another terminal's command line is never replayed. Handwritten oracles."""

from __future__ import annotations

import pytest
from test_map import reopen_desktop

from niri_desktop_continuity.launch import refusal
from niri_desktop_continuity.map_preview import render_html
from niri_desktop_continuity.reopen import plan

REASON = "agent-in-other-terminal"


def app(*argv):
    return {"kind": "app", "argv": list(argv), "cwd": None}


@pytest.mark.parametrize(
    "argv",
    [
        ("kitty", "-e", "claude", "Fix the flaky login test"),  # -e and an opening prompt
        ("foot", "codex", "resume"),  # foot and kitty take the program as a plain argument
        ("/usr/bin/alacritty", "-e", "sh", "-c", "cd /w && aider --yes"),  # inside a shell line
        ("wezterm", "start", "--", "/fabricated/bin/pi", "--session", "s-1"),  # by path
        ("konsole", "-e", "angel", "--prompt", "draft the notes"),  # angel is angelX
        ("Kitty", "-e", "CLAUDE"),  # names compare case-insensitively, like the agent table
    ],
)
def test_an_agent_on_another_terminals_command_line_is_refused(argv):
    assert refusal(app(*argv)) == REASON


@pytest.mark.parametrize(
    "argv",
    [
        ("kitty",),  # a terminal you typed into: nothing on its line replays
        ("kitty", "-e", "htop"),  # an ordinary command still comes back
        ("alacritty", "-e", "sh", "-c", "npm run dev"),
        ("code", "/work/pi"),  # not a terminal: an editor opening a folder named pi
        ("ghostty", "--gtk-single-instance=false"),  # Ghostty tabs have their own readers
    ],
)
def test_ordinary_terminal_commands_and_other_apps_still_reopen(argv):
    assert refusal(app(*argv)) is None


def test_the_check_errs_on_the_safe_side_for_a_word_that_names_an_agent():
    # A terminal titled "pi notes" stays closed with its reason: refusing is the safe mistake.
    assert refusal(app("kitty", "--title", "pi notes")) == REASON


def test_plan_and_preview_refuse_it_with_a_plain_reason():
    source = reopen_desktop()
    source["windows"][3]["app_id"] = "kitty"
    source["windows"][3]["reopen"] = app("kitty", "-e", "claude", "Fix the flaky login test")
    planned = plan(source, [], entries=[], users={})
    slot = next(s for s in planned["slots"] if s["window_id"] == 4)
    assert slot["status"] == "not-reopened" and slot["reason"] == REASON
    assert all(4 not in [s["window_id"] for s in g["slots"]] for g in planned["groups"])
    markup = render_html(source)
    assert f"<code>{REASON}</code>" in markup and "other than Ghostty" in markup
    assert "nothing is launched" in markup
