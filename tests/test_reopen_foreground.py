"""A terminal tab reopens with the command in its foreground, never a helper it detached."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import launch  # noqa: E402


def tab(monkeypatch, rows, cmdlines, cwds=None):
    """Fabricated tab under terminal 10: rows are (pid, ppid, comm, process group, foreground)."""
    inventory = [{"pid": 10, "ppid": 1, "comm": "ghostty", "start_ticks": 1}]
    groups = {}
    for pid, ppid, comm, group, foreground in rows:
        inventory.append({"pid": pid, "ppid": ppid, "comm": comm, "start_ticks": pid})
        groups[pid] = (group, foreground)
    monkeypatch.setattr(launch, "job_control", lambda pid, start: groups.get(pid))
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: (cwds or {}).get(pid, "/w"))
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    return launch.terminal_sessions(10, inventory)


def test_script_tab_whose_program_detached_its_server_reopens_the_script(monkeypatch):
    # ghostty -e start.sh: bash runs the script, which runs nodecode in the foreground; nodecode
    # started its organism through `setsid -w ... serve`, a group and then a session of its own.
    rows = [
        (11, 10, "bash", 11, 11),
        (12, 11, "nodecode", 11, 11),
        (13, 12, "setsid", 13, 11),
        (14, 13, "nodecode", 14, -1),
    ]
    cmdlines = {
        11: ["bash", "/srv/test/start.sh"],
        12: ["/opt/nodecode/nodecode"],
        13: ["setsid", "-w", "/opt/nodecode/nodecode", "serve", "--store", "/srv/test/h.db"],
        14: ["/opt/nodecode/nodecode", "serve", "--store", "/srv/test/h.db"],
    }
    sessions = tab(monkeypatch, rows, cmdlines, {11: "/srv/test/work"})
    assert sessions == [
        {
            "kind": "command",
            "argv": ["bash", "/srv/test/start.sh"],
            "cwd": "/srv/test/work",
            "label": None,
        }
    ]


def test_program_started_directly_keeps_its_own_command_not_its_daemon(monkeypatch):
    # ghostty -e nodecode -p test: the program is the job leader; its detached server is not.
    rows = [(11, 10, "nodecode", 11, 11), (12, 11, "setsid", 12, 11), (13, 12, "nodecode", 13, -1)]
    cmdlines = {
        11: ["/opt/nodecode/nodecode", "-p", "test"],
        12: ["setsid", "-w", "/opt/nodecode/nodecode", "serve"],
        13: ["/opt/nodecode/nodecode", "serve"],
    }
    (session,) = tab(monkeypatch, rows, cmdlines)
    assert session["argv"] == ["/opt/nodecode/nodecode", "-p", "test"]


def test_interactive_shell_reopens_the_job_it_runs_as_typed(monkeypatch):
    # An interactive shell gives each job its own group and puts it in the foreground: the tab
    # shows `just dev`, whose recipe runs a server; a background `sleep` is not the tab's command.
    rows = [
        (11, 10, "bash", 11, 12),
        (12, 11, "just", 12, 12),
        (13, 12, "python3", 12, 12),
        (14, 11, "sleep", 14, 12),
    ]
    cmdlines = {
        11: ["/bin/bash", "--posix"],
        12: ["just", "dev"],
        13: ["python3", "-m", "http.server"],
        14: ["sleep", "600"],
    }
    (session,) = tab(monkeypatch, rows, cmdlines, {12: "/repo"})
    assert session == {"kind": "command", "argv": ["just", "dev"], "cwd": "/repo", "label": None}


def test_idle_shell_with_only_a_background_job_reopens_as_a_shell(monkeypatch):
    rows = [(11, 10, "bash", 11, 11), (12, 11, "sleep", 12, 11)]
    cmdlines = {11: ["-bash"], 12: ["sleep", "600"]}
    (session,) = tab(monkeypatch, rows, cmdlines, {11: "/fabricated/home"})
    assert session == {"kind": "shell", "argv": [], "cwd": "/fabricated/home", "label": None}


def test_without_job_control_the_whole_tree_is_the_job(monkeypatch):
    # Unknown groups (a process gone, a reused pid): the earlier innermost-program rule applies.
    rows = [(11, 10, "bash", 11, 12), (12, 11, "just", 12, 12), (13, 12, "python3", 12, 12)]
    cmdlines = {11: ["-bash"], 12: ["just", "dev"], 13: ["python3", "-m", "http.server"]}
    inventory = [{"pid": 10, "ppid": 1, "comm": "ghostty", "start_ticks": 1}] + [
        {"pid": p, "ppid": pp, "comm": c, "start_ticks": p} for p, pp, c, _, _ in rows
    ]
    monkeypatch.setattr(launch, "job_control", lambda pid, start: None)
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/w")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    (session,) = launch.terminal_sessions(10, inventory)
    assert session["argv"] == ["python3", "-m", "http.server"]


@pytest.mark.parametrize(
    ("comm", "argv", "expected"),
    [
        ("bash", ["-bash"], True),
        ("bash", ["/bin/bash", "--posix"], True),
        ("zsh", ["zsh", "-l"], True),
        ("bash", ["bash", "/srv/test/start.sh"], False),
        # Ghostty's bash integration adds --posix to a script it starts, too.
        ("bash", ["bash", "--posix", "/srv/test/start.sh"], False),
        ("sh", ["/bin/sh", "-c", "exec tool"], False),
        ("just", ["just"], False),
    ],
)
def test_interactive_shell_means_no_script_and_no_command(monkeypatch, comm, argv, expected):
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: argv)
    assert launch.interactive_shell(1, comm) is expected


def test_job_control_reads_this_process_and_refuses_a_reused_pid():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    start = int(fields[19])
    # Handwritten oracle: the kernel's own answer for this process's group.
    group, _ = launch.job_control(os.getpid(), start)
    assert group == os.getpgrp()
    assert launch.job_control(os.getpid(), start + 1) is None
    assert launch.job_control(os.getpid(), None) is None
