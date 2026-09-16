"""Opt-in systemd user units: periodic capture and reopen-at-login. Nothing is installed by default."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .store import default_root

CAPTURE = "niri-desktop-continuity-capture"
RESTORE = "niri-desktop-continuity-restore"
UNITS = (f"{RESTORE}.service", f"{CAPTURE}.service", f"{CAPTURE}.timer")


def unit_directory() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "systemd" / "user"


def command() -> str:
    return f"{sys.executable} -m niri_desktop_continuity"


def render(interval_minutes: int, state_root: Path | None) -> dict[str, str]:
    root = (state_root or default_root()).absolute()
    state = f"--state-root {root} " if state_root else ""
    exe = command()
    restore_service = f"""[Unit]
Description=Reopen the last saved Niri desktop (niri-desktop-continuity, opt-in)
After=graphical-session.target
PartOf=graphical-session.target
ConditionPathExists={root}/latest-observed.json

[Service]
Type=oneshot
ExecStart={exe} {state}restore --apply --at-login
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
"""
    capture_service = f"""[Unit]
Description=Save the current Niri desktop (niri-desktop-continuity, opt-in)
After=graphical-session.target {RESTORE}.service
PartOf=graphical-session.target

[Service]
Type=oneshot
ExecStart={exe} {state}capture
StandardOutput=journal
StandardError=journal
"""
    capture_timer = f"""[Unit]
Description=Periodic Niri desktop save (niri-desktop-continuity, opt-in)
PartOf=graphical-session.target

[Timer]
OnStartupSec={interval_minutes}min
OnUnitActiveSec={interval_minutes}min
Unit={CAPTURE}.service

[Install]
WantedBy=timers.target
"""
    return {
        f"{RESTORE}.service": restore_service,
        f"{CAPTURE}.service": capture_service,
        f"{CAPTURE}.timer": capture_timer,
    }


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", "--user", *args], check=True, capture_output=True, text=True)


def status(runner=subprocess.run) -> dict:
    directory = unit_directory()
    result = {"unit_directory": str(directory), "units": {}}
    for name in UNITS:
        path = directory / name
        state = "absent"
        if path.exists():
            completed = runner(
                ["systemctl", "--user", "is-enabled", name], capture_output=True, text=True
            )
            state = (completed.stdout or completed.stderr).strip() or "installed"
        result["units"][name] = state
    return result


def enable(
    *, interval_minutes: int = 15, state_root: Path | None = None, control=systemctl
) -> dict:
    if not 1 <= interval_minutes <= 1440:
        raise ValueError("capture interval must be 1..1440 minutes")
    directory = unit_directory()
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in render(interval_minutes, state_root).items():
        path = directory / name
        path.write_text(content)
        written.append(str(path))
    control("daemon-reload")
    control("enable", f"{RESTORE}.service", f"{CAPTURE}.timer")
    control("start", f"{CAPTURE}.timer")
    return {"enabled": True, "written": written, "interval_minutes": interval_minutes}


def disable(control=systemctl) -> dict:
    directory = unit_directory()
    removed = []
    try:
        control("disable", "--now", f"{RESTORE}.service", f"{CAPTURE}.timer")
    except subprocess.CalledProcessError:
        pass
    for name in UNITS:
        path = directory / name
        if path.exists():
            path.unlink()
            removed.append(str(path))
    control("daemon-reload")
    return {"enabled": False, "removed": removed}
