"""Offline retained-width fixture; expected chain/outcomes are handwritten, not validator output."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import cli, operation_lock, restore
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_disposition_evidence as evidence
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity import restore_state as states
from niri_desktop_continuity.model import digest


@pytest.fixture
def retained(integrated, monkeypatch):
    return fabricate_retained(integrated, monkeypatch)


def fabricate_retained(s, monkeypatch):
    action = s.desktop.action

    def fail_width(*argv):
        if argv[0] == "set-column-width":
            raise subprocess.CalledProcessError(2, ["niri", "msg", "action", *argv])
        action(*argv)

    monkeypatch.setattr(s.desktop, "action", fail_width)
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted"
    directory = history.fence_path(s.identity)
    paths = sorted(directory.glob("*.json"))
    assert [history.read(p)["type"] for p in paths] == [
        "prepared",
        "intent",
        "observed",
        "intent",
        "observed",
        "association",
        "intent",
        "observed",
        "intent",
    ]
    last = history.read(paths[-1])
    payload = s.store.get("receipts", last["receipt"])
    assert payload["details"]["argv"] == ["set-column-width", "888"]
    payload["details"]["argv"] = ["set-column-width", "888.0"]
    last["receipt"] = s.store.put("receipts", payload)
    paths[-1].write_text(json.dumps(last) + "\n")
    receipt = {k: v for k, v in result.items() if k not in {"snapshot_digest", "receipt_digest"}}
    receipt["error"] = str(
        subprocess.CalledProcessError(2, ["niri", "msg", "action", "set-column-width", "888.0"])
    )
    receipt_key = s.store.put("receipts", receipt)
    result = {"snapshot_digest": key, "receipt_digest": receipt_key, **receipt}
    result_path, exit_path = s.store.root / "client-result.json", s.store.root / "client-exit.txt"
    result_path.write_text(json.dumps(result) + "\n")
    exit_path.write_text("2\n")
    result_path.chmod(0o600)
    exit_path.chmod(0o600)
    # Legitimate later activity is not evidence of historical restore preservation.
    s.desktop.widths[70] = s.desktop.widths[71] = 680.0
    s.desktop.focus = s.desktop.active[1] = 80
    return SimpleNamespace(
        **vars(s),
        key=key,
        interrupted=receipt_key,
        result_path=result_path,
        exit_path=exit_path,
        attempt=last["attempt"],
        original={p: p.read_bytes() for p in paths},
        receipt=receipt,
    )


def test_cli_exposes_explicit_separate_lifecycle():
    args = cli.parser().parse_args(
        [
            "restore-disposition",
            "approve",
            "a" * 64,
            "--confirm",
            "a" * 64,
            "--accept",
            "operator-accepted-partial",
            "--attest-client-returned",
        ]
    )
    assert args.command == "restore-disposition"


def test_retained_invalid_width_is_readable_data_but_never_action_authority(retained):
    s = retained
    with operation_lock.operation_lock(s.identity, effectful=False):
        completed, active, count, tail = history.load(s.identity)
        assert not completed and count == 9 and tail == digest(history.read(list(s.original)[-1]))
        assert active["attempt"] == s.attempt
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pytest.fail("pending decimal intent cannot grant effects")
    assert s.store.pointer("last-reopened") is None
    with pytest.raises(ValueError, match="unresolved restore"):
        restore.restore(s.store, s.key, s.desktop, apply=True)
    assert {p: p.read_bytes() for p in s.original} == s.original


def observer(s):
    def read():
        return {
            "identity": s.identity,
            "coherent": True,
            "state": states.record(
                (
                    {w["id"]: w for w in s.desktop.windows()},
                    s.desktop.workspaces(),
                    states.output_scales(s.desktop.outputs(), s.desktop.workspaces()),
                )
            ),
        }

    return read


@pytest.fixture
def ready(retained, monkeypatch):
    s = retained

    class Process:
        def __init__(self, pid):
            self.pin = {"boot_id": s.identity["boot_id"], "pid": pid, "start_ticks": 1}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def live(self):
            pass

        def validate(self, expected):
            assert expected == {"device": 1, "inode": 2, "sha256": "b" * 64}

        def argv(self):
            return s.receipt["windows"][0]["entry"]["recipe"]["argv"]

    class Image:
        pin = {"device": 1, "inode": 2, "sha256": "b" * 64}

        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Directory:
        def __init__(self, path, pin, process):
            self.value = {"path": path, "directory": pin, "process_directory": pin}

        def validate(self):
            return self.value

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(evidence, "Directory", Directory)
    monkeypatch.setattr(host, "Process", Process)
    monkeypatch.setattr(host, "Image", Image)
    monkeypatch.setattr(evidence, "controller_pids", lambda: {999999})
    s.observe = observer(s)
    s.calls = tuple(s.desktop.actions)

    def forbidden(*args, **kwargs):
        pytest.fail("disposition must never dispatch, launch or terminate")

    monkeypatch.setattr(s.desktop, "action", forbidden)
    monkeypatch.setattr(restore.LiveDesktop, "action", forbidden)
    monkeypatch.setattr(restore.LiveDesktop, "spawn", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return s


def proposal(s):
    return disposition.propose(
        s.store,
        s.identity,
        s.attempt,
        s.interrupted,
        s.result_path,
        s.exit_path,
        observer=s.observe,
    )["plan_digest"]


def approval(s, plan):
    return disposition.approve(
        s.store,
        plan,
        confirmation=plan,
        acceptance="operator-accepted-partial",
        attest_client_returned=True,
        observer=s.observe,
    )["approval_digest"]


def fenced(s):
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pytest.fail("damaged/uncommitted evidence released a writer")


def test_exact_flow_retains_bytes_releases_new_source_but_never_retries_original(ready):
    s = ready
    before = set(s.store.root.rglob("*"))
    info = disposition.inspect(
        s.store, s.identity, s.attempt, s.interrupted, s.result_path, s.exit_path
    )
    assert info["approval"] == "not-granted" and info["desktop_effects"] == []
    assert set(s.store.root.rglob("*")) == before
    key = proposal(s)
    assert not list((s.store.root / "approvals").iterdir())
    fenced(s)
    plan = s.store.get("plans", key)
    assert plan["current"]["state"]["windows"][0]["layout"]["tile_size"][0] == 680.0
    assert plan["limits"]["historical_preservation"] == "unproved"
    approved = approval(s, key)
    fenced(s)
    result = disposition.apply(s.store, approved, observer=s.observe)
    assert result["status"] == "operator-accepted-partial"
    assert result["disposition_effects"] == result["effects"] == []
    assert result["pending_outcome"] == "unresolved" and result["retry_authorized"] is False
    assert s.store.pointer("last-reopened") is None
    assert {p: p.read_bytes() for p in s.original} == s.original
    records = sorted(history.fence_path(s.identity).glob("*.json"))
    assert len(records) == 10
    final = history.read(records[-1])
    assert final == {
        "schema": "desktop-continuity.restore-history.v3",
        "seq": 9,
        "previous": plan["history_tail"],
        "type": "operator-disposition",
        "attempt": s.attempt,
        "receipt": result["receipt_digest"],
        "origin": plan["origin"],
    }
    with operation_lock.operation_lock(s.identity):
        pass
    replay = restore.restore(
        s.store,
        s.key,
        s.desktop,
        apply=True,
        observe=lambda: pytest.fail("replay cannot observe fresh state"),
    )
    assert replay["status"] == "operator-accepted-partial" and replay["effects"] == []
    assert replay["historical_effects"] == [["move-column-to-index", "3"]]
    assert not replay["fresh_native_verification"]
    repeated = disposition.apply(
        s.store, approved, observer=lambda: pytest.fail("committed replay is historical")
    )
    assert repeated["historical"] and repeated["receipt_digest"] == result["receipt_digest"]
    assert tuple(s.desktop.actions) == s.calls
    from test_reopen import saved

    from niri_desktop_continuity.restore_attempt import Attempt

    new_key = s.store.put("snapshots", saved([]))
    with Attempt(s.store, new_key, s.identity) as attempt:
        assert attempt.historical is None  # Admission only, no new launch or old approval grant.


@pytest.mark.parametrize(
    "change",
    [
        "missing-result",
        "missing-exit",
        "exit",
        "timeout",
        "other-command",
        "wrong-source",
        "wrong-receipt",
        "extra-body",
        "unsafe-mode",
        "other-root",
    ],
)
def test_untrusted_or_unrelated_invocation_never_supplies_exit_proof(ready, change, tmp_path):
    s = ready
    if change == "missing-result":
        s.result_path.unlink()
    elif change == "missing-exit":
        s.exit_path.unlink()
    elif change == "exit":
        s.exit_path.write_text("0\n")
    elif change == "unsafe-mode":
        s.result_path.chmod(0o644)
    elif change == "other-root":
        other = tmp_path / "result.json"
        other.write_bytes(s.result_path.read_bytes())
        other.chmod(0o600)
        s.result_path = other
    else:
        body = json.loads(s.result_path.read_text())
        if change == "wrong-source":
            body["snapshot_digest"] = "0" * 64
        elif change == "wrong-receipt":
            body["receipt_digest"] = "0" * 64
        elif change == "extra-body":
            body["invented_execution_fact"] = True
        else:
            receipt = dict(s.receipt)
            if change == "timeout":
                receipt["error_type"] = "TimeoutExpired"
            else:
                receipt["error"] = str(
                    subprocess.CalledProcessError(2, ["niri", "msg", "action", "other"])
                )
            s.interrupted = s.store.put("receipts", receipt)
            body = {"snapshot_digest": s.key, "receipt_digest": s.interrupted, **receipt}
        s.result_path.write_text(json.dumps(body))
    with pytest.raises((ValueError, OSError)):
        proposal(s)
    fenced(s)
    assert not list((s.store.root / "approvals").iterdir())


@pytest.mark.parametrize("stage", ["approve", "apply"])
@pytest.mark.parametrize(
    "change",
    [
        "raw",
        "inode",
        "extra-record",
        "focus",
        "geometry",
        "identity",
        "expired",
        "argv",
        "image",
        "pid-reuse",
        "surplus",
        "controller",
        "unknown-pid",
    ],
)
def test_fresh_revalidation_refuses_drift(ready, monkeypatch, stage, change):
    s = ready
    key = proposal(s)
    approved = approval(s, key) if stage == "apply" else None
    if change == "raw":
        s.result_path.write_bytes(s.result_path.read_bytes() + b" ")
    elif change == "inode":
        data = s.exit_path.read_bytes()
        s.exit_path.rename(s.exit_path.with_suffix(".old"))
        s.exit_path.write_bytes(data)
        s.exit_path.chmod(0o600)
    elif change == "extra-record":
        (history.fence_path(s.identity) / "extra").write_text("{}")
    elif change == "focus":
        s.desktop.focus = s.desktop.active[1] = 70
    elif change == "geometry":
        s.desktop.widths[80] += 1
    elif change == "identity":
        base = s.observe
        s.observe = lambda: {**base(), "identity": {**s.identity, "socket_inode": 777}}
    elif change == "expired":
        monkeypatch.setattr(disposition.time, "time", lambda: s.store.get("plans", key)["expires"])
    elif change == "argv":
        monkeypatch.setattr(host.Process, "argv", lambda self: ["not-launched"])
    elif change == "image":
        monkeypatch.setattr(host.Image, "pin", {"device": 1, "inode": 99, "sha256": "b" * 64})
    elif change == "pid-reuse":
        original = host.Process.__init__

        def reused(self, pid):
            original(self, pid)
            self.pin["start_ticks"] += 1

        monkeypatch.setattr(host.Process, "__init__", reused)
    elif change == "surplus":
        s.desktop.windows_by_id[70]["pid"] = 2000
    elif change == "controller":
        monkeypatch.setattr(evidence, "controller_pids", lambda: {2000})
    else:
        s.desktop.windows_by_id[70]["pid"] = None
    with pytest.raises((ValueError, OSError)):
        if stage == "approve":
            approval(s, key)
        else:
            disposition.apply(s.store, approved, observer=s.observe)
    fenced(s)
    assert s.store.pointer("last-reopened") is None


@pytest.mark.parametrize(
    "field,value",
    [("confirmation", "0" * 64), ("acceptance", "partial"), ("attest_client_returned", False)],
)
def test_approval_requires_all_explicit_decisions(ready, field, value):
    s = ready
    key = proposal(s)
    args = {
        "confirmation": key,
        "acceptance": "operator-accepted-partial",
        "attest_client_returned": True,
    }
    args[field] = value
    with pytest.raises(ValueError):
        disposition.approve(s.store, key, observer=s.observe, **args)
    assert not list((s.store.root / "approvals").iterdir())
    fenced(s)


def test_every_stage_respects_held_flock(ready):
    s = ready
    key, approved = proposal(s), None
    approved = approval(s, key)
    with operation_lock.operation_lock(s.identity, effectful=False):
        for call in (
            lambda: proposal(s),
            lambda: approval(s, key),
            lambda: disposition.apply(s.store, approved, observer=s.observe),
            lambda: disposition.inspect(
                s.store, s.identity, s.attempt, s.interrupted, s.result_path, s.exit_path
            ),
        ):
            with pytest.raises(ValueError, match="another continuity writer"):
                call()
