"""The reopen result page: what came back, what did not and why. Handwritten oracles only."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_map import Elements, recipe, reopen_desktop
from test_reopen import IDENTITY, saved, window
from test_reopen import recipe as terminal_recipe
from test_reopen_engine import Desktop

from niri_desktop_continuity import cli, launch_sessions, live_desktop, reopen
from niri_desktop_continuity.reopen_report import render_report, write_report
from niri_desktop_continuity.store import Store

SCHEMA = "desktop-continuity.restore-receipt.v1"


def receipt(snapshot_key, rows, *, status="reopened-partially", apply=True, **extra):
    return {
        "schema": SCHEMA,
        "snapshot_digest": snapshot_key,
        "started_at": "2026-11-02T20:41:09+00:00",
        "finished_at": "2026-11-02T20:41:57+00:00",
        "apply": apply,
        "protected_window_ids": [],
        "unknown_workspace_idx": None,
        "groups": len(rows),
        "windows": rows,
        "effects": [],
        "status": status,
        "failures": sum(r["status"] in {"not-reopened", "not-detected", "no-route"} for r in rows),
        **extra,
    }


def slot(window_id, status, *, extra_of=None, workspace=1, column=None, **fields):
    return {
        "window_id": window_id,
        "extra_of": extra_of,
        "saved_workspace_idx": workspace,
        "saved_workspace_name": None,
        "column": column if column is not None else window_id or extra_of,
        "tile": 1,
        "status": status,
        **fields,
    }


def mixed_rows():
    """reopen_desktop(): 8 windows + 2 tab sessions of window 1, outcomes chosen by hand."""
    return [
        slot(1, "placed", kind="claude", restored_window_id=1001),
        slot(None, "placed", extra_of=1, kind="pi", restored_window_id=1002),
        slot(
            None,
            "not-reopened",
            extra_of=1,
            kind="unknown",
            reason="claude-session-unregistered",
        ),
        slot(2, "already-open", kind="pi"),
        slot(3, "placed", kind="declared", restored_window_id=1003),
        slot(4, "not-detected", kind="app", argv=["/usr/bin/obsidian"], route="argv"),
        slot(5, "placed", kind="command", restored_window_id=1004),
        slot(6, "placed", kind="shell", restored_window_id=1005),
        slot(7, "not-reopened", kind="unknown", reason="xwayland-client"),
        slot(8, "not-reopened", kind="unknown", reason="no-recipe"),
    ]


def section(markup, anchor):
    start = markup.index(f'id="{anchor}"')
    return markup[start : markup.index("</section>", start)]


def tile(markup, window_id):
    start = markup.index(f"WINDOW {window_id} /")
    return markup[markup.rindex("<article", 0, start) : markup.index("</article>", start)]


def test_page_says_what_came_back_and_lists_every_miss_with_its_reason():
    source = reopen_desktop()
    markup = render_report(receipt("a" * 64, mixed_rows()), source)
    # Handwritten oracle: 5 placed + 1 already open of 10 rows came back; 4 did not.
    assert "6 of 10 came back" in markup and "4 did not" in markup
    missed = section(markup, "did-not-come-back")
    assert missed.count("<tr>") == 1 + 4  # header + one row per miss
    assert "X11 window" in missed and "<code>xwayland-client</code>" in missed
    assert "session registry entry" in missed and "TAB OF WINDOW 1" in missed
    assert "captured without a reopen recipe" in missed
    assert "no new window" in missed and "<code>/usr/bin/obsidian</code>" in missed
    assert "WINDOW 2" not in missed and "WINDOW 3" not in missed
    # Status is text first; color only repeats it.
    assert "BACK as window 1001" in tile(markup, 1) and 'class="tile back"' in tile(markup, 1)
    assert "ALREADY OPEN" in tile(markup, 2) and 'class="tile back"' in tile(markup, 2)
    assert "NOT BACK" in tile(markup, 4) and 'class="tile missed"' in tile(markup, 4)
    assert "NOT BACK" in tile(markup, 7) and "NOT BACK" in tile(markup, 8)
    assert "tab session: BACK" in tile(markup, 1) and "tab session: NOT BACK" in tile(markup, 1)
    assert ".back{" in markup and "var(--colors-success)" in markup
    assert ".missed{" in markup and "var(--colors-error)" in markup
    legend = markup[markup.index('class="legend"') : markup.index("</ul>")]
    for term in ("BACK</b>", "ALREADY OPEN</b>", "NOT BACK</b>"):
        assert term in legend


def test_page_has_no_active_content_and_escapes_every_saved_string():
    source = reopen_desktop()
    rows = mixed_rows()
    rows[5]["argv"] = ["</td><script>alert(1)</script>", "--x=<img src=x>"]
    markup = render_report(receipt("a" * 64, rows), source)
    elements = Elements()
    elements.feed(markup)
    assert not {"script", "img", "button", "form", "iframe", "a"} & set(elements.tags)
    assert not any(name.startswith("on") or name in {"src", "href"} for name, _ in elements.attrs)
    assert "&lt;script&gt;" in markup and "default-src 'none'" in markup


def test_titles_stay_redacted_unless_the_capture_included_them():
    source = reopen_desktop()
    source["windows"][3]["title"] = "PRIVATE DRAFT"
    assert "PRIVATE DRAFT" not in render_report(receipt("a" * 64, mixed_rows()), source)


def test_interrupted_run_says_so_and_unreached_windows_are_not_attempted():
    rows = [slot(1, "placed", kind="claude", restored_window_id=1001)]
    rows += [slot(i, "not-attempted", kind="shell") for i in range(2, 9)]
    rows += [slot(None, "not-attempted", extra_of=1, kind="pi")] * 2
    value = receipt(
        "a" * 64, rows, status="interrupted", error_type="TimeoutExpired", error="niri <msg>"
    )
    markup = render_report(value, reopen_desktop())
    assert "1 of 10 came back" in markup and "9 did not" in markup
    warning = markup[markup.index('class="warning"') :]
    assert "interrupted" in warning and "TimeoutExpired: niri &lt;msg&gt;" in warning
    assert "the run stopped before reaching it" in section(markup, "did-not-come-back")


def test_a_run_where_everything_came_back_says_so():
    rows = [slot(i, "placed", kind="shell", restored_window_id=1000 + i) for i in range(1, 9)]
    rows += [slot(None, "placed", extra_of=1, kind="pi", restored_window_id=2001)] * 2
    markup = render_report(receipt("a" * 64, rows, status="reopened"), reopen_desktop())
    assert "10 of 10 came back" in markup and "nothing was left out" in markup.lower()
    assert section(markup, "did-not-come-back").count("<tr>") == 0


def stored_receipt(store, rows, *, apply=True, mtime):
    key = store.save_snapshot(reopen_desktop())
    receipt_key = store.put("receipts", receipt(key, rows, apply=apply))
    os.utime(store.root / "receipts" / f"{receipt_key}.json", (mtime, mtime))
    return receipt_key


def test_preview_receipts_renders_the_newest_apply_run_and_refuses_dry_runs(tmp_path, capsys):
    store = Store(tmp_path / "private")
    root = ["--state-root", str(store.root), "preview", "--kind", "receipts"]
    assert cli.main(root) == 2
    assert "no restore --apply run" in capsys.readouterr().err
    older = stored_receipt(store, mixed_rows(), mtime=1_000)
    newer = stored_receipt(store, mixed_rows()[:4], mtime=2_000)
    dry = stored_receipt(store, mixed_rows()[:3], apply=False, mtime=3_000)
    assert cli.main(root) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["html"]).name == f"{newer}.html" and "svg" not in result
    assert "3 of 4 came back" in Path(result["html"]).read_text()
    assert oct(Path(result["html"]).stat().st_mode & 0o777) == "0o600"
    assert cli.main([*root, older]) == 0
    assert "6 of 10 came back" in Path(json.loads(capsys.readouterr().out)["html"]).read_text()
    assert cli.main([*root, dry]) == 2
    assert "not a restore --apply run" in capsys.readouterr().err


@pytest.fixture
def engine(tmp_path, monkeypatch):
    @contextmanager
    def lock(identity, *, effectful):
        yield  # never the live /run/user lock directory

    monkeypatch.setattr(reopen.locks, "operation_lock", lock)
    monkeypatch.setattr(reopen.probe, "compositor_identity", lambda: {**IDENTITY, "boot_id": "new"})
    monkeypatch.setattr(launch_sessions, "declaration_root", lambda: tmp_path / "declared")
    return Store(tmp_path / "state")


def test_a_real_partial_run_writes_a_page_that_matches_its_receipt(engine):
    brave = [
        window(i, 1, i, app="brave-browser", pid=50, reopen=terminal_recipe("app", "brave"))
        for i in (1, 2)
    ]
    shell = window(3, 2, 1, reopen=terminal_recipe("shell", "ghostty"))
    key = engine.put("snapshots", saved([*brave, shell]))
    desktop = Desktop(
        opens={
            ("brave",): ["brave-browser"],
            ("ghostty", "--gtk-single-instance=false"): ["com.mitchellh.ghostty"],
        }
    )
    result = reopen.reopen(
        engine,
        key,
        desktop,
        apply=True,
        observe=lambda: {"windows": desktop.windows()},
        spawn_timeout=10,
        entries=[],
        users={},
    )
    # Oracle: brave opened one of its two saved windows; the shell came back.
    assert [(w["window_id"], w["status"]) for w in result["windows"]] == [
        (1, "placed"),
        (2, "not-detected"),
        (3, "placed"),
    ]
    page = write_report(engine, result["receipt_digest"])
    markup = page.read_text()
    assert page.name == f"{result['receipt_digest']}.html"
    assert "2 of 3 came back" in markup and "1 did not" in markup
    assert "NOT BACK" in tile(markup, 2) and "BACK as window" in tile(markup, 3)


class Recorder:
    """A desktop that records, in order, the reopen run and every spawn."""

    def __init__(self, fail=None):
        self.events, self.fail = [], fail

    def spawn(self, argv):
        if self.fail:
            raise self.fail
        self.events.append(("spawn", *argv))


@pytest.fixture
def cli_run(engine, monkeypatch):
    from niri_desktop_continuity import reopen_report

    desktop = Recorder()
    key = engine.save_snapshot(reopen_desktop())

    def hermetic_reopen(store, snapshot_key, live, *, apply, spawn_timeout):
        live.events.append(("reopen", apply))
        status = "reopened-partially" if apply else "dry-run"
        value = receipt(snapshot_key, mixed_rows(), apply=apply, status=status)
        return {"receipt_digest": store.put("receipts", value), **value}

    monkeypatch.setattr(live_desktop, "LiveDesktop", lambda: desktop)
    monkeypatch.setattr(reopen, "reopen", hermetic_reopen)
    monkeypatch.setattr(reopen_report.shutil, "which", lambda name: f"/fabricated/{name}")
    args = SimpleNamespace(snapshot=key, at_login=False, apply=True, spawn_timeout=25)
    args.no_open = False
    return SimpleNamespace(args=args, desktop=desktop, store=engine, module=reopen_report)


def test_restore_apply_writes_its_result_page_and_opens_it_last(cli_run):
    result, status = cli.run_restore(cli_run.args, cli_run.store)
    assert status == 2 and result["status"] == "reopened-partially"
    page = cli_run.store.root / "previews" / f"{result['receipt_digest']}.html"
    assert Path(result["report"]) == page and "6 of 10 came back" in page.read_text()
    # Oracle: the reopen ran, then exactly one spawn opened exactly this page.
    assert cli_run.desktop.events == [
        ("reopen", True),
        ("spawn", "/fabricated/xdg-open", str(page)),
    ]
    assert result["report_open"] == "requested"
    stored = cli_run.store.get("receipts", result["receipt_digest"])
    assert "report" not in stored and "report_open" not in stored  # the receipt is unchanged
    cli_run.args.apply = False
    dry, status = cli.run_restore(cli_run.args, cli_run.store)
    assert status == 0 and "report" not in dry and "report_open" not in dry
    assert cli_run.desktop.events[-1] == ("reopen", False)


def test_no_open_writes_the_page_but_opens_nothing(cli_run):
    cli_run.args.no_open = True
    result, _ = cli.run_restore(cli_run.args, cli_run.store)
    assert Path(result["report"]).is_file() and result["report_open"] == "skipped"
    assert cli_run.desktop.events == [("reopen", True)]


def test_a_missing_or_failing_opener_never_changes_the_runs_result(cli_run, monkeypatch):
    monkeypatch.setattr(cli_run.module.shutil, "which", lambda name: None)
    result, status = cli.run_restore(cli_run.args, cli_run.store)
    assert status == 2 and result["report_open_error"] == "xdg-open not found"
    assert Path(result["report"]).is_file() and cli_run.desktop.events == [("reopen", True)]
    monkeypatch.setattr(cli_run.module.shutil, "which", lambda name: f"/fabricated/{name}")
    cli_run.desktop.fail = OSError("niri is gone")
    result, status = cli.run_restore(cli_run.args, cli_run.store)
    assert status == 2 and result["report_open_error"] == "niri is gone"


def test_recipe_helper_is_the_preview_fixture():
    # Guard: the oracles above rely on reopen_desktop() having windows 1..8 and two tab sessions.
    source = reopen_desktop()
    assert [w["id"] for w in source["windows"]] == list(range(1, 9))
    assert len(source["windows"][0]["reopen"]["extra"]) == 2
    assert recipe("shell")["kind"] == "shell"


def test_a_page_that_cannot_be_written_never_changes_the_runs_result(engine, monkeypatch):
    from niri_desktop_continuity import reopen_report

    key = engine.save_snapshot(reopen_desktop())

    def hermetic_reopen(store, snapshot_key, desktop, *, apply, spawn_timeout):
        rows = [slot(i, "placed", kind="shell", restored_window_id=1000 + i) for i in range(1, 9)]
        value = receipt(snapshot_key, rows, status="reopened", apply=apply)
        return {"receipt_digest": store.put("receipts", value), **value}

    def broken(store, key):
        raise OSError("disk full")

    desktop = Recorder()
    monkeypatch.setattr(live_desktop, "LiveDesktop", lambda: desktop)
    monkeypatch.setattr(reopen, "reopen", hermetic_reopen)
    monkeypatch.setattr(reopen_report, "write_report", broken)
    args = SimpleNamespace(snapshot=key, at_login=False, apply=True, spawn_timeout=25)
    args.no_open = False
    result, status = cli.run_restore(args, engine)
    assert status == 0 and result["status"] == "reopened"
    assert result["report_error"] == "disk full" and "report" not in result
    assert desktop.events == []  # a page that was not written is never opened


def test_times_are_shown_in_the_local_time_zone(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        source = reopen_desktop()
        source["captured_at"] = "2026-11-02T15:39:50.498260+00:00"
        markup = render_report(receipt("a" * 64, mixed_rows()), source)
    finally:
        monkeypatch.undo()
        time.tzset()
    # Oracle: 20:41 and 15:39 UTC are 21:41 and 16:39 in Berlin on 2 November (CET, +01:00).
    assert "Reopened 2026-11-02 21:41+01:00 from the capture of 2026-11-02 16:39+01:00" in markup


def test_documentation_demo_run_is_fabricated_and_shows_all_three_outcomes():
    # The README screenshot of the result page is rendered from this fixture, never a real run.
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts/demo-desktop.py"
    spec = importlib.util.spec_from_file_location("demo_desktop", path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    source = demo.demo_snapshot()
    run = demo.demo_receipt(source)
    statuses = {row["window_id"]: row["status"] for row in run["windows"]}
    # Handwritten oracle over the demo's 23 windows: 8-10 are Brave, 2 the unregistered Claude
    # session, 7 the X11 IDE, 16 Thunderbird (garden-api 1-7, web 8-11, notes 12-15, chat 16-18,
    # ops 19-23); 19 placed windows plus Thunderbird came back.
    assert (
        len(statuses) == 23 and statuses[10] == "not-detected" and statuses[16] == "already-running"
    )
    assert statuses[2] == statuses[7] == "not-reopened"
    assert sum(status == "placed" for status in statuses.values()) == 19
    markup = render_report(run, source)
    assert "20 of 23 came back" in markup and "3 did not" in markup
    missed = section(markup, "did-not-come-back")
    for code in ("claude-session-unregistered", "xwayland-client", "not-detected"):
        assert f"<code>{code}</code>" in missed
    assert "ALREADY OPEN" in tile(markup, 16) and "BACK as window 101" in tile(markup, 1)
