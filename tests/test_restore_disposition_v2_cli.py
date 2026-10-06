"""Explicit new-family selection is required; absence preserves the width-only CLI route."""

import pytest

from niri_desktop_continuity import cli


@pytest.mark.parametrize("stage", ["inspect", "propose"])
def test_given_new_family_when_cli_is_explicit_then_selection_is_preserved(stage):
    """Given accounting-only v2, when explicitly selected, then parse without altering v1 default."""
    args = [
        "restore-disposition",
        stage,
        "a" * 64,
        "--interrupted-receipt",
        "b" * 64,
        "--client-result",
        "/fabricated/result",
        "--client-exit",
        "/fabricated/exit",
    ]
    parsed = cli.parser().parse_args([*args, "--family", "exec-observed-unassociated"])
    assert parsed.family == "exec-observed-unassociated"
    assert cli.parser().parse_args(args).family is None
