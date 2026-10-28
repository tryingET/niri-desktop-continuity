"""IS-2 small restorer: handwritten oracles on a fake Niri desktop. Nothing contacts a compositor."""

from __future__ import annotations

import io
import json
import os
from contextlib import contextmanager

import pytest
from test_reopen import IDENTITY, recipe, saved, window

from niri_desktop_continuity import cli, launch, reopen, routes
from niri_desktop_continuity.store import Store

GHOSTTY = "com.mitchellh.ghostty"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    locks = []

    @contextmanager
    def lock(identity, *, effectful):
        locks.append(effectful)  # never the live /run/user lock directory
        yield

    monkeypatch.setattr(reopen.locks, "operation_lock", lock)
    monkeypatch.setattr(reopen.probe, "compositor_identity", lambda: {**IDENTITY, "boot_id": "new"})
    monkeypatch.setattr(launch, "declaration_root", lambda: tmp_path / "declared")
    return locks


class Desktop:
    """Each launch opens the scripted windows of the scripted app; every action is recorded."""

    def __init__(self, live=(), opens=None):
        self.live = [dict(w) for w in live]
        self.opens = opens or {}  # argv tuple -> list of app IDs, one per window it opens
        self.actions: list[tuple] = []
        self.next_id = 1000
        self.clock = 0.0

    def windows(self):
        return [dict(w) for w in self.live]

    def workspaces(self):
        return [{"id": i, "idx": i, "output": "DP-1"} for i in (1, 2, 3, 4)]

    def spawn(self, argv):
        self.actions.append(("spawn", tuple(argv)))
        for app in self.opens.get(tuple(argv), []):
            self.next_id += 1
            self.live.append(window(self.next_id, 1, len(self.live) + 1, app=app))

    def action(self, *args):
        self.actions.append(args)
        if args[0] == "move-window-to-workspace":
            for w in self.live:
                if w["id"] == int(args[2]):
                    w["workspace_id"] = int(args[-1])

    def sleep(self, seconds):
        self.clock += seconds

    def monotonic(self):
        return self.clock

    def spawns(self):
        return [a[1] for a in self.actions if a[0] == "spawn"]


def run(tmp_path, windows, desktop, *, apply=True, entries=(), users=None):
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved(windows))
    observe = lambda: {"windows": desktop.windows()}  # noqa: E731
    return reopen.reopen(
        store,
        key,
        desktop,
        apply=apply,
        observe=observe,
        spawn_timeout=10,
        entries=list(entries),
        users=users or {},
    )


def entry(entry_id, *argv, wm_class=None):
    return routes.Entry(entry_id, f"/fabricated/{entry_id}", tuple(argv), wm_class, None)


def statuses(result):
    return [(w["window_id"], w["status"]) for w in result["windows"]]


# --- Rule A: apps launch once, adopt only their own new windows ----------------------------


def test_browser_group_launches_once_and_fills_saved_slots_in_order(tmp_path):
    brave = [
        window(i, 1, i, app="brave-browser", pid=50, reopen=recipe("app", "brave"))
        for i in (1, 2, 3)
    ]
    desktop = Desktop(opens={("brave",): ["brave-browser"] * 3})
    result = run(tmp_path, brave, desktop, entries=[entry("brave-browser.desktop", "brave")])
    assert desktop.spawns() == [("brave",)]  # one launch, never a second after a wait
    assert statuses(result) == [(1, "placed"), (2, "placed"), (3, "placed")]
    assert [w["restored_window_id"] for w in result["windows"]] == [1001, 1002, 1003]
    assert result["status"] == "reopened" and result["groups"] == 1


def test_fewer_windows_than_saved_is_partial_and_never_relaunched(tmp_path):
    brave = [
        window(i, 1, i, app="brave-browser", pid=50, reopen=recipe("app", "brave"))
        for i in (1, 2, 3)
    ]
    desktop = Desktop(opens={("brave",): ["brave-browser"]})
    result = run(tmp_path, brave, desktop, entries=[entry("brave-browser.desktop", "brave")])
    assert desktop.spawns() == [("brave",)]
    assert statuses(result) == [(1, "placed"), (2, "not-detected"), (3, "not-detected")]
    assert result["status"] == "reopened-partially" and result["failures"] == 2


