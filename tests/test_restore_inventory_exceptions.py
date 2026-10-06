"""Inventory exceptions are permanent vetoes, not opportunities to read recovery."""

import json
from copy import deepcopy

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401
from test_restore_observation_coherence import sample, setup

from niri_desktop_continuity import restore_history, restore_layout, restore_observation


@pytest.mark.parametrize("sign", ["", "-"])
def test_huge_json_integer_prelaunch_preserves_frozen_evidence(integrated, monkeypatch, sign):
    s = integrated
    baseline = [
        {"name": "DP-1", "logical": {"scale": 8.0}},
        {"name": "DP-DISABLED", "logical": None},
    ]
    bad = deepcopy(baseline)
    # Real JSON decoding, not a mocked float conversion or a production validator oracle.
    bad[1]["extra"] = json.loads(sign + "1" + "0" * 400)
    assert type(bad[1]["extra"]) is int
    replies = [baseline, baseline, bad, baseline]
    layouts = []
    init = restore_layout.Layout.__init__

    def remember(self, *args, **kwargs):
        init(self, *args, **kwargs)
        layouts.append(self)

    def outputs(*, deadline=None):
        assert replies, "unexpected inventory resampling"
        return deepcopy(replies.pop(0))

    monkeypatch.setattr(restore_layout.Layout, "__init__", remember)
    monkeypatch.setattr(s.desktop, "outputs", outputs)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted"
    assert not s.proofs and not s.desktop.actions and not result["effects"]
    records = [
        restore_history.read(p)
        for p in sorted(restore_history.fence_path(s.identity).glob("*.json"))
    ]
    assert [r["type"] for r in records] == ["prepared"]
    assert len(layouts) == 1 and layouts[0].inventory_failed
    assert layouts[0].output_inventory == baseline
    assert replies == [baseline]  # error fallback must not consume recovery
    assert result["error_type"] == "ValueError"
    assert result["final_observation"] == {"unavailable": True}


@pytest.mark.parametrize(
    "fault",
    [
        ValueError,
        OverflowError,
        OSError,
        MemoryError,
        KeyboardInterrupt,
        SystemExit,
        GeneratorExit,
        BaseException,
    ],
)
def test_every_inventory_check_exception_latches_and_propagates(monkeypatch, fault):
    layout, desktop, _, records, _, _ = setup(monkeypatch, [sample(), sample()])
    frozen = deepcopy(layout.output_inventory)
    error = fault("fabricated inventory fault")

    def fail(*args):
        raise error

    monkeypatch.setattr(restore_observation, "check_outputs", fail)
    with pytest.raises(fault) as raised:
        layout.fresh()
    assert raised.value is error  # exact exception, never swallowed or converted to success
    assert layout.inventory_failed and layout.output_inventory == frozen
    with pytest.raises(ValueError, match="previously refused"):
        layout.read()
    assert desktop.samples == [sample()] and not records


@pytest.mark.parametrize("missing", [False, True])
def test_failed_initial_inventory_is_latched_before_propagation(monkeypatch, missing):
    owner, desktop, _, _, _, _ = setup(monkeypatch, [])
    current = sample()
    if missing:
        del current["outputs"]
    else:
        current["outputs"].append(
            {"name": "DP-DISABLED", "logical": None, "extra": json.loads("1" + "0" * 400)}
        )
    layout = restore_layout.Layout.__new__(restore_layout.Layout)
    with pytest.raises(ValueError):
        layout.__init__(owner.attempt, desktop, current, 1)
    assert layout.inventory_failed


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("offset", [0, 1])
def test_output_integer_bound_is_exact_and_never_rounded(sign, offset):
    # Handwritten binary64 maximum finite value; do not derive it from the validator.
    limit = (2**53 - 1) * 2**971
    value = json.loads(str(sign * (limit + offset)))
    outputs = [{"name": "DP-DISABLED", "logical": None, "extra": value}]
    if offset:
        with pytest.raises(ValueError, match="integer exceeds finite numeric range"):
            restore_observation.output_inventory(outputs)
    else:
        observed = restore_observation.output_inventory(outputs)
        assert type(observed[0]["extra"]) is int and observed[0]["extra"] == value
