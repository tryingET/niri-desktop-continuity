"""Default ELF/pidfd/argv/cwd proofs for v2; IPC/history and cooperative host are fabricated."""

import shutil
import time

import pytest
from test_restore_disposition_process import real_retained as real_retained  # noqa: F401
from test_restore_disposition_v2 import approve, make_unassociated, propose
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_host as host


@pytest.fixture
def real_unassociated(real_retained):
    s = real_retained
    s.directory = history.fence_path(s.identity)
    s.result, s.exit_file = s.result_path, s.exit_path
    return make_unassociated(s)


def test_real_default_v2_proof_and_no_effect_commit(real_unassociated):
    s = real_unassociated
    key = propose(s)
    assert host.process_pin(s.child.pid) in s.store.get("plans", key)["current"]["processes"]
    result = d.apply(s.store, approve(s, key), observer=s.observe)
    assert result["historical_association"] == "not-recorded" and result["effects"] == []
    assert s.child.poll() is None


@pytest.mark.parametrize("change", ["exit", "image", "argv", "cwd", "exec", "protected"])
def test_real_v2_identity_gaps_block_approval(real_unassociated, change):
    s = real_unassociated
    key = propose(s)
    if change == "exit":
        s.child.stdin.close()
        s.child.wait(timeout=10)
    elif change == "image":
        old = s.binary.with_suffix(".old")
        s.binary.rename(old)
        shutil.copyfile(old, s.binary)
        s.binary.chmod(0o700)
    elif change == "protected":
        s.desktop.windows_by_id[70]["pid"] = 2147483647
    else:
        s.child.stdin.write({"argv": b"a", "cwd": b"d", "exec": b"x"}[change])
        s.child.stdin.flush()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                approve(s, key)
            except (ValueError, OSError):
                break
            time.sleep(0.01)
        else:
            pytest.fail("cooperative host mutation was not detected")
    with pytest.raises((ValueError, OSError)):
        approve(s, key)
    assert not list((s.store.root / "used").iterdir())
    assert len(list(s.directory.iterdir())) == 5
