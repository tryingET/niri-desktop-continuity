"""Additional scale/coverage boundaries and current-schema semantic attacks."""

from copy import deepcopy

import pytest
from test_reopen import saved
from test_restore_bounded import scaled
from test_restore_integration import integrated as integrated  # noqa: F401
from test_restore_lifecycle import rewrite_chain
from test_restore_semantics import blocked

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_dimensions as dimensions
from niri_desktop_continuity import restore_history as history


def floating(s):
    entry = s.entry(1, 1, is_floating=True)
    entry["layout"].update(
        pos_in_scrolling_layout=None, tile_pos_in_workspace_view=[-11 / 1.5, 49 / 1.5]
    )
    return entry


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, 1.0),
        (-0.5, -1.0),
        (2.5, 3.0),
        (-2.5, -3.0),
        (0.49999999999999994, 0.0),
        (-0.49999999999999994, 0.0),
    ],
)
def test_rust_round_half_away_not_python_or_add_half(value, expected):
    assert dimensions.quantize([value, value], 1.0) == [expected, expected]


def test_missing_scale_cannot_supply_a_floating_position_proof(integrated, monkeypatch):
    s = integrated
    scaled(s, monkeypatch, None)
    _, result = s.run([floating(s)])
    assert result["status"] == "interrupted" and "scale" in result["error"]
    assert result["windows"][0]["geometry_coverage"] == {
        "width": "requested-observed",
        "position": "requested-pending",
    }
    assert not any(
        a[0] in {"move-window-to-floating", "move-floating-window"} for a in s.desktop.actions
    )


@pytest.mark.parametrize("scale", [0, -1, True])
def test_invalid_scale_refuses_before_launch(integrated, monkeypatch, scale):
    s = integrated
    scaled(s, monkeypatch, scale)
    with pytest.raises(ValueError, match="scale"):
        s.run([floating(s)])
    assert not s.proofs and not s.desktop.actions


def test_live_transport_output_mapping_uses_logical_scale(integrated, monkeypatch):
    s = integrated
    scaled(s, monkeypatch, 1.5)
    desktop = restore.LiveDesktop()
    queries = []

    def query(command, *, deadline=None):
        queries.append(command)
        return {
            "outputs": lambda: {"DP-1": s.desktop.outputs()[0]},
            "windows": s.desktop.windows,
            "workspaces": s.desktop.workspaces,
        }[command]()

    monkeypatch.setattr(desktop, "_query", query)
    for name in ("action", "monotonic", "sleep"):
        monkeypatch.setattr(desktop, name, getattr(s.desktop, name))
    key = s.store.put("snapshots", saved([floating(s)]))
    result = restore.restore(
        s.store, key, desktop, apply=True, observe=s.desktop.observe, spawn_timeout=0.1
    )
    assert result["status"] == "reopened", result
    assert "outputs" in queries
    assert result["final_observation"]["outputs"] == [{"name": "DP-1", "scale": 1.5}]
    assert s.desktop.floats[12000][1] == [-11 / 1.5, 49 / 1.5]


def test_scale_drift_after_intent_stops_before_floating_dispatch(integrated, monkeypatch):
    s = integrated
    scaled(s, monkeypatch, 1.5)
    create = history.durable_create
    at_intent = []

    def drift(path, record):
        create(path, record)
        payload = s.store.get("receipts", record["receipt"])
        if (
            record["type"] == "intent"
            and payload.get("details", {}).get("argv", [None])[0] == "move-floating-window"
        ):
            at_intent.append(len(s.desktop.actions))
            monkeypatch.setattr(
                s.desktop,
                "outputs",
                lambda *, deadline=None: [{"name": "DP-1", "logical": {"scale": 1.25}}],
            )

    monkeypatch.setattr(history, "durable_create", drift)
    _, result = s.run([floating(s)])
    assert result["status"] == "interrupted"
    assert at_intent == [len(s.desktop.actions)]
    assert not any(a[0] == "move-floating-window" for a in s.desktop.actions)
    assert result["windows"][0]["geometry_coverage"]["position"] == "requested-pending"
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass


def test_already_observed_width_needs_no_decoration_guess(integrated, monkeypatch):
    s = integrated
    windows = s.desktop.windows

    def unknown(*, deadline=None):
        result = windows()
        for w in result:
            if w["id"] == 12000:
                w["layout"]["window_size"] = None
        return result

    monkeypatch.setattr(s.desktop, "windows", unknown)
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = 800.0
    _, result = s.run([entry])
    assert result["status"] == "reopened", result
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-observed"
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)


def test_unprocessed_dimensions_are_pending_not_observed(integrated, monkeypatch):
    s = integrated
    windows = s.desktop.windows

    def unknown(*, deadline=None):
        result = windows()
        for w in result:
            if w["id"] == 12000:
                w["layout"]["window_size"] = None
        return result

    monkeypatch.setattr(s.desktop, "windows", unknown)
    _, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    assert result["status"] == "interrupted"
    assert result["windows"][1]["status"] == "unprocessed"
    assert [r["geometry_coverage"]["width"] for r in result["windows"]] == ["requested-pending"] * 2


