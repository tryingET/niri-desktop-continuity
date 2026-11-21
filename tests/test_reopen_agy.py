"""Antigravity CLI (agy) tabs resume via `agy --conversation <id>` and never replay `-i` prompts."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest
from test_map import reopen_desktop
from test_reopen import recipe, window
from test_reopen_engine import GHOSTTY, Desktop, isolated, run, statuses  # noqa: F401

from niri_desktop_continuity import launch, launch_sessions
from niri_desktop_continuity.map_preview import render_html

SESSION_ID = "11111111-2222-3333-4444-555555555555"
OTHER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
START_TICKS = 53592767


def _stat_line(pid: int, comm: str, start_ticks: int, ppid: int = 10) -> str:
    # /proc/<pid>/stat: fields[19] after ') ' is starttime (field 22).
    fields = ["S", str(ppid), str(pid), str(pid), "0", str(pid)] + ["0"] * 13 + [str(start_ticks)]
    return f"{pid} ({comm}) " + " ".join(fields) + "\n"


def _fdinfo_line(pid: int, inode: int, *, lock_type: str = "FLOCK", mode: str = "WRITE") -> str:
    return (
        "pos:\t0\n"
        "flags:\t02100002\n"
        "mnt_id:\t103\n"
        f"ino:\t{inode}\n"
        f"lock:\t1: {lock_type}  ADVISORY  {mode} {pid} 00:23:{inode} 0 EOF\n"
    )


def _setup_fake_proc(
    tmp_path: Path,
    *,
    pid: int = 11,
    comm: str = "agy",
    start_ticks: int = START_TICKS,
    cwd: str | None = "/fabricated/proj",
    locks: list[tuple[str, str, dict]] | None = None,
) -> tuple[Path, Path]:
    """Build a fabricated /proc/<pid> tree and presence directory.

    Each lock entry is (fd_name, filename, options) where options may override:
    - target_path: custom symlink target instead of presence_root / filename
    - deleted: append " (deleted)" to symlink target
    - symlink_file: make the lockfile itself a symlink
    - fdinfo: custom fdinfo text
    - lock_type / mode / lock_pid / lock_inode: overrides for the generated fdinfo lock line
    """
    presence = tmp_path / "home" / ".gemini" / "antigravity-cli" / "presence"
    presence.mkdir(parents=True, exist_ok=True)
    proc_root = tmp_path / "proc"
    proc_dir = proc_root / str(pid)
    (proc_dir / "fd").mkdir(parents=True, exist_ok=True)
    (proc_dir / "fdinfo").mkdir(parents=True, exist_ok=True)
    (proc_dir / "stat").write_text(_stat_line(pid, comm, start_ticks))
    if cwd is not None:
        os.symlink(cwd, proc_dir / "cwd")
    for fd_name, filename, opts in locks or []:
        lock_file = presence / filename
        if opts.get("symlink_file"):
            real_target = tmp_path / f"real-{filename}"
            real_target.write_text("")
            os.symlink(real_target, lock_file)
            inode = real_target.stat().st_ino
        elif not opts.get("missing_file"):
            lock_file.write_text("")
            lock_file.chmod(0o600)
            inode = lock_file.lstat().st_ino
        else:
            inode = 999999
        target = str(opts.get("target_path", lock_file))
        if opts.get("deleted"):
            target += " (deleted)"
        os.symlink(target, proc_dir / "fd" / fd_name)
        fdinfo_text = opts.get(
            "fdinfo",
            _fdinfo_line(
                opts.get("lock_pid", pid),
                opts.get("lock_inode", inode),
                lock_type=opts.get("lock_type", "FLOCK"),
                mode=opts.get("mode", "WRITE"),
            ),
        )
        (proc_dir / "fdinfo" / fd_name).write_text(fdinfo_text)
    return proc_root, presence


def _ghostty_agy_tab(monkeypatch, proc_root: Path, presence: Path, *, via_env: bool = False):
    inventory = [
        {"pid": 10, "ppid": 1, "comm": "ghostty", "start_ticks": 1},
        {"pid": 11, "ppid": 10, "comm": "agy", "start_ticks": START_TICKS},
    ]
    if via_env:
        cmdline_10 = [
            "ghostty",
            "--working-directory=/fabricated/proj",
            "-e",
            "env",
            "AGENT_HANDOFF=/fabricated/handoff.md",
            "agy",
            "--model",
            "demo-model",
            "-i",
            "Read the handoff and carry it out.",
        ]
    else:
        cmdline_10 = [
            "ghostty",
            "--working-directory=/fabricated/proj",
            "-e",
            "agy",
            "--prompt-interactive",
            "Read the handoff and carry it out.",
        ]
    cmdlines = {
        10: cmdline_10,
        11: ["agy", "--prompt-interactive", "Read the handoff and carry it out."],
    }
    monkeypatch.setattr(launch_sessions, "agy_presence_root", lambda: presence)
    monkeypatch.setattr(
        launch,
        "agy_session",
        lambda pid, start_ticks: launch_sessions.agy_session(pid, start_ticks, proc_root=proc_root),
    )
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    monkeypatch.setattr(launch, "nodecode_session", lambda pid, start_ticks: None)
    monkeypatch.setattr(launch, "declared_session", lambda pid, start_ticks: None)
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: cmdlines[pid])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/fabricated/proj")
    return cmdline_10, launch.terminal_sessions(10, inventory)


@pytest.mark.parametrize("via_env", [False, True])
def test_agy_tab_resumes_by_conversation_id_and_never_replays_prompt(
    tmp_path, monkeypatch, via_env
):
    proc_root, presence = _setup_fake_proc(tmp_path, locks=[("45", f"{SESSION_ID}.lock", {})])
    cmdline, sessions = _ghostty_agy_tab(monkeypatch, proc_root, presence, via_env=via_env)
    expected_session = {
        "kind": "agy",
        "argv": ["agy", "--conversation", SESSION_ID],
        "cwd": "/fabricated/proj",
        "label": None,
    }
    assert sessions == [expected_session]
    reopen_recipe = launch.terminal_recipe(cmdline, sessions[0])
    assert reopen_recipe == {
        "schema": launch.RECIPE_SCHEMA,
        "kind": "agy",
        "argv": [
            "ghostty",
            "--working-directory=/fabricated/proj",
            "-e",
            "agy",
            "--conversation",
            SESSION_ID,
        ],
        "cwd": "/fabricated/proj",
        "label": None,
    }
    assert "-i" not in reopen_recipe["argv"]
    assert "--prompt-interactive" not in reopen_recipe["argv"]
    assert "Read the handoff and carry it out." not in reopen_recipe["argv"]


@pytest.mark.parametrize(
    "case",
    [
        {"locks": []},  # no presence lock held
        {"start_ticks": 99999},  # reused PID (start_ticks mismatch)
        {"comm": "python3", "locks": [("45", f"{SESSION_ID}.lock", {})]},  # wrong comm
        {"cwd": None, "locks": [("45", f"{SESSION_ID}.lock", {})]},  # unreadable cwd
        {"cwd": "relative/proj", "locks": [("45", f"{SESSION_ID}.lock", {})]},  # non-absolute cwd
        {"locks": [("45", f"{SESSION_ID}.lock", {"deleted": True})]},  # deleted lockfile
        {"locks": [("45", f"{SESSION_ID}.lock", {"symlink_file": True})]},  # symlink lockfile
        {"locks": [("45", "not-a-uuid.lock", {})]},  # invalid conversation id
        {"locks": [("45", f"{SESSION_ID}.lock", {"fdinfo": "pos:\t0\nflags:\t02100002\n"})]},
        {"locks": [("45", f"{SESSION_ID}.lock", {"mode": "READ"})]},  # shared lock, not WRITE
        {"locks": [("45", f"{SESSION_ID}.lock", {"lock_type": "POSIX"})]},  # not FLOCK
        {"locks": [("45", f"{SESSION_ID}.lock", {"lock_pid": 999})]},  # lock owned by other PID
        {"locks": [("45", f"{SESSION_ID}.lock", {"lock_inode": 12345})]},  # inode mismatch
        {
            "locks": [
                ("45", f"{SESSION_ID}.lock", {}),
                ("46", f"{OTHER_ID}.lock", {}),
            ]
        },  # ambiguous: two locks held
    ],
)
def test_unverified_agy_fails_closed_and_never_replays_prompt(tmp_path, monkeypatch, case):
    proc_root, presence = _setup_fake_proc(tmp_path, **case)
    cmdline, sessions = _ghostty_agy_tab(monkeypatch, proc_root, presence)
    assert sessions == [
        {
            "kind": "unknown",
            "argv": [],
            "cwd": None,
            "label": None,
            "reason": "agent-session-unannounced",
            "agent": "agy",
        }
    ]
    assert launch.terminal_recipe(cmdline, sessions[0]) == {
        "schema": launch.RECIPE_SCHEMA,
        "kind": "unknown",
        "argv": [],
        "cwd": None,
        "label": None,
        "reason": "agent-session-unannounced",
    }


def test_agy_session_refuses_none_start_ticks(tmp_path, monkeypatch):
    proc_root, presence = _setup_fake_proc(tmp_path, locks=[("45", f"{SESSION_ID}.lock", {})])
    monkeypatch.setattr(launch_sessions, "agy_presence_root", lambda: presence)
    assert launch_sessions.agy_session(11, None, proc_root=proc_root) is None


def test_refusal_blocks_legacy_command_app_and_other_terminal_agy_recipes():
    assert (
        launch.refusal(
            {"kind": "command", "argv": ["ghostty", "-e", "agy", "-i", "Run handoff"], "cwd": "/w"}
        )
        == "agent-session-unannounced"
    )
    assert (
        launch.refusal({"kind": "app", "argv": ["agy", "--prompt-interactive", "Hi"], "cwd": "/w"})
        == "agent-session-unannounced"
    )
    assert (
        launch.refusal(
            {"kind": "app", "argv": ["kitty", "-e", "agy", "-i", "Run handoff"], "cwd": None}
        )
        == "agent-in-other-terminal"
    )


def test_resume_template_for_agy():
    assert launch_sessions.AGENT_NAMES["agy"] == "agy"
    assert launch_sessions.RESUME_TEMPLATES["agy"] == ["agy", "--conversation", "{id}"]


def test_kernel_oracle_fdinfo_flock_matches_real_linux_proc(tmp_path):
    """Real Linux kernel oracle: fcntl.flock populates /proc/self/fdinfo/<fd> as parsed."""
    lock_path = tmp_path / f"{SESSION_ID}.lock"
    with lock_path.open("w") as stream:
        inode = lock_path.lstat().st_ino
        fdinfo_path = Path(f"/proc/{os.getpid()}/fdinfo/{stream.fileno()}")
        assert (
            launch_sessions._fdinfo_holds_flock(fdinfo_path.read_text(), os.getpid(), inode)
            is False
        )
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert (
                launch_sessions._fdinfo_holds_flock(fdinfo_path.read_text(), os.getpid(), inode)
                is True
            )
            assert (
                launch_sessions._fdinfo_holds_flock(fdinfo_path.read_text(), os.getpid() + 1, inode)
                is False
            )
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        assert (
            launch_sessions._fdinfo_holds_flock(fdinfo_path.read_text(), os.getpid(), inode)
            is False
        )


RESUME = (
    "ghostty",
    "--working-directory=/fabricated/proj",
    "-e",
    "agy",
    "--conversation",
    SESSION_ID,
)
SPAWNED = (RESUME[0], "--gtk-single-instance=false", *RESUME[1:])


def test_restore_launches_agy_conversation_in_its_terminal(tmp_path):
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("agy", *RESUME))]
    desktop = Desktop(opens={SPAWNED: [GHOSTTY]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.spawns() == [SPAWNED]
    assert statuses(result) == [(1, "placed")]


def test_already_open_agy_session_is_not_launched_again(tmp_path):
    live = [window(50, 1, 1, app=GHOSTTY, reopen=recipe("agy", *RESUME))]
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("agy", *RESUME))]
    desktop = Desktop(live=live, opens={SPAWNED: [GHOSTTY]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.spawns() == []
    assert statuses(result) == [(1, "already-open")]


def test_preview_renders_agy_session_kind():
    source = reopen_desktop()
    source["windows"][3]["reopen"] = recipe("agy", *RESUME)
    markup = render_html(source)
    assert "Antigravity CLI session, resumed by id" in markup
    assert f"--conversation {SESSION_ID}" in markup
