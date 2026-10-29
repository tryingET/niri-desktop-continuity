"""Snapshot retention: the N most recent days with captures, never a referenced snapshot."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import autostart  # noqa: E402
from niri_desktop_continuity.store import Store  # noqa: E402


def noon(day: int) -> float:
    """Local noon of 2026-10-<day>, so the expected calendar day holds in any time zone."""
    return time.mktime((2026, 10, day, 12, 0, 0, 0, 0, -1))


def saved(store: Store, n: int, day: int) -> str:
    key = store.put("snapshots", {"fabricated": n})
    os.utime(store.path("snapshots", key), (noon(day), noon(day)))
    return key


def test_keeps_the_most_recent_capture_days_and_every_referenced_snapshot(tmp_path):
    store = Store(tmp_path / "state")
    history = tmp_path / "locks"
    history.mkdir()
    # Capture days 1, 2, 5, 6 and 9: the gaps are days the machine was off.
    plain = [saved(store, 1, 1), saved(store, 2, 2)]
    by_pointer = saved(store, 3, 1)
    by_receipt = saved(store, 4, 2)
    by_history = saved(store, 5, 1)
    recent = [saved(store, 6, 5), saved(store, 7, 6), saved(store, 8, 9), saved(store, 9, 9)]
    store.pointer("last-display-valid", by_pointer)
    store.put("receipts", {"snapshot_digest": by_receipt})
    (history / "attempt.json").write_text(f'{{"source": "{by_history}"}}')

    result = store.prune_snapshots(3, history=history)

    assert result == {
        "kept_days": ["2026-10-05", "2026-10-06", "2026-10-09"],
        "deleted": 2,
        "protected": 3,
    }
    left = {p.stem for p in (store.root / "snapshots").iterdir()}
    assert left == {by_pointer, by_receipt, by_history, *recent}
    assert not left & set(plain)
    assert store.pointer("last-display-valid") == by_pointer


def test_fewer_capture_days_than_kept_deletes_nothing(tmp_path):
    store = Store(tmp_path / "state")
    keys = {saved(store, 1, 1), saved(store, 2, 20)}
    result = store.prune_snapshots(3, history=tmp_path / "absent")
    assert result == {"kept_days": ["2026-10-01", "2026-10-20"], "deleted": 0, "protected": 0}
    assert {p.stem for p in (store.root / "snapshots").iterdir()} == keys


@pytest.mark.parametrize("days", [0, -1, 3651])
def test_keep_days_is_bounded(tmp_path, days):
    with pytest.raises(ValueError, match="1..3650"):
        Store(tmp_path / "state").prune_snapshots(days, history=tmp_path / "absent")


def test_autostart_capture_unit_carries_keep_days(tmp_path):
    units = autostart.render(15, None, keep_days=3)
    capture = units["niri-desktop-continuity-capture.service"]
    assert [line for line in capture.splitlines() if line.startswith("ExecStart=")] == [
        f"ExecStart={autostart.command()} capture --keep-days 3"
    ]
    plain = autostart.render(15, None)["niri-desktop-continuity-capture.service"]
    assert "--keep-days" not in plain
    with pytest.raises(ValueError, match="1..3650"):
        autostart.enable(keep_days=0, control=lambda *args: None)
