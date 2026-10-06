"""Frozen handwritten Niri parser oracle; no native binary or production sizing helper.

niri-ipc/src/lib.rs @ 62c230a662ac913a54fc49c86fda0406da3f3ba9:
SizeChange i32 / PositionChange f64 (948–974), FromStr (1784–1862).
Relative and percentage widths parse, but are NOT the restore fixed-width contract.
"""

import re

import pytest


def niri_change(token, *, position=False):
    proportional = token.endswith("%")
    value = token[:-1] if proportional else token
    relative = value.startswith(("+", "-"))
    if position or proportional:
        # Rust float parsing does not accept Python's whitespace/underscore extensions.
        if not re.fullmatch(
            r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
            r"|[+-]?(?i:inf(?:inity)?|nan)",
            value,
        ):
            raise ValueError("invalid f64")
        parsed = float(value)
    else:
        if not re.fullmatch(r"[+-]?[0-9]+", value):
            raise ValueError("invalid i32")
        parsed = int(value)
        if not -(2**31) <= parsed < 2**31:
            raise ValueError("i32 overflow")
    return ("Adjust" if relative else "Set") + ("Proportion" if proportional else "Fixed"), parsed


@pytest.mark.parametrize(
    "token,expected",
    [
        ("800", ("SetFixed", 800)),
        ("000800", ("SetFixed", 800)),
        ("0", ("SetFixed", 0)),
        ("2147483647", ("SetFixed", 2147483647)),
        ("+800", ("AdjustFixed", 800)),
        ("-2147483648", ("AdjustFixed", -2147483648)),
        ("50.5%", ("SetProportion", 50.5)),
        ("+5%", ("AdjustProportion", 5.0)),
    ],
)
def test_frozen_size_change_grammar(token, expected):
    assert niri_change(token) == expected


@pytest.mark.parametrize(
    "token",
    ["800.0", "800.5", "1e3", "2147483648", "-2147483649", "", " 800", "8_00", "８００", "50%x"],
)
def test_frozen_size_change_rejects_invalid_cli(token):
    with pytest.raises(ValueError):
        niri_change(token)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("+0.125", ("AdjustFixed", 0.125)),
        ("-0.25", ("AdjustFixed", -0.25)),
        ("800.0", ("SetFixed", 800.0)),
        ("+1e-3", ("AdjustFixed", 0.001)),
    ],
)
def test_position_change_has_separate_float_grammar(token, expected):
    assert niri_change(token, position=True) == expected
