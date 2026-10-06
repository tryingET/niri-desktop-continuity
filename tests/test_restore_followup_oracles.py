"""Supplied independent follow-up oracles; only header/import isolation adapted for v3.

Executing these copied assertions is implementer-run evidence, not independent sign-off.
"""

import json
from copy import deepcopy

import pytest
from test_reopen import saved
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.store import Store


def writer(s):
    return operation_lock.operation_lock(s.identity)


def foreign(s, tmp_path, key):
    store = Store(tmp_path / "caller-two")
    store.put("snapshots", s.store.get("snapshots", key))
    return store


def rewrite_with_references(s, mutate):
    previous, refs = None, {}
    for path in sorted(history.fence_path(s.identity).glob("*.json")):
        record = history.read(path)
        assert record["schema"] == "desktop-continuity.restore-history.v3"
        old = record["receipt"]
        payload = s.store.get("receipts", old)
        mutate(record, payload)
        if record["type"] == "observed":
            payload["intent"] = refs.get(payload["intent"], payload["intent"])
        record["receipt"] = s.store.put("receipts", payload)
        refs[old] = record["receipt"]
        record["previous"] = previous
        path.write_text(json.dumps(record))
        previous = digest(record)


@pytest.mark.parametrize("damage", ["altered-prediction", "paired-final-destination"])
def test_stronger_v3_semantic_corruption_blocks_all_consumers(integrated, tmp_path, damage):
    s = integrated
    key, good = s.run([s.entry(1, 1)])
    assert good["status"] == "reopened"
    with writer(s):
        pass
    touched = []

    def mutate(record, payload):
        if (
            damage == "altered-prediction"
            and record["type"] == "intent"
            and payload["action"] == "layout"
        ):
            # Relink observed.intent to the NEW receipt too, avoiding a dangling-reference proxy.
            next(w for w in payload["details"]["expected"]["windows"] if w["id"] == 12000)[
                "layout"
            ]["tile_size"][0] += 4
            touched.append(record["type"])
        elif damage == "paired-final-destination" and record["type"] in {
            "final-observed",
            "terminal",
        }:
            state = (
                payload["state"]
                if record["type"] == "final-observed"
                else payload["final_observation"]
            )
            w = next(w for w in state["windows"] if w["id"] == 12000)
            w["workspace_id"] = 2
            w["layout"]["pos_in_scrolling_layout"] = [1, 1]
            next(ws for ws in state["workspaces"] if ws["id"] == 2)["active_window_id"] = 12000
            if record["type"] == "terminal":
                payload["windows"][0]["target_workspace_id"] = 2
            touched.append(record["type"])

    rewrite_with_references(s, mutate)
    assert touched
    if damage == "paired-final-destination":
        assert touched == ["final-observed", "terminal"]
    other = foreign(s, tmp_path, key)
    newkey = other.put("snapshots", saved([s.entry(2, 1)]))
    before = (deepcopy(s.desktop.actions), len(s.proofs))
    with pytest.raises(ValueError, match="unresolved restore"):
        with writer(s):
            pass
    for candidate in (key, newkey):
        with pytest.raises(ValueError, match="unresolved restore"):
            restore.restore(
                other,
                candidate,
                s.desktop,
                apply=True,
                observe=lambda: pytest.fail("must not observe"),
            )
    assert before == (s.desktop.actions, len(s.proofs))


def test_extra_tab_preserves_nondefault_observed_width(integrated, monkeypatch):
    s = integrated
    add = s.desktop.add

    def unusual(pid):
        wid = add(pid)
        if pid == 2001:
            s.desktop.widths[wid] = 733.5
        return wid

    monkeypatch.setattr(s.desktop, "add", unusual)
    parent = s.entry(1, 1)
    parent["reopen"]["extra"] = [deepcopy(parent["reopen"])]
    _, result = s.run([parent])
    assert result["status"] == "reopened", result
    assert s.desktop.columns[1] == [[70, 71], [80], [12000], [12001]]
    assert s.desktop.widths[12000] == 900 and s.desktop.widths[12001] == 733.5
    assert result["windows"][1]["geometry_coverage"]["width"] == "not-recorded-preserved"


def test_floating_saved_width_without_saved_position(integrated):
    s = integrated
    entry = s.entry(1, 1, is_floating=True)
    entry["layout"]["pos_in_scrolling_layout"] = None
    entry["layout"]["tile_pos_in_workspace_view"] = None
    _, result = s.run([entry])
    assert result["status"] == "reopened", result
    assert s.desktop.floats == {12000: (1, [123.25, 91.5])}
    assert s.desktop.widths[12000] == 900
    assert result["windows"][0]["geometry_coverage"] == {
        "width": "requested-observed",
        "position": "not-recorded",
    }
    assert not any(a[0] == "move-floating-window" for a in s.desktop.actions)


def test_legal_cleanup_after_durable_intent_must_not_dispatch_stale_workspace_index(
    integrated, monkeypatch
):
    s = integrated
    d = s.desktop
    # idx1 is an inactive unnamed transient, idx2 is retained named empty, idx3 is protected/focused.
    d.columns = {1: [], 2: [], 3: [[70, 71], [80]]}
    d.ws = [
        {"id": 1, "idx": 1, "output": "DP-1", "is_focused": False},
        {"id": 2, "idx": 2, "output": "DP-1", "is_focused": False, "name": "retained"},
        {"id": 3, "idx": 3, "output": "DP-1", "is_focused": True},
    ]
    d.initialize()
    matched, target = s.entry(1, 1), s.entry(2, 1)
    matched["reopen"].update(kind="pi", argv=["ghostty", "-e", "pi", "--session", "fabricated"])
    d.windows_by_id[70]["reopen"] = deepcopy(matched["reopen"])
    target["workspace_id"] = 2
    create = history.durable_create
    changed = []

    def cleanup(path, record):
        create(path, record)
        payload = s.store.get("receipts", record["receipt"])
        if (
            record["type"] == "intent"
            and payload.get("details", {}).get("argv", [None])[0] == "move-window-to-workspace"
        ):
            assert payload["details"]["argv"][-1] == "2"
            changed.append(len(d.actions))
            d.lifecycle(cleanup=True)  # legal removal of empty idx1; stable target id2 becomes idx1
            assert next(w for w in d.ws if w["id"] == 2)["idx"] == 1

    monkeypatch.setattr(history, "durable_create", cleanup)
    key, result = s.run([matched, target])
    assert changed == [0], result
    print(
        "REINDEX",
        json.dumps(
            {
                "status": result["status"],
                "error": result.get("error"),
                "actions": d.actions,
                "columns": d.columns,
            }
        ),
    )
    assert s.store.pointer("last-reopened") is None
    with pytest.raises(ValueError, match="unresolved restore"):
        with writer(s):
            pass
    # Stopping before dispatch is safe. Reusing old numeric idx2 now addresses protected source id3.
    assert d.actions == [], (
        "stale index was dispatched after an accepted pre-effect workspace reindex"
    )