@pytest.mark.parametrize(
    "damage",
    [
        "reference-id",
        "reference-output",
        "reference-index",
        "reference-type",
        "reference-extra",
        "reference-missing",
        "scale-extra",
        "scale-change",
        "scale-missing",
        "scale-type",
        "coverage-pending",
        "coverage-preserved",
        "legacy-v2",
    ],
)
def test_v3_bound_scale_reference_and_column_coverage_are_semantic(integrated, tmp_path, damage):
    s = integrated
    matched = s.entry(1, 1)
    matched["reopen"].update(kind="pi", argv=["ghostty", "-e", "pi", "--session", "fabricated"])
    s.desktop.windows_by_id[70]["reopen"] = deepcopy(matched["reopen"])
    seed, donor = s.entry(2, 1), s.entry(3, 1, 2)
    seed["workspace_id"] = donor["workspace_id"] = 5
    seed["layout"]["tile_size"] = None
    key, result = s.run([matched, seed, donor])
    assert result["status"] == "reopened", result
    assert result["windows"][1]["geometry_coverage"]["width"] == "inherited-column"
    with operation_lock.operation_lock(s.identity):
        pass
    assert restore.restore(
        s.store, key, s.desktop, apply=True, observe=lambda: pytest.fail("historical only")
    )["historical"]
    touched = []

    def mutate(record, payload):
        assert record["schema"] == "desktop-continuity.restore-history.v3"
        if damage == "legacy-v2":
            record["schema"] = "desktop-continuity.restore-history.v2"
            touched.append(True)
        if (
            record["type"] == "intent"
            and payload.get("details", {}).get("argv", [None])[0] == "move-window-to-workspace"
        ):
            details = payload["details"]
            if damage.startswith("reference-"):
                target = details["target"]
                if damage == "reference-id":
                    target["workspace_id"] = 1
                elif damage == "reference-output":
                    target["output"] = "DP-2"
                elif damage == "reference-index":
                    target["index"] = 1
                elif damage == "reference-type":
                    target["index"] = 2.0
                elif damage == "reference-extra":
                    target["extra"] = True
                else:
                    del details["target"]
                touched.append(True)
            elif damage.startswith("scale-"):
                outputs = details["expected"]["outputs"]
                if damage == "scale-extra":
                    outputs[0]["guessed"] = True
                elif damage == "scale-change":
                    outputs[0]["scale"] = 1.25
                elif damage == "scale-type":
                    outputs[0]["scale"] = True
                else:
                    del details["expected"]["outputs"]
                touched.append(True)
        if record["type"] == "terminal" and damage.startswith("coverage-"):
            payload["windows"][1]["geometry_coverage"]["width"] = (
                "inherited-pending" if damage == "coverage-pending" else "not-recorded-preserved"
            )
            touched.append(True)

    rewrite_chain(s, mutate)  # relinks observed.intent as well as every canonical hash
    assert touched
    blocked(s, tmp_path, key)


@pytest.mark.parametrize("damage", ["off-grid-epsilon", "consistent-wrong-pixel"])
def test_float_history_must_prove_exact_observable_requested_position(
    integrated, monkeypatch, tmp_path, damage
):
    s = integrated
    scaled(s, monkeypatch, 1.5)
    key, result = s.run([floating(s)])
    assert result["status"] == "reopened", result
    with operation_lock.operation_lock(s.identity):
        pass
    expected = [-11 / 1.5, 49 / 1.5]
    wrong = (
        [expected[0] + 1e-10, expected[1]] if damage == "off-grid-epsilon" else [-8.0, expected[1]]
    )
    touched = []

    def change_state(node):
        if isinstance(node, dict):
            if (
                node.get("id") == 12000
                and node.get("is_floating")
                and node["layout"]["tile_pos_in_workspace_view"] == expected
            ):
                node["layout"]["tile_pos_in_workspace_view"] = deepcopy(wrong)
                touched.append(True)
            for value in node.values():
                change_state(value)
        elif isinstance(node, list):
            for value in node:
                change_state(value)

    def mutate(record, payload):
        assert record["schema"] == "desktop-continuity.restore-history.v3"
        change_state(payload)
        if damage == "consistent-wrong-pixel":
            if (
                record["type"] == "intent"
                and payload.get("details", {}).get("argv", [None])[0] == "move-floating-window"
            ):
                payload["details"]["argv"][4] = "-132"  # 124 -> -8 is exact on the 1.5 grid
            if record["type"] == "terminal":
                for argv in payload["effects"]:
                    if argv[0] == "move-floating-window":
                        argv[4] = "-132"

    rewrite_chain(s, mutate)
    assert touched
    with pytest.raises(ValueError) as error:
        history.load(s.identity)
    cause = str(error.value.__cause__)
    assert ("prediction" if damage == "off-grid-epsilon" else "dimension coverage") in cause
    blocked(s, tmp_path, key)
