"""A nodecode tab reopens on the session its shell recorded, and only on that exact shell's record."""

from __future__ import annotations

import json

import pytest
from test_reopen import recipe, window
from test_reopen_engine import GHOSTTY, Desktop, isolated, run, statuses  # noqa: F401

from niri_desktop_continuity import launch

# The record nodecode's shell writes (nodecode-ai/nodecode#52), with fabricated values.
RECORD = {
    "version": 1,
    "kind": "nodecode-shell",
    "pid": 11,
    "start_ticks": 53592767,
    "session_id": "s-9OY5QAJT",
    "profile": "test",
    "home": "/fabricated/nodecode-home/",
    "cwd": "/fabricated/proj",
    "resume_argv": ["nodecode", "-p", "test", "resume", "s-9OY5QAJT"],
    "updated_at": 1793252467,
}
RESUMED = {
    "kind": "nodecode",
    "argv": ["nodecode", "-p", "test", "resume", "s-9OY5QAJT"],
    "cwd": "/fabricated/proj",
    "label": None,
}
# Without a usable record the tab keeps today's recipe: its shell, in its profile.
FOREGROUND = {
    "kind": "command",
    "argv": ["/opt/nodecode/nodecode", "-p", "test"],
    "cwd": "/fabricated/tab",
    "label": None,
}


@pytest.fixture
def shells(tmp_path, monkeypatch):
    runtime = tmp_path / "xdg"
    root = runtime / "nodecode" / "shells"
    root.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    def write(text, pid=11):
        path = root / f"{pid}.json"
        path.write_text(text)
        path.chmod(0o600)

    return write


def tab(monkeypatch):
    """ghostty -e nodecode -p test: the shell (start 53592767) and its detached organism."""
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty", "start_ticks": 1},
        {"pid": 11, "ppid": 10, "comm": "nodecode", "start_ticks": 53592767},
        {"pid": 12, "ppid": 11, "comm": "setsid", "start_ticks": 12},
        {"pid": 13, "ppid": 12, "comm": "nodecode", "start_ticks": 13},
    ]
    groups = {11: (11, 11), 12: (12, 11), 13: (13, -1)}
    cmdlines = {
        11: ["/opt/nodecode/nodecode", "-p", "test"],
        12: ["setsid", "-w", "/opt/nodecode/nodecode", "serve"],
        13: ["/opt/nodecode/nodecode", "serve"],
    }
    monkeypatch.setattr(launch, "job_control", lambda pid, start: groups.get(pid))
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/fabricated/tab")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    return launch.terminal_sessions(10, inventory)


def test_tab_resumes_the_session_its_shell_recorded(shells, monkeypatch):
    shells(json.dumps(RECORD))
    assert tab(monkeypatch) == [RESUMED]
    assert launch.terminal_recipe(["ghostty", "--gtk-single-instance=false"], RESUMED) == {
        "schema": launch.RECIPE_SCHEMA,
        "kind": "nodecode",
        "argv": [
            "ghostty",
            "--gtk-single-instance=false",
            "--working-directory=/fabricated/proj",
            "-e",
            "nodecode",
            "-p",
            "test",
            "resume",
            "s-9OY5QAJT",
        ],
        "cwd": "/fabricated/proj",
        "label": None,
    }


def test_custom_home_resume_command_is_kept_as_recorded(shells, monkeypatch):
    argv = ["env", "NODECODE_HOME=/fabricated/h", "nodecode", "resume", "s-9OY5QAJT"]
    shells(json.dumps({**RECORD, "resume_argv": argv}))
    assert tab(monkeypatch) == [{**RESUMED, "argv": argv}]


@pytest.mark.parametrize(
    "change",
    [
        {"start_ticks": 1},  # a record left under a pid that now names another process
        {"pid": 99},
        {"kind": "nodecode-rpc"},
        {"version": 2},
        {"session_id": None},
        {"session_id": "../s-9OY5QAJT"},
        {"resume_argv": []},
        {"resume_argv": ["nodecode", 7]},
        {"resume_argv": ["nodecode", "", "resume", "s-9OY5QAJT"]},
        {"resume_argv": ["nodecode", "resume", "s-OTHER"]},  # does not resume this session
        {"resume_argv": "nodecode resume s-9OY5QAJT"},
        {"cwd": "fabricated/proj"},
        {"cwd": None},
    ],
)
def test_malformed_or_foreign_record_keeps_the_foreground_recipe(shells, monkeypatch, change):
    shells(json.dumps({**RECORD, **change}))
    assert tab(monkeypatch) == [FOREGROUND]


@pytest.mark.parametrize("text", ["", "{", "[]", json.dumps(RECORD)[:-1]])
def test_unreadable_record_keeps_the_foreground_recipe(shells, monkeypatch, text):
    shells(text)
    assert tab(monkeypatch) == [FOREGROUND]


def test_record_of_another_shell_is_not_used(shells, monkeypatch):
    shells(json.dumps({**RECORD, "pid": 12}), pid=12)
    assert tab(monkeypatch) == [FOREGROUND]


@pytest.mark.parametrize("runtime", [None, "", "relative/xdg"])
def test_records_are_read_only_from_an_absolute_runtime_directory(shells, monkeypatch, runtime):
    shells(json.dumps(RECORD))
    if runtime is None:
        monkeypatch.delenv("XDG_RUNTIME_DIR")
    else:
        monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
    assert tab(monkeypatch) == [FOREGROUND]


RESUME = ("ghostty", "--working-directory=/fabricated/proj", "-e", *RECORD["resume_argv"])
SPAWNED = (RESUME[0], "--gtk-single-instance=false", *RESUME[1:])


def test_restore_launches_the_recorded_session_in_its_terminal(tmp_path):
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("nodecode", *RESUME))]
    desktop = Desktop(opens={SPAWNED: [GHOSTTY]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.spawns() == [SPAWNED]
    assert statuses(result) == [(1, "placed")]


def test_session_already_open_on_the_desktop_is_not_launched_again(tmp_path):
    live = [window(50, 1, 1, app=GHOSTTY, reopen=recipe("nodecode", *RESUME))]
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("nodecode", *RESUME))]
    desktop = Desktop(live=live, opens={SPAWNED: [GHOSTTY]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.spawns() == []
    assert statuses(result) == [(1, "already-open")]
