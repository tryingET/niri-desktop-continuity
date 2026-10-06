"""The six original outcome obligations, adapted to the launch-ticket transport seam."""

import pytest
from test_reopen import recipe
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_execute
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize("arrival_app", ["ghostty", "unrelated"])
def test_unowned_arrival_is_never_placed(integrated, monkeypatch, arrival_app):
    s = integrated
    launch = restore_execute.launch

    def arrival(*args, **kwargs):
        proof = launch(*args, **kwargs)
        s.desktop.add(9000)
        s.desktop.windows_by_id[19000]["app_id"] = arrival_app
        s.desktop.columns[1].remove([19000])
        s.desktop.columns[2].append([19000])
        return proof

    monkeypatch.setattr(restore_execute, "launch", arrival)
    _, result = s.run([s.entry(1, 1)])
    assert s.desktop.columns[2] == [[19000]]
    assert not s.desktop.actions
    assert not any(w.get("restored_window_id") == 19000 for w in result["windows"])
    assert result["status"] == "interrupted"


def test_missing_browser_outputs_never_authorize_relaunch(integrated):
    s = integrated
    entries = [s.entry(i, i) for i in (1, 2)]
    for entry in entries:
        entry["reopen"] = recipe("app", "brave-browser")
    _, result = s.run(entries)
    assert not s.proofs and not s.desktop.actions
    assert [w["status"] for w in result["windows"]] == ["unsupported"] * 2
    assert result["status"] == "partial"  # explicitly NOT evidence of browser restore


def test_interruption_keeps_every_unprocessed_entry_visible(integrated, monkeypatch):
    s = integrated

    def interrupted(attempt, ticket, **kwargs):
        attempt.consume(ticket)
        attempt.intent("bootstrap", {"entry": ticket.index})
        raise OSError("fabricated dispatch interruption")

    monkeypatch.setattr(restore_execute, "launch", interrupted)
    _, result = s.run([s.entry(i, i) for i in (1, 2)])
    assert [w["window_id"] for w in result["windows"]] == [1, 2]
    assert [w["status"] for w in result["windows"]] == ["launch-indeterminate", "unprocessed"]
    assert not s.desktop.actions


def test_partial_restore_never_updates_success_pointer(integrated):
    s = integrated
    unknown = s.entry(1, 1)
    unknown["reopen"] = recipe("unknown")
    _, result = s.run([unknown])
    assert result["status"] == "partial"
    assert s.store.pointer("last-reopened") is None


def test_dispatch_requires_durable_attempt_intent(integrated, monkeypatch):
    s = integrated
    original = restore_execute.launch
    observed = []

    def launch(attempt, ticket, **kwargs):
        records = sorted(history.fence_path(s.identity).glob("*.json"))
        prepared = history.read(records[0])
        payload = s.store.get("receipts", prepared["receipt"])
        observed.append(
            prepared["type"] == "prepared" and len(payload["plan"]["initial_accounting"]) == 2
        )
        return original(attempt, ticket, **kwargs)

    monkeypatch.setattr(restore_execute, "launch", launch)
    _, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    assert observed == [True, True]
    assert result["status"] == "reopened"
