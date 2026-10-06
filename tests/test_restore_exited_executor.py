"""Actual executor/bootstrap with cooperative ELF; current diagnostics are negative compatibility."""

import json
import os
import subprocess
from copy import deepcopy

import pytest
from test_reopen import saved, window
from test_restore_exited_history import FAMILY
from test_restore_lifecycle import Niri

from niri_desktop_continuity import cli, probe, restore, restore_producer
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_attempt import Attempt


def continuation_then_diagnostic(s, root, patch):
    """Called inside the controlled namespace after real v3 commit/replay."""
    assert "NIRI_SOCKET" not in os.environ
    source, binary = root / "cooperative.c", root / "ghostty"
    source.write_text(
        "#include <unistd.h>\n#include <stdlib.h>\n"
        'int main(void){for(int i=0;i<6000 && access(getenv("NDC_TEST_QUIT"),F_OK);i++)'
        "usleep(10000);return 0;}\n"
    )
    subprocess.run(["cc", str(source), "-o", str(binary)], check=True)
    quit_file = root / "cooperative-quit"
    desktop = Niri()
    desktop.columns = {1: [[70], [71]], 2: [[80]]}
    desktop.focus = 80
    for ws in desktop.ws:
        ws["is_focused"] = ws["id"] == 2
    for w in desktop.windows_by_id.values():
        w["pid"] = os.getpid()
    desktop.initialize()
    patch.setattr(restore, "compositor_identity", lambda: s.identity)
    patch.setattr(host, "compositor_identity", lambda: s.identity)
    patch.setattr(restore, "LiveDesktop", lambda: desktop)
    patch.setattr(probe, "capture", desktop.observe)
    children = []

    def spawn(argv, identity, deadline):
        assert identity == s.identity
        child = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env={
                "PATH": os.defpath,
                "HOME": str(root / "home"),
                "NIRI_SOCKET": s.identity["niri_socket"],
                "WAYLAND_DISPLAY": "fixture",
                "XDG_RUNTIME_DIR": str(root / "runtime"),
                "NDC_TEST_QUIT": str(quit_file),
            },
        )
        children.append(child)
        desktop.add(child.pid)

    patch.setattr(restore_producer, "niri_spawn", spawn)

    def run(wid):
        cwd = root / f"cwd-{wid}"
        cwd.mkdir(mode=0o700)
        w = window(wid, 1, 1, reopen={"kind": "shell", "argv": [str(binary)], "cwd": str(cwd)})
        w["layout"]["tile_size"][0] = 800.0
        snapshot = saved([w])
        snapshot.update(
            identity=s.identity,
            niri_version=s.snapshot["niri_version"],
            process_inventory=s.snapshot["process_inventory"],
            inventory_complete=True,
        )
        key = s.store.put("snapshots", snapshot)
        return cli.run(
            cli.parser().parse_args(
                [
                    "--state-root",
                    str(s.store.root),
                    "restore",
                    key,
                    "--apply",
                    "--spawn-timeout",
                    "10",
                ]
            )
        )

    try:
        before = {w["id"]: w for w in desktop.windows()}
        continued, code = run(31)
        assert code == 0 and continued["status"] == "reopened", continued
        wid = children[0].pid + 10000
        assert desktop.columns[1] == [[70], [71], [wid]]
        assert desktop.focus == 80 and desktop.widths[wid] == 800.0
        for w in desktop.windows():
            if w["id"] in before:
                assert w["pid"] == before[w["id"]]["pid"]
                assert w["layout"]["tile_size"] == before[w["id"]]["layout"]["tile_size"]
        assert s.store.pointer("last-reopened") == continued["snapshot_digest"]
        prior_count = len(list(s.directory.glob("*.json")))
        prior_actions = len(desktop.actions)
        observed, windows = Attempt.observed, desktop.windows
        armed = False
        samples = []

        def acknowledged(attempt, evidence):
            nonlocal armed
            observed(attempt, evidence)
            if (
                len(desktop.actions) > prior_actions
                and desktop.actions[-1][0] == "focus-window"
                and "layout" in evidence
            ):
                armed = True  # Real stable focus observation has already been recorded.

        def drift(*, deadline=None):
            sample = windows(deadline=deadline)
            if armed:
                if not samples:
                    for w in sample:
                        for field in ("tile_size", "window_size"):
                            w["layout"][field][1] += 92.0
                samples.append(deepcopy(sample))
            return sample

        with pytest.MonkeyPatch.context() as refusal:
            refusal.setattr(Attempt, "observed", acknowledged)
            refusal.setattr(desktop, "windows", drift)
            result, code = run(32)
        assert code == 2 and result["error"] == "protected dimensions changed", result
        assert result["error_type"] == "ValueError" and result["status"] == "interrupted"
        new = children[1].pid + 10000
        expected = [
            ["move-window-to-workspace", "--window-id", str(new), "--focus", "false", "1"],
            ["focus-window", "--id", str(new)],
        ]
        assert result["effects"] == expected
        assert result["windows"][0]["geometry_coverage"]["width"] == "requested-observed"
        assert result["windows"][0]["status"] == "owned-not-placed"
        assert "first_rejected_observation" in result
        assert len(samples) == 2 and samples[0] != samples[1]
        records = [
            json.loads(p.read_text()) for p in sorted(s.directory.glob("*.json"))[prior_count:]
        ]
        assert [r["type"] for r in records] == [
            "prepared",
            "intent",
            "observed",
            "intent",
            "observed",
            "association",
            "intent",
            "observed",
            "intent",
            "observed",
        ]
        witness = root / "new-diagnostic-result.json"
        exit_file = root / "new-diagnostic-exit.txt"
        witness.write_text(json.dumps(result))
        exit_file.write_text("2\n")
        witness.chmod(0o600)
        exit_file.chmod(0o600)
        patch.setattr(
            proof,
            "current",
            lambda *_a, **_k: pytest.fail("diagnostic receipt must refuse before native proof"),
        )
        with pytest.raises(ValueError, match="unknown restore state fields"):
            disposition.inspect(
                s.store,
                None,
                records[0]["attempt"],
                result["receipt_digest"],
                witness,
                exit_file,
                family=FAMILY,
            )
        # No laundering: result/immutable receipt retain the genuine diagnostic field unchanged.
        assert json.loads(witness.read_text()) == result
        assert "first_rejected_observation" in s.store.get("receipts", result["receipt_digest"])
        assert len(children) == 2 and all(child.poll() is None for child in children)
        return {"continuation": "reopened", "diagnostic": "v3-refused", "new_records": 10}
    finally:
        quit_file.touch()  # Cooperative fixture-only shutdown; no product signals or cleanup.
        for child in children:
            child.stdin.close()
            assert child.wait(timeout=10) == 0
