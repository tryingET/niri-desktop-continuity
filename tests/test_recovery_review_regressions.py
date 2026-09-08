"""Independent-review counterexamples promoted to permanent, scratch-only regressions."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture

from niri_desktop_continuity.model import digest, fingerprint, focus_pin
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.store import Store


def repin(data, settings):
    root, profile = data["root"], data["profile"]
    (root / "settings.json").write_text(json.dumps(settings))
    for pin in [profile["endpoint"], *profile["sources"]]:
        pin["sha256"] = hashlib.sha256(Path(pin["path"]).read_bytes()).hexdigest()
    (root / "profile.json").write_text(json.dumps(profile))
    config = json.loads((root / "config.json").read_text())
    config.update(profile_digest=digest(profile), endpoint=profile["endpoint"])
    (root / "config.json").write_text(json.dumps(config))


@pytest.mark.parametrize("branch", ["observed-image", "capability-btop"])
def test_utility_cannot_be_another_selected_window_host(fixture, branch):
    data = fixture(utility=branch, utility_only=True)
    snapshot = data["snapshot"]
    window = deepcopy(snapshot["windows"][0])
    window.update(id=2, pid=104, is_focused=False)
    window["layout"]["pos_in_scrolling_layout"] = [2, 1]
    snapshot["windows"].append(window)
    snapshot["processes"].append(
        {
            **snapshot["processes"][0],
            "pid": 104,
            "ppid": 101,
            "start_ticks": 45,
            "exe_sha256": "b" * 64,
            "exe_inode": 2,
        }
    )
    data["snapshot_digest"] = Store(data["root"] / "state").save_snapshot(snapshot)
    settings = json.loads((data["root"] / "settings.json").read_text())
    settings["observation"].update(
        state_fingerprint=fingerprint(snapshot), focus_digest=digest(focus_pin(snapshot))
    )
    repin(data, settings)
    with pytest.raises(ValueError):
        plan(data)
    assert not (data["root"] / "effects.jsonl").exists()
    assert not list((data["root"] / "state/approvals").glob("*.json"))


@pytest.mark.parametrize("branch", [None, "observed-image", "capability-btop"])
@pytest.mark.parametrize("damage", ["interrupted", "unresolved-child", "legacy-incomplete"])
def test_inspection_preserves_history_but_reports_adverse_accounting(
    fixture, monkeypatch, branch, damage
):
    data = fixture(**({"utility": branch} if branch else {}))
    args = []
    if branch == "capability-btop":
        settings = json.loads((data["root"] / "settings.json").read_text())
        args = ["--accept-utility-limit", settings["observation"]["utilities"][0]["utility_ref"]]
    approval = approve(data, plan(data), *args)
    executed, _ = execute(data, approval)
    terminal = data["root"] / "ledger/recovery-terminal" / f"{approval}.json"
    before = terminal.read_bytes()
    response = {
        "legacy": {"locations_digest": digest([]), "complete": True, "unresolved": 0},
        "interrupted": False,
        "unresolved_children": 0,
    }
    if damage == "interrupted":
        response["interrupted"] = True
    elif damage == "unresolved-child":
        response["unresolved_children"] = 1
    else:
        response["legacy"]["complete"] = False
    monkeypatch.setattr(Adapter, "call", lambda *a, **kw: response)
    report, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 2 and report["status"] == "indeterminate"
    assert report["historical_status"] == executed["status"]
    assert report["adapter"] == response and report["adapter_accounting"] == "valid"
    assert report["retry_authorized"] is False
    assert terminal.read_bytes() == before
