"""Offline semantic history counterexamples; deliberately relink hashes, not byte-corruption tests."""

import json
from copy import deepcopy

import pytest
from test_reopen import saved
from test_restore_integration import integrated as integrated  # noqa: F401
from test_restore_lifecycle import clean, rewrite_chain

from niri_desktop_continuity import operation_lock, restore, restore_host
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.store import Store


def blocked(s, tmp_path, key):
    other = Store(tmp_path / "other")
    other.put("snapshots", s.store.get("snapshots", key))
    different = other.put("snapshots", saved([s.entry(99, 1)]))
    before = deepcopy(s.desktop.actions), len(s.proofs)
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass
    for source in (key, different):
        with pytest.raises(ValueError, match="unresolved restore"):
            restore.restore(
                other,
                source,
                s.desktop,
                apply=True,
                observe=lambda: pytest.fail("before fresh baseline"),
            )
    assert before == (s.desktop.actions, len(s.proofs))


def test_zero_effect_fabricated_already_open_without_baseline_evidence(integrated, tmp_path):
    s = integrated
    clean(s)
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened"
    paths = sorted(history.fence_path(s.identity).glob("*.json"))
    first, last = history.read(paths[0]), history.read(paths[-1])
    prepared = s.store.get("receipts", first["receipt"])
    receipt = s.store.get("receipts", last["receipt"])
    # No process/association/layout history at all; the initial entry is still unprocessed.
    receipt["windows"] = [{**prepared["plan"]["initial_accounting"][0], "status": "already-open"}]
    receipt["effects"] = []
    receipt["final_observation"] = prepared["plan"]["baseline"]
    final = {
        **first,
        "type": "final-observed",
        "seq": 1,
        "previous": digest(first),
        "receipt": s.store.put("receipts", {"state": receipt["final_observation"]}),
    }
    last.update(seq=2, previous=digest(final), receipt=s.store.put("receipts", receipt))
    paths[1].write_text(json.dumps(final))
    paths[2].write_text(json.dumps(last))
    for path in paths[3:]:
        path.unlink()
    blocked(s, tmp_path, key)


@pytest.mark.parametrize(
    "damage",
    [
        "observed-wrong-width",
        "predicted-wrong-width",
        "extra-effect",
        "duplicate-effect",
        "wrong-coverage",
        "wrong-target",
        "prepared-classification",
        "prepared-spec",
        "duplicate-tile",
        "missing-process-receipt",
        "legacy-schema",
        "final-height",
    ],
)
def test_semantically_inconsistent_history_is_not_authority(integrated, tmp_path, damage):
    s = integrated
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened"
    if damage == "missing-process-receipt":
        s.store.path("receipts", result["windows"][0]["process_receipt"]).unlink()
    else:

        def mutate(record, payload):
            if damage == "legacy-schema":
                record["schema"] = "desktop-continuity.restore-history.v1"
            if record["type"] == "terminal":
                if damage == "final-height":
                    payload["final_observation"]["windows"][-1]["layout"]["tile_size"][1] += 10
                if damage == "extra-effect":
                    payload["effects"].append(["focus-window", "--id", "70"])
                elif damage == "duplicate-effect":
                    payload["effects"] *= 2
                elif damage == "wrong-coverage":
                    payload["windows"][0]["geometry_coverage"]["width"] = "not-recorded-preserved"
                elif damage == "wrong-target":
                    payload["windows"][0]["target_workspace_id"] = 2
                elif damage == "duplicate-tile":
                    payload["final_observation"]["windows"][-1]["layout"][
                        "pos_in_scrolling_layout"
                    ] = [1, 1]
            elif record["type"] == "prepared":
                if damage == "prepared-classification":
                    payload["plan"]["initial_accounting"][0]["status"] = "already-open"
                elif damage == "prepared-spec":
                    payload["plan"]["entries"][0]["recipe"]["argv"].append("-e")
            elif (
                record["type"] == "observed"
                and damage == "observed-wrong-width"
                and "layout" in payload["evidence"]
            ):
                payload["evidence"]["layout"]["windows"][-1]["layout"]["tile_size"][0] += 3
            elif (
                record["type"] == "intent"
                and damage == "predicted-wrong-width"
                and payload["action"] == "layout"
            ):
                payload["details"]["expected"]["windows"][-1]["layout"]["tile_size"][0] += 3

        rewrite_chain(s, mutate)
    blocked(s, tmp_path, key)


def test_real_baseline_recipe_match_can_terminate_without_launch(integrated):
    s = integrated
    entry = s.entry(1, 1)
    entry["reopen"].update(kind="pi", argv=["ghostty", "-e", "pi", "--session", "fabricated"])
    s.desktop.windows_by_id[70]["reopen"] = deepcopy(entry["reopen"])
    _, result = s.run([entry])
    assert result["status"] == "reopened"
    assert result["windows"][0]["status"] == "already-open"
    assert not s.proofs and not s.desktop.actions


def test_historical_validation_does_not_reprobe_host_or_cwd(integrated, monkeypatch):
    s = integrated
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened"
    monkeypatch.setattr(
        restore_host, "admit", lambda *a: pytest.fail("historical executable admission")
    )
    monkeypatch.setattr(
        restore_host, "Image", lambda *a, **k: pytest.fail("historical executable hash")
    )
    with operation_lock.operation_lock(s.identity):
        pass
    replay = restore.restore(
        s.store, key, s.desktop, apply=True, observe=lambda: pytest.fail("historical capture")
    )
    assert replay["historical"] and replay["status"] == "reopened"


def test_capacity_refusal_is_before_preparation_or_launch(integrated, monkeypatch):
    s = integrated
    monkeypatch.setattr(history, "LIMIT", 5)
    with pytest.raises(ValueError, match="capacity"):
        s.run([s.entry(1, 1)])
    assert not history.fence_path(s.identity).exists() and not s.proofs and not s.desktop.actions
