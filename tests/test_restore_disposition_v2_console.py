"""Installed wheel full new-family CLI, real ELF/pidfds, fabricated IPC and original witness."""

import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from test_restore_disposition_handwritten import handwritten, sha, state
from test_restore_disposition_v2 import make_unassociated


def test_installed_wheel_explicit_v2_full_cli(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"NIRI_SOCKET", "WAYLAND_SOCKET", "DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH"}
    }
    env.update(
        UV_OFFLINE="1",
        HOME=str(tmp_path),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_STATE_HOME=str(tmp_path / "state-home"),
    )

    def run(*argv, cwd=root):
        value = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=100)
        assert value.returncode == 0, value.stderr + value.stdout

    # Use the existing offline build cache; package installation/driver HOME is private.
    build = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist")],
        cwd=root,
        env={**os.environ, "UV_OFFLINE": "1"},
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    run("uv", "venv", "--python", sys.executable, str(tmp_path / "venv"))
    python = tmp_path / "venv/bin/python"
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        str(next((tmp_path / "dist").glob("*.whl"))),
    )
    c = tmp_path / "cooperative.c"
    c.write_text("#include <unistd.h>\nint main(void){char c;while(read(0,&c,1)>0){}return 0;}\n")
    run(shutil.which("cc"), "-o", str(tmp_path / "ghostty"), str(c))
    text = inspect.getsource(handwritten.__wrapped__)
    text = text[text.index("def handwritten") :]
    text = (
        inspect.getsource(sha)
        + inspect.getsource(state)
        + text
        + inspect.getsource(make_unassociated)
    )
    text = text.replace('"/fabricated/ghostty"', "str(binary)").replace(
        '"/fabricated/cwd"', "str(cwd)"
    )
    text = text.replace(
        '"--working-directory=/fabricated/cwd"', '"--working-directory=" + str(cwd)'
    )
    text = text.replace('"fabricated-boot"', "host.boot_id()")
    text = text.replace(
        "2000 if wid == 12000 else wid + 100", "child.pid if wid == 12000 else os.getpid()"
    )
    text = text.replace(
        '{"boot_id": identity["boot_id"], "pid": 2000, "start_ticks": 1}',
        "independent_process_pin()",
    )
    text = text.replace(
        '{"device": 1, "inode": 2, "sha256": "b" * 64}',
        '{"device": binary.stat().st_dev, "inode": binary.stat().st_ino, "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}',
    )
    text = text.replace('{"device": 1, "inode": 3}', "directory_pin")
    for line in (
        'monkeypatch.setattr(host, "Process", Process)',
        'monkeypatch.setattr(host, "Image", Image)',
        'monkeypatch.setattr(e, "Directory", Directory)',
        'monkeypatch.setattr(e, "controller_pids", lambda: {9999})',
    ):
        assert line in text
        text = text.replace("    " + line + "\n", "")
    fixture = tmp_path / "literal_fixture.py"
    fixture.write_text(
        "import hashlib\nfrom copy import deepcopy\n"
        "from niri_desktop_continuity import operation_lock\n"
        "from niri_desktop_continuity.store import Store\n" + text
    )
    driver = tmp_path / "driver.py"
    shutil.copyfile(root / "tests/restore_v2_installed_driver.py", driver)
    # Keep the inherited driver/assertions intact; supply the new routing input only
    # AFTER its clean-environment assertion and fabricated history construction.
    selector = "    disposition_cli.compositor_identity = lambda: s.identity\n"
    driver_text = driver.read_text()
    assert driver_text.count(selector) == 1
    driver.write_text(
        driver_text.replace(
            selector,
            '    os.environ["NIRI_SOCKET"] = "/fabricated/niri.sock"\n' + selector,
        )
    )
    run(
        str(python),
        str(driver),
        str(tmp_path),
        str(fixture),
        str(python.parent / "niri-desktop-continuity"),
        cwd=tmp_path,
    )
    assert json.loads((tmp_path / "outcome.json").read_text()) == {
        "installed": True,
        "native_desktop": False,
        "default_process_proofs": True,
        "exits": [0, 0, 0, 2, 2, 2, 2],
        "records": 6,
        "status": "operator-accepted-partial",
    }

    evidence = os.environ.get("NDC_TEST_WHEEL_EVIDENCE")
    if evidence:
        destination = Path(evidence)
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        for path in (
            next((tmp_path / "dist").glob("*.whl")),
            tmp_path / "outcome.json",
            driver,
            fixture,
            c,
        ):
            shutil.copyfile(path, destination / path.name)