def test_another_apps_window_is_never_adopted(tmp_path):
    saved_windows = [window(1, 1, 1, app="x", reopen=recipe("app", "x"))]
    desktop = Desktop(opens={("x",): ["unrelated"]})
    result = run(tmp_path, saved_windows, desktop)
    assert statuses(result) == [(1, "not-detected")]
    assert [a for a in desktop.actions if a[0] != "spawn"] == []  # nothing moved


def test_running_app_is_not_launched_and_its_windows_are_untouched(tmp_path):
    live = [window(7, 2, 1, app="md.Obsidian")]
    saved_windows = [window(1, 1, 1, app="md.Obsidian", reopen=recipe("app", "obsidian"))]
    desktop = Desktop(live, opens={("obsidian",): ["md.Obsidian"]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.actions == []
    assert statuses(result) == [(1, "already-running")]
    assert result["windows"][0]["route"] == "argv"  # what would launch, shown though skipped
    assert result["protected_window_ids"] == [7] and desktop.live[0]["workspace_id"] == 2


def test_deep_link_is_not_replayed_the_desktop_entry_launches_the_app(tmp_path):
    link = "grokbot://app/v1/bot-template?id=fabricated"
    saved_windows = [
        window(1, 1, 1, app="grok-bot", reopen=recipe("app", "/opt/Grok Bot/grok-bot", link))
    ]
    desktop = Desktop(opens={("grok-bot",): ["grok-bot"]})
    result = run(tmp_path, saved_windows, desktop, entries=[entry("grok-bot.desktop", "grok-bot")])
    assert desktop.spawns() == [("grok-bot",)]
    assert result["windows"][0]["route"] == "desktop:grok-bot.desktop"


def test_wrapper_launched_app_reopens_through_its_launcher_not_electron(tmp_path):
    electron = ("/srv/agnt/node_modules/electron/dist/electron", ".", "--ozone-platform=wayland")
    saved_windows = [window(1, 1, 1, app="AGNT", reopen=recipe("app", *electron))]
    start = entry("agnt.desktop", "/srv/agnt/tools/agnt-start.sh", wm_class="AGNT")
    desktop = Desktop(opens={("/srv/agnt/tools/agnt-start.sh",): ["AGNT"]})
    result = run(tmp_path, saved_windows, desktop, entries=[start])
    assert desktop.spawns() == [("/srv/agnt/tools/agnt-start.sh",)]
    assert statuses(result) == [(1, "placed")]


def test_app_id_without_matching_entry_name_resolves_by_its_executable(tmp_path):
    image = tmp_path / "Obsidian.AppImage"
    image.write_text("")
    obsidian = entry("obsidian.desktop", str(image), wm_class="obsidian")
    saved_windows = [window(1, 1, 1, app="md.Obsidian", reopen=recipe("app", str(image)))]
    desktop = Desktop(opens={(str(image),): ["md.Obsidian"]})
    result = run(tmp_path, saved_windows, desktop, entries=[obsidian])
    assert result["windows"][0]["route"] == "desktop:obsidian.desktop"
    assert statuses(result) == [(1, "placed")]


def test_two_profiles_are_two_serial_groups_with_their_own_commands(tmp_path):
    work = ("brave", "--profile-directory=Work")
    saved_windows = [
        window(
            1, 1, 1, app="brave-browser", pid=50, reopen=recipe("app", "brave", "https://x.test")
        ),
        window(2, 1, 2, app="brave-browser", pid=60, reopen=recipe("app", *work)),
        window(3, 1, 3, app="brave-browser", pid=60, reopen=recipe("app", *work)),
    ]
    # The first launch restores one extra window; the second group must not take it.
    desktop = Desktop(opens={("brave",): ["brave-browser"] * 2, work: ["brave-browser"] * 2})
    result = run(
        tmp_path, saved_windows, desktop, entries=[entry("brave-browser.desktop", "brave")]
    )
    assert desktop.spawns() == [("brave",), work]  # URL dropped; one entry cannot name a profile
    assert [w["restored_window_id"] for w in result["windows"]] == [1001, 1003, 1004]
    assert result["status"] == "reopened"


def test_no_route_is_reported_not_guessed(tmp_path):
    saved_windows = [window(1, 1, 1, app="mystery", reopen=recipe("unknown"))]
    desktop = Desktop()
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.actions == [] and result["windows"][0]["status"] == "not-reopened"


def test_user_route_overrides_the_automatic_rules(tmp_path):
    saved_windows = [window(1, 1, 1, app="x", reopen=recipe("app", "x", "--old"))]
    desktop = Desktop(opens={("x", "--new"): ["x"]})
    result = run(tmp_path, saved_windows, desktop, users={"x": {"argv": ["x", "--new"]}})
    assert desktop.spawns() == [("x", "--new")] and result["windows"][0]["route"] == "user"


# --- Rule B: terminals ----------------------------------------------------------------------


def test_terminal_keeps_user_config_cwd_and_command(tmp_path):
    argv = ["ghostty", "--config-default-files=false", "--working-directory=/w", "-e", "btop"]
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("command", *argv))]
    expected = ("ghostty", "--gtk-single-instance=false", "--working-directory=/w", "-e", "btop")
    desktop = Desktop(opens={expected: [GHOSTTY]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.spawns() == [expected]
    assert statuses(result) == [(1, "placed")]


def test_each_terminal_window_is_its_own_launch_and_extra_tabs_get_windows(tmp_path):
    tab = recipe("shell", "ghostty", "--working-directory=/b")
    saved_windows = [
        window(
            1,
            1,
            1,
            app=GHOSTTY,
            reopen=recipe("shell", "ghostty", "--working-directory=/a", extra=[tab]),
        ),
        window(2, 1, 2, app=GHOSTTY, reopen=recipe("shell", "ghostty", "--working-directory=/c")),
    ]
    desktop = Desktop()
    desktop.opens = {
        ("ghostty", "--gtk-single-instance=false", f"--working-directory={d}"): [GHOSTTY]
        for d in ("/a", "/b", "/c")
    }
    result = run(tmp_path, saved_windows, desktop)
    assert len(desktop.spawns()) == 3 and result["status"] == "reopened"


# --- dry run, fences, receipts ---------------------------------------------------------------


def test_dry_run_shows_routes_and_has_no_effects(tmp_path, isolated):
    saved_windows = [
        window(1, 1, 1, app="grok-bot", reopen=recipe("app", "grok-bot", "grokbot://a"))
    ]
    desktop = Desktop()
    result = run(
        tmp_path,
        saved_windows,
        desktop,
        apply=False,
        entries=[entry("grok-bot.desktop", "grok-bot")],
    )
    assert desktop.actions == [] and result["status"] == "dry-run"
    assert result["windows"][0] | {} == result["windows"][0]
    assert (result["windows"][0]["status"], result["windows"][0]["argv"]) == (
        "planned",
        ["grok-bot"],
    )
    assert isolated == [False]  # a dry run never asks for effect admission


def test_apply_asks_for_effect_admission_so_unresolved_attempts_still_block(tmp_path, isolated):
    run(tmp_path, [window(1, 1, 1, app="x", reopen=recipe("app", "x"))], Desktop())
    assert isolated == [True]


# --- Rule C: agents announce their own session ------------------------------------------------


def surface(comm, start=50):
    return [
        {"pid": 11, "ppid": 10, "comm": "bash", "start_ticks": 40},
        {"pid": 12, "ppid": 11, "comm": comm, "start_ticks": start},
    ]


@pytest.mark.parametrize("comm", ["codex", "angel", "gemini"])
def test_unannounced_agent_is_refused_never_replayed(comm, monkeypatch):
    monkeypatch.setattr(launch, "read_cmdline", lambda pid: [comm, "fabricated opening prompt"])
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/w")
    monkeypatch.setattr(launch, "claude_session", lambda pid: None)
    monkeypatch.setattr(launch, "pi_session", lambda pid: None)
    (session,) = launch.terminal_sessions(10, surface(comm))
    assert session["kind"] == "unknown" and session["reason"] == "agent-session-unannounced"
    assert "fabricated opening prompt" not in json.dumps(session)


def hook(monkeypatch, tmp_path, payload, template=None, comm="codex", terminal=True):
    # Fabricated chain: hook shell 13 -> agent 12 -> tab shell 11 -> terminal 10 (or a daemon).
    monkeypatch.setattr(launch.shutil, "which", lambda name: f"/fabricated/bin/{name}")
    monkeypatch.setattr(launch, "read_cwd", lambda pid: "/fabricated/cwd")  # never real /proc
    parents = {13: 12, 12: 11, 11: 10, 10: 1}
    monkeypatch.setattr(
        "niri_desktop_continuity.probe.proc_stat",
        lambda pid: {"pid": pid, "ppid": parents[pid], "start_ticks": {12: 50}.get(pid, 1)},
    )
    comms = {13: "sh", 12: comm, 11: "bash", 10: "ghostty" if terminal else "codex-daemon"}
    real = launch.Path

    class Proc(type(real())):
        def read_text(self, *args, **kwargs):
            parts = self.parts
            if len(parts) == 4 and parts[1] == "proc" and parts[3] == "comm":
                return comms[int(parts[2])] + "\n"
            return super().read_text(*args, **kwargs)

    monkeypatch.setattr(launch, "Path", Proc)
    monkeypatch.setattr(launch, "declaration_root", lambda: real(tmp_path) / "declared")
    return launch.hook_declaration(comm, payload, template, 13)


def test_hook_declares_the_current_session_and_a_switch_replaces_it(tmp_path, monkeypatch):
    first = hook(monkeypatch, tmp_path, {"session_id": "11111111-aaaa", "cwd": "/w"})
    assert first["pid"] == 12 and first["start_ticks"] == 50
    assert first["argv"] == ["/fabricated/bin/codex", "resume", "11111111-aaaa"]
    second = hook(monkeypatch, tmp_path, {"session_id": "22222222-bbbb", "cwd": "/w"})
    stored = json.loads((tmp_path / "declared" / "12.json").read_text())
    assert stored["argv"][-1] == "22222222-bbbb" == second["argv"][-1]
    assert launch.declared_session(12, 50)["argv"][-1] == "22222222-bbbb"


def test_hook_takes_a_template_for_any_agent_and_rejects_odd_ids(tmp_path, monkeypatch):
    value = hook(
        monkeypatch, tmp_path, {"session_id": "s1"}, ["myagent", "--continue", "{id}"], "myagent"
    )
    assert value["argv"] == ["/fabricated/bin/myagent", "--continue", "s1"]
    with pytest.raises(ValueError, match="session_id"):
        hook(monkeypatch, tmp_path, {"session_id": "; rm -rf ~"})
    with pytest.raises(ValueError, match="no resume template"):
        hook(monkeypatch, tmp_path, {"session_id": "s1"}, None, "unknownagent")


def test_hook_command_never_exits_2(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert cli.main(["hook", "codex"]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "error"


# --- routes: Desktop Entry Exec parsing and the routes file --------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("grok-bot %U", ["grok-bot"]),
        ('"/opt/Grok Bot/grok-bot" %u', ["/opt/Grok Bot/grok-bot"]),
        ("app --flag=%%u --file=%f", ["app", "--flag=%u", "--file="]),
        ('app "a \\"quoted\\" word"', ["app", 'a "quoted" word']),
        ("app\\sarg", ["app", "arg"]),  # \\s is a space before quoting rules
        ('app "unterminated', None),
        ("app %z", None),
        ("app 'single'", None),
        ("%U", None),
    ],
)
def test_exec_parsing_follows_the_desktop_entry_spec(value, expected):
    assert routes.exec_argv(value) == expected


def test_entries_follow_xdg_precedence_and_skip_hidden_or_terminal(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    user.mkdir()
    system.mkdir()
    (user / "a.desktop").write_text("[Desktop Entry]\nType=Application\nExec=user-a\n")
    (system / "a.desktop").write_text("[Desktop Entry]\nType=Application\nExec=system-a\n")
    (system / "b.desktop").write_text("[Desktop Entry]\nType=Application\nExec=b\nHidden=true\n")
    (system / "c.desktop").write_text("[Desktop Entry]\nType=Application\nExec=c\nTerminal=true\n")
    found = routes.desktop_entries([user, system])
    assert [(e.id, e.argv) for e in found] == [("a.desktop", ("user-a",))]


def test_routes_file_must_be_private_and_well_formed(tmp_path):
    path = tmp_path / "routes.json"
    path.write_text(json.dumps({"routes": {"x": {"argv": ["x"]}}}))
    os.chmod(path, 0o644)
    assert routes.user_routes(path) == {"x": {"argv": ["x"]}}
    os.chmod(path, 0o666)
    with pytest.raises(ValueError, match="not writable by others"):
        routes.user_routes(path)
    os.chmod(path, 0o600)
    path.write_text(json.dumps({"routes": {"x": {"argv": []}}}))
    with pytest.raises(ValueError, match="needs"):
        routes.user_routes(path)
    assert routes.user_routes(tmp_path / "absent.json") == {}


def test_saved_tile_width_is_requested_net_of_the_measured_border(tmp_path):
    # Niri's fixed column width is the window's; the saved width is the tile's (window + border).
    class Bordered(Desktop):
        def spawn(self, argv):
            super().spawn(argv)
            self.live[-1]["layout"]["window_size"] = [888.0, 988.0]  # 12 px decoration

    argv = ("ghostty", "--gtk-single-instance=false", "--working-directory=/w")
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=recipe("shell", *argv))]
    desktop = Bordered(opens={argv: [GHOSTTY]})
    run(tmp_path, saved_windows, desktop)
    assert ("set-column-width", "888") in desktop.actions  # 900 saved tile - 12 border


def test_old_captured_agent_command_is_refused_not_replayed(tmp_path):
    # Captures made before agent refusal recorded a Codex tab as a plain command with its prompt.
    old = recipe("command", "ghostty", "--working-directory=/w", "-e", "codex", "opening prompt")
    saved_windows = [window(1, 1, 1, app=GHOSTTY, reopen=old)]
    desktop = Desktop()
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.actions == []
    assert (result["windows"][0]["status"], result["windows"][0]["reason"]) == (
        "not-reopened",
        "agent-session-unannounced",
    )
    from niri_desktop_continuity import map_preview

    shown = map_preview.reopen_html(saved(saved_windows))
    assert "0 of 1 reopen" in shown and "coding agent without an announced session" in shown


def test_agent_outside_a_terminal_declares_nothing(tmp_path, monkeypatch):
    # Codex's shared app-server daemon runs the session outside any terminal tab.
    value = hook(monkeypatch, tmp_path, {"session_id": "s1", "cwd": "/w"}, terminal=False)
    assert value is None and not (tmp_path / "declared").exists()


@pytest.mark.parametrize("declared", [{"pid": 12}, None])
def test_hook_prints_nothing_on_stdout(declared, monkeypatch, capsys):
    # SessionStart hooks feed stdout into the agent's context; keep it empty.
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s1"})))
    monkeypatch.setattr(launch, "hook_declaration", lambda *args: declared)
    assert cli.main(["hook", "codex"]) == 0
    output = capsys.readouterr()
    assert output.out == ""
    assert ("not inside a terminal" in output.err) is (declared is None)


def test_agent_in_its_own_window_is_refused_not_relaunched_with_its_prompt(tmp_path):
    gui = recipe("app", "/usr/bin/angelX", "/w", "--prompt", "opening prompt")
    saved_windows = [window(1, 1, 1, app="angelx", reopen=gui)]
    desktop = Desktop(opens={("/usr/bin/angelX", "/w", "--prompt", "opening prompt"): ["angelx"]})
    result = run(tmp_path, saved_windows, desktop)
    assert desktop.actions == []
    assert result["windows"][0]["reason"] == "agent-session-unannounced"
