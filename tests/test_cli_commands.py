"""The commands this CLI offers, as a handwritten list rather than one read back from the parser."""

import pytest

from niri_desktop_continuity import cli

COMMANDS = {
    "approve",
    "autostart",
    "capture",
    "declare",
    "history",
    "hook",
    "inspect",
    "plan",
    "preview",
    "reconcile",
    "reconstruct",
    "restore",
    "verify",
}


def test_the_command_surface_is_exactly_the_documented_one():
    choices = cli.parser()._subparsers._group_actions[0].choices
    assert set(choices) == COMMANDS


@pytest.mark.parametrize("stage", ["inspect", "propose", "approve", "apply"])
def test_restore_disposition_is_gone(capsys, stage):
    with pytest.raises(SystemExit) as raised:
        cli.main(["restore-disposition", stage, "fabricated"])
    assert raised.value.code == 2
    assert "invalid choice: 'restore-disposition'" in capsys.readouterr().err
