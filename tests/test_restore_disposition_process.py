"""Real default /proc, ELF and pidfd validation; IPC/history are fabricated, not native."""

import os
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest
from test_restore_disposition import approval, fabricate_retained, fenced, observer, proposal
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_execute, restore_host


@pytest.fixture
def real_retained(integrated, tmp_path, monkeypatch):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler required for real default process evidence")
    source = tmp_path / "cooperative.c"
    source.write_text(
        "#include <unistd.h>\n#include <stdio.h>\n"
        "int main(int n, char **v) { char c, alt[4096]; while(read(0,&c,1)>0) {"
        "if(c=='a' && n>1) v[1][2]='X';"
        "if(c=='d') chdir(\"/\");"
        "if(c=='x') { snprintf(alt,sizeof alt,\"%s.alternate\",v[0]); execl(alt,alt,(char*)0); }"
        "} return 0; }\n"
    )
    binary = tmp_path / "ghostty"
    subprocess.run([compiler, "-o", str(binary), str(source)], check=True)
    shutil.copy2(binary, binary.with_suffix(".alternate"))
    s = integrated
    cwd = tmp_path / "host-cwd"
    cwd.mkdir(mode=0o700)
    original_entry = s.entry

    def entry(*args, **kwargs):
        result = original_entry(*args, **kwargs)
        result["reopen"]["cwd"] = str(cwd)
        return result

    s.entry = entry
    s.identity["boot_id"] = restore_host.boot_id()
    for window in s.desktop.windows_by_id.values():
        window["pid"] = os.getpid()  # Known live protected processes; not owned.
    children = []

    def launch(attempt, ticket, **kwargs):
        spec = attempt.consume(ticket)
        with restore_host.Image(spec["argv"][0]) as image:
            image_pin = image.pin
        attempt.intent(
            "bootstrap",
            {
                "entry": ticket.index,
                "nonce": "a" * 64,
                "spec": {k: spec[k] for k in ("argv", "cwd")},
                "image": image_pin,
                "directory": {"device": cwd.stat().st_dev, "inode": cwd.stat().st_ino},
            },
        )
        child = subprocess.Popen(
            spec["argv"],
            cwd=spec["cwd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        children.append(child)
        process = restore_host.Process(child.pid)
        process.validate(image_pin)
        pin = process.pin
        s.desktop.add(child.pid)
        attempt.observed({"bootstrap": pin, "binding": "c" * 64})
        attempt.intent("exec", {"entry": ticket.index, "process": pin, "binding": "c" * 64})
        evidence = {
            "phase": "process-observed",
            "ownership": "process-only",
            "process": pin,
            "binding": "c" * 64,
            "window_ownership": "not-proved",
            "placement": "not-attempted",
            "native_session": "not-proved",
            "settlement": "unresolved",
        }
        proof = SimpleNamespace(
            process=process,
            receipt=attempt.store.put("receipts", evidence),
            validate=lambda **kw: process.validate(image_pin),
            close=process.close,
        )
        attempt.proofs.append(proof)
        attempt.observed(evidence)
        return proof

    monkeypatch.setattr(restore_execute, "launch", launch)
    try:
        value = fabricate_retained(s, monkeypatch)
        value.observe = observer(s)
        value.child = children[0]
        value.binary = binary
        value.cwd = cwd

        # From here onward feature code must never launch/kill/dispatch even in refusal paths.
        def forbidden(*args, **kwargs):
            pytest.fail("accounting disposition invoked an effect")

        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr(s.desktop, "action", forbidden)
        yield value
    finally:
        for child in children:
            child.stdin.close()  # Cooperative fixture exits on EOF, no kill or signal cleanup.
            assert child.wait(timeout=10) == 0


def test_real_default_process_evidence_approval_and_commit(real_retained):
    s = real_retained
    key = proposal(s)
    plan = s.store.get("plans", key)
    pin = next(p for p in plan["current"]["processes"] if p["pid"] == s.child.pid)
    assert pin == restore_host.process_pin(s.child.pid)
    assert plan["current"]["running_image"]["inode"] == s.binary.stat().st_ino
    result = disposition.apply(s.store, approval(s, key), observer=s.observe)
    assert result["status"] == "operator-accepted-partial" and result["effects"] == []
    assert s.child.poll() is None


@pytest.mark.parametrize(
    "change", ["exit", "replace-executable", "protected-unknown", "running-exec", "running-argv"]
)
def test_default_process_proof_refuses_real_identity_gaps(real_retained, change):
    s = real_retained
    key = proposal(s)
    if change == "exit":
        s.child.stdin.close()
        s.child.wait(timeout=10)
    elif change == "replace-executable":
        old = s.binary.with_suffix(".old")
        s.binary.rename(old)
        shutil.copyfile(old, s.binary)
        s.binary.chmod(0o700)
    elif change == "protected-unknown":
        s.desktop.windows_by_id[70]["pid"] = 2147483647
    else:
        s.child.stdin.write(b"x" if change == "running-exec" else b"a")
        s.child.stdin.flush()
        deadline = time.monotonic() + 3
        with restore_host.Process(s.child.pid) as process:
            expected = s.receipt["windows"][0]["entry"]["recipe"]["argv"]
            while time.monotonic() < deadline:
                try:
                    if process.argv() != expected:
                        break
                except ValueError:
                    pass  # The fixture may be between exec images; never used as positive proof.
                time.sleep(0.01)
            assert process.argv() != expected
    with pytest.raises((ValueError, OSError)):
        approval(s, key)
    fenced(s)
