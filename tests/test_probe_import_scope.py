"""Feature: probe's process helpers do not import the launch-recipe module.

probe.py's proc_stat and executable_info are cheap /proc readers that consumers import on
their own; workstation saved-reopen runs them under a sealed loader that admits only a
reviewed module list. ecab334 (2026-09-16) imported launch at probe's top level for the
one function that builds recipes, capture(), and every consumer of the helpers inherited
a 460-line module it never calls -- the sealed loader refused it and saved-reopen's
machine recovery stopped at import.

Scenario: importing probe does not import launch
  Given a fresh interpreter
  When niri_desktop_continuity.probe is imported
  Then niri_desktop_continuity.launch is not in sys.modules

Scenario: capture still builds recipes
  Given probe's capture path
  Then launch.window_recipes is still what capture uses
"""

from __future__ import annotations

import inspect
import subprocess
import sys


def test_importing_probe_does_not_import_launch() -> None:
    code = (
        "import sys, niri_desktop_continuity.probe; "
        "print('niri_desktop_continuity.launch' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


def test_capture_still_uses_window_recipes() -> None:
    from niri_desktop_continuity import probe

    assert "window_recipes" in inspect.getsource(probe.capture)
