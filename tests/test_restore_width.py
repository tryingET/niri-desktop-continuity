"""Fixed-width regression and exact, measured-decoration representability (offline only)."""

import math

import pytest
from test_restore_cli_grammar import niri_change
from test_restore_integration import integrated as integrated  # noqa: F401
from test_restore_lifecycle import rewrite_chain
from test_restore_semantics import blocked

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_geometry as geometry
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_state as states
from niri_desktop_continuity.restore_layout import Layout


def measured(s, monkeypatch, tile, decoration):
    s.desktop.decoration = decoration
    add = s.desktop.add

    def fresh(pid):
        wid = add(pid)
        s.desktop.widths[wid] = tile
        return wid

    monkeypatch.setattr(s.desktop, "add", fresh)


@pytest.mark.parametrize(
    "tile,decoration,desired,token",
    [
        (700.0, 0.0, 800.0, "800"),
        (700.0, 12.0, 800.0, "788"),
        (702.5, 2.5, 802.5, "800"),
        (102.66666666666667, 8 / 3, 1025.6666666666667, "1023"),  # inverse > 1023
        (700.0, 0.0, 100000.0, "100000"),
    ],
)
def test_integral_fixed_cli_with_exact_observable_reconstruction(
    integrated, monkeypatch, tile, decoration, desired, token
):
    s = integrated
    measured(s, monkeypatch, tile, decoration)
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = desired
    _, result = s.run([entry])
    assert result["status"] == "reopened", result
    assert [a for a in s.desktop.actions if a[0] == "set-column-width"] == [
        ("set-column-width", token)
    ]
    assert niri_change(token) == ("SetFixed", int(token))
    assert s.desktop.widths[12000] == desired
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-observed"
    with operation_lock.operation_lock(s.identity):
        pass


@pytest.mark.parametrize(
    "tile,decoration,desired",
    [
        (700.0, 0.0, 800.5),
        (700.0, 12.0, 800.5),
        (702.5, 2.5, 800.0),
        (709.6, 9.6, 1033.6),  # inverse < 1024: native Wayland floor loses a pixel
        (709.6, 9.6, math.nextafter(1033.6, math.inf)),
        (700.0, 0.0, 2147483648.0),
        (700.0, 0.0, 100001.0),  # parser accepts; native tile clamp cannot restore this
        (700.0, 12.0, 12.5),  # positive but no positive integer window width
    ],
)
def test_nonrepresentable_width_refuses_before_any_layout_dispatch(
    integrated, monkeypatch, tile, decoration, desired
):
    s = integrated
    measured(s, monkeypatch, tile, decoration)
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = desired
    _, result = s.run([entry])
    assert result["status"] == "interrupted"
    assert "fixed integer" in result["error"]
    assert len(s.proofs) == 1  # decoration is known only after fresh host association
    assert not s.desktop.actions and not result["effects"]
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-pending"
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass


def test_already_exact_fractional_width_does_not_need_integer_resize(integrated, monkeypatch):
    s = integrated
    measured(s, monkeypatch, 800.5, 12.0)
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = 800.5
    _, result = s.run([entry])
    assert result["status"] == "reopened", result
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-observed"


@pytest.mark.parametrize("saved_widths", [(None, None), (800.5, None), (None, 800.5)])
def test_shared_column_inherits_already_exact_seed_without_resize(
    integrated, monkeypatch, saved_widths
):
    s = integrated
    add = s.desktop.add

    def fresh(pid):
        wid = add(pid)
        s.desktop.widths[wid] = 800.5 if pid == 2000 else 700.0
        return wid

    monkeypatch.setattr(s.desktop, "add", fresh)
    entries = [s.entry(1, 1), s.entry(2, 1, 2)]
    for entry, width in zip(entries, saved_widths, strict=True):
        entry["layout"]["tile_size"] = None if width is None else [width, 1000.0]
    _, result = s.run(entries)
    assert result["status"] == "reopened", result
    assert [s.desktop.widths[i] for i in (12000, 12001)] == [800.5, 800.5]
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)
    assert [r["geometry_coverage"]["width"] for r in result["windows"]] == (
        ["not-recorded-preserved", "inherited-column"]
        if saved_widths == (None, None)
        else ["requested-observed" if w is not None else "inherited-column" for w in saved_widths]
    )


@pytest.mark.parametrize(
    "token", ["800.0", "800.5", "+800", "-800", "50%", "2147483648", "0", "8_00", " 800", "８００"]
)
def test_predictor_refuses_outside_admitted_fixed_integer_syntax(integrated, token):
    s = integrated
    value = states.decode(
        states.record(({w["id"]: w for w in s.desktop.windows()}, s.desktop.workspaces()))
    )
    with pytest.raises(ValueError, match="fixed integer"):
        geometry.transition(value, ["set-column-width", token], {70, 71}, {}, 70)


@pytest.mark.parametrize("token", ["888.0", "888.5", "+888", "2147483648"])
def test_semantic_history_rejects_rehashed_invalid_fixed_cli(
    integrated, monkeypatch, tmp_path, token
):
    s = integrated
    effect = Layout.effect

    def canonical_baseline(self, args, **kwargs):
        # Supply valid old-code history independently, so RED tests the decoder, not execution.
        if args[0] == "set-column-width":
            assert args[1] in {"888", "888.0"}
            args = ("set-column-width", "888")
        return effect(self, args, **kwargs)

    monkeypatch.setattr(Layout, "effect", canonical_baseline)
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened", result
    with operation_lock.operation_lock(s.identity):
        pass
    assert restore.restore(
        s.store, key, s.desktop, apply=True, observe=lambda: pytest.fail("historical only")
    )["historical"]
    touched = []

    def mutate(record, payload):
        if (
            record["type"] == "intent"
            and payload.get("details", {}).get("argv", [None])[0] == "set-column-width"
        ):
            payload["details"]["argv"][1] = token
            touched.append(True)
        if record["type"] == "terminal":
            for argv in payload["effects"]:
                if argv[0] == "set-column-width":
                    argv[1] = token

    rewrite_chain(s, mutate)
    assert touched == [True]
    with pytest.raises(ValueError) as error:
        history.load(s.identity)
    assert "fixed integer" in str(error.value.__cause__)
    blocked(s, tmp_path, key)
