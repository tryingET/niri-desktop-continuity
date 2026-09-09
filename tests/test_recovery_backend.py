"""Fabricated internal endpoint and fixture provisioner; never contacts native transports.

Copy this file beside owner-only settings.json, run only through the coordinator.
The native oracle is deliberately handwritten rather than importing protocol validators.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL = "desktop-continuity.recovery.v1"


def address(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def private_json(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def provision(
    root,
    interpreter=None,
    *,
    mode="normal",
    missing=False,
    unsafe=False,
    utility=None,
    utility_only=False,
    saved_refs=("c" * 64,),
):
    """One native process per saved_refs entry; duplicate refs share one native proof.

    References are opaque, already app-scoped identities supplied by the machine owner.
    This fixture neither discovers tools nor implements native identity namespacing.
    """
    from niri_desktop_continuity.model import digest, fingerprint, focus_pin, normalized_snapshot
    from niri_desktop_continuity.store import Store

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backend = root / "endpoint.py"
    backend.write_bytes(Path(__file__).read_bytes())
    backend.chmod(0o600)
    interpreter = str(Path(interpreter or sys.executable).resolve())
    for name in ("ledger", "runtime", "state"):
        (root / name).mkdir(mode=0o700)
    snapshot = normalized_snapshot(
        {
            "identity": {
                "boot_id": "fabricated",
                "niri_socket": "/fabricated",
                "socket_device": 1,
                "socket_inode": 1,
            },
            "coherent": True,
            "inventory_complete": True,
            "outputs": [
                {"name": "DISPLAY", "logical": {"width": 1200, "height": 800}, "current_mode": 0}
            ],
            "workspaces": [{"id": 1, "idx": 1, "output": "DISPLAY", "is_focused": True}],
            "windows": [
                {
                    "id": 1,
                    "pid": 101,
                    "app_id": "fabricated-terminal",
                    "workspace_id": 1,
                    "is_floating": False,
                    "is_focused": True,
                    "layout": {
                        "pos_in_scrolling_layout": [1, 1],
                        "tile_size": [800, 600],
                        "window_size": [800, 600],
                    },
                }
            ],
            "processes": [
                {
                    "pid": 101,
                    "ppid": 1,
                    "start_ticks": 42,
                    "exe_sha256": "a" * 64,
                    "exe_inode": 1,
                    "exe_device": 1,
                    "cgroup": "/fabricated.scope",
                }
            ],
            "process_inventory": [],
            "layers": [],
        }
    )
    source_key = Store(root / "state").save_snapshot(snapshot)
    private_json(root / "snapshot.json", snapshot)
    pin = {
        "boot_id": "fabricated",
        "pid": 102,
        "start_ticks": 43,
        "exe_sha256": "b" * 64,
        "exe_inode": 2,
        "exe_device": 1,
        "uid": os.getuid(),
    }
    processes = [
        {
            # Reserve 101 for the host, 103 for omission, and 104 for the utility.
            "pin": {
                **pin,
                "pid": 102 if index == 0 else 104 + index,
                "start_ticks": 43 if index == 0 else 45 + index,
            },
            "owned": True,
            "identity_proved": True,
            "protected_overlap": unsafe,
            "session_ref": session_ref,
        }
        for index, session_ref in enumerate(saved_refs)
    ]
    omitted = {**pin, "pid": 103, "start_ticks": 44}
    if missing:
        processes.append(
            {
                "pin": omitted,
                "owned": True,
                "identity_proved": True,
                "protected_overlap": unsafe,
                "session_ref": None,
            }
        )
    processes.sort(key=lambda item: digest(item["pin"]))
    observation = {
        "identity_digest": digest(snapshot["identity"]),
        "state_fingerprint": fingerprint(snapshot),
        "focus_digest": digest(focus_pin(snapshot)),
        "private_ref": "d" * 64,
        "supported": True,
        "processes": processes,
        "session_refs": sorted(set(saved_refs)),
        "legacy": {
            "locations_digest": digest([]),
            "complete": mode != "legacy-incomplete",
            "unresolved": 0,
        },
    }
    proof = {
        "dimensions": {
            name: {"status": "proved", "evidence_ref": "e" * 64}
            for name in (
                "causal_ownership",
                "new_images",
                "old_tree_exit",
                "service_contract",
                "layout",
                "focus",
                "recovery_labels",
                "temporary_holds",
                "protected_preservation",
            )
        },
        "native": [
            {
                "session_ref": session_ref,
                "evidence_ref": "f" * 64,
                "file": True,
                "cwd": mode != "wrong-cwd",
                "runtime": True,
                "bootstrap": True,
                "surface": True,
                "causal_window": True,
            }
            for session_ref in sorted(set(saved_refs))
        ],
        "interrupted": False,
        "unresolved_children": 0,
    }
    protocol = PROTOCOL
    if utility is not None:
        protocol = "desktop-continuity.recovery.v2"
        item, result = utility_fixture(pin, capability=utility == "capability-btop")
        observation["utilities"], proof["utilities"] = [item], [result]
        if utility_only:
            observation["processes"], observation["session_refs"], proof["native"] = [], [], []
    settings = {
        "mode": mode,
        "observation": observation,
        "proof": proof,
        "profile_path": str(root / "profile.json"),
        "interpreter": interpreter,
    }
    private_json(root / "settings.json", settings)

    def pinned(path):
        return {"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}

    profile = {
        "schema": protocol,
        "contract": "saved-conversations-v1",
        "reviewed": True,
        "interpreter": pinned(interpreter),
        "endpoint": pinned(backend),
        "sources": [pinned(root / "settings.json")],
        "ledger_root": str(root / "ledger"),
        "legacy_locations": [],
    }
    if utility is not None:
        platform = root / "platform.txt"
        platform.write_text("Fabricated owner-trusted application platform; no native code")
        platform.chmod(0o600)
        profile["platform"] = {
            "kind": "owner-trusted-application-platform",
            "pins": [pinned(platform)],
        }
    private_json(root / "profile.json", profile)
    private_json(
        root / "config.json",
        {
            "schema": protocol,
            "profile_digest": digest(profile),
            "interpreter": profile["interpreter"],
            "endpoint": profile["endpoint"],
        },
    )
    return {
        "root": root,
        "snapshot": snapshot,
        "snapshot_digest": source_key,
        "omission": digest(omitted),
        "profile": profile,
    }


def utility_fixture(pin, *, capability):
    """Handwritten image/utility proof oracle, independent of runtime validators."""
    host = {**pin, "pid": 101, "start_ticks": 42, "exe_sha256": "a" * 64, "exe_inode": 1}
    image = {**pin, "pid": 104, "start_ticks": 45}
    identity = {
        "kind": "capability-btop" if capability else "observed-image",
        "boot_id": "fabricated",
        "pid": 104,
        "start_ticks": 45,
        "uid": os.getuid(),
        "parent_pid": 101,
        "cgroup_digest": "1" * 64,
        "argv_digest": "2" * 64,
        "image_pin": None if capability else image,
        "installed_file_ref": "3" * 64,
        "capabilities_digest": "4" * 64 if capability else None,
        "running_image": "unobservable" if capability else "observed",
    }
    basis = {"kind": "btop", "host_pin": host, "identity": identity}
    ref = address(basis)
    return (
        {
            **basis,
            "utility_ref": ref,
            "owned": True,
            "identity_proved": True,
            "protected_overlap": False,
            "evidence_ref": "5" * 64,
        },
        {
            "utility_ref": ref,
            "evidence_ref": "6" * 64,
            "identity": True,
            "installed_file": True,
            "capabilities": True,
            "sole_owned_leaf": True,
            "causal_window": True,
            "running_image": "accepted-unobservable" if capability else "proved",
        },
    )


def installation_hook(root):
    # Test-only injection in the disposable installed interpreter, NOT a production CLI flag.
    return f"""
import json
from pathlib import Path
from niri_desktop_continuity import cli, operation_lock, recovery_profile
_root = Path({str(root)!r})
operation_lock.runtime_root = lambda: _root / "runtime"
recovery_profile.profile_path = lambda: _root / "profile.json"
cli.capture = lambda **kw: json.loads((_root / "snapshot.json").read_text())
"""


def backend_main():
    root = Path(__file__).resolve().parent
    settings = json.loads((root / "settings.json").read_text())
    mode = settings["mode"]
    channel = socket.socket(fileno=int(os.environ["NDC_RECOVERY_FD"]))
    os.set_inheritable(channel.fileno(), False)
    channel.settimeout(5)
    reader = channel.makefile("rb")
    request = json.loads(reader.readline(1024 * 1024 + 1))
    phase = request["phase"]
    profile = json.loads(Path(settings["profile_path"]).read_text())

    protocol = profile["schema"]

    def pinned():
        assert (
            address(json.loads(Path(settings["profile_path"]).read_text()))
            == request["profile_digest"]
        )
        for pin in [
            profile["interpreter"],
            profile["endpoint"],
            *profile["sources"],
            *profile.get("platform", {}).get("pins", []),
        ]:
            assert hashlib.sha256(Path(pin["path"]).read_bytes()).hexdigest() == pin["sha256"]
        assert (
            hashlib.sha256(Path("/proc/self/exe").read_bytes()).hexdigest()
            == profile["interpreter"]["sha256"]
        )

    pinned()
    last_reply = time.monotonic()
    assert request["protocol"] == protocol
    lock = request["lock_fd"]
    assert (lock is not None) == (phase == "execute")
    if lock is not None:
        os.set_inheritable(lock, False)
        payload = request["payload"]
        attempt = payload["attempt_digest"]
        assert address(payload["approval"]) == attempt
        assert payload["approval"]["schema"] == protocol
        expected_fields = {
            "schema",
            "plan_digest",
            "expires_at",
            "scope",
            "profile_digest",
            "accepted_omissions",
        }
        if protocol == "desktop-continuity.recovery.v2":
            expected_fields.add("accepted_utility_limits")
            assert payload["approval"]["accepted_utility_limits"] == [
                item["utility_ref"]
                for item in settings["observation"]["utilities"]
                if item["identity"]["kind"] == "capability-btop"
            ]
        assert set(payload["approval"]) == expected_fields
        ledger = Path(profile["ledger_root"])
        prepared = json.loads((ledger / "recovery-prepared" / (attempt + ".json")).read_text())
        ready = json.loads((ledger / "recovery-ready" / (attempt + ".json")).read_text())
        assert (
            ready == prepared["binding"] == json.loads(Path(prepared["cli_used_path"]).read_text())
        )
        assert ready["schema"] == protocol
        assert ready["approval_digest"] == attempt and ready["profile_digest"] == address(profile)
        assert ready["plan_digest"] == payload["plan_digest"]
        assert not (ledger / "recovery-terminal" / (attempt + ".json")).exists()
        # Independently one-use even if an internal execute frame were replayed directly.
        claims = ledger / "endpoint-started"
        claims.mkdir(mode=0o700, exist_ok=True)
        claim_fd = os.open(
            claims / (attempt + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(claim_fd, "w") as stream:
            json.dump(ready, stream)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(claims, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    with (root / "phases.jsonl").open("a") as stream:
        stream.write(json.dumps(phase) + "\n")

    def send(kind, body):
        value = {
            "protocol": protocol,
            "request_digest": address(request),
            "phase": phase,
            "type": kind,
            "body": body,
        }
        if mode == "wrong-phase":
            value["phase"] = "invented"
        if phase == "execute":
            if mode == "execute-wrong-request":
                value["request_digest"] = "0" * 64
            if mode == "execute-wrong-phase":
                value["phase"] = "observe"
            if kind == "result" and mode == "execute-final-invalid":
                value["body"] = {"ok": True, "private": "FABRICATED-SECRET"}
        raw = json.dumps(value).encode()
        if phase == "execute":
            if mode == "execute-utf16":
                raw = json.dumps(value).encode("utf-16")
            if mode == "execute-duplicate-key":
                raw = raw[:-1] + b', "phase": "execute"}'
            if mode == "execute-nonfinite":
                raw = raw[:-1] + b', "overflow": 1e309}'
            if kind == "result" and mode in ("execute-max-frame", "execute-over-frame"):
                raw += b" " * (1024 * 1024 - len(raw) + (mode == "execute-over-frame"))
            if kind == "result" and mode == "execute-trailing":
                raw += b"\n{}"
        channel.sendall(raw + b"\n")

    def exchange(kind, body):
        nonlocal last_reply
        send(kind, body)
        raw = reader.readline(1024 * 1024 + 1)
        if not raw:
            raise EOFError
        answer = json.loads(raw)
        assert (
            answer["protocol"] == protocol
            and answer["request_digest"] == address(request)
            and answer["phase"] == phase
        )
        if kind != "effect":
            assert answer["type"] == "continue" and answer["body"] == {}
        last_reply = time.monotonic()
        return answer

    def live():
        from datetime import datetime, timezone

        pinned()
        if time.monotonic() - last_reply >= request["liveness_seconds"]:
            (root / "worker-lease-expired").touch()
            raise EOFError
        assert datetime.now(timezone.utc) < datetime.fromisoformat(request["expires_at"])
        if select.select([channel], [], [], 0)[0] and not channel.recv(1, socket.MSG_PEEK):
            raise EOFError

    try:
        if mode == "malformed":
            channel.sendall(b"not-json\n")
        elif mode == "oversized":
            channel.sendall(b"x" * (1024 * 1024 + 2))
        elif phase in ("observe", "admit"):
            value = settings["observation"]
            if mode == "extra-field":
                value["environment"] = "FABRICATED-SECRET"
            if mode == "noisy":
                print("FABRICATED-SECRET", file=sys.stderr)
                print("FABRICATED-SECRET")
            send("result", value)
        elif phase == "inspect":
            send(
                "result",
                {
                    "legacy": settings["observation"]["legacy"],
                    "interrupted": mode == "die-after-intent",
                    "unresolved_children": 0,
                },
            )
        elif phase == "verify":
            send("result", settings["proof"])
        elif phase == "execute":
            if mode == "execute-stall":
                # Real protocol-lease elapsed time, not a mocked expiry/timeout-kill.
                time.sleep(request["liveness_seconds"] + 0.2)
                live()
            if mode == "execute-orphan-result":
                exchange(
                    "effect-result",
                    {
                        "sequence": 0,
                        "intent_ref": "1" * 64,
                        "outcome": "observed",
                        "evidence_ref": "e" * 64,
                    },
                )
            for index, kind in enumerate(("shutdown", "launch", "layout")):
                live()
                exchange("heartbeat", {})
                intent = {"sequence": index, "kind": kind, "intent_ref": str(index + 1) * 64}
                if mode == "execute-out-of-order":
                    intent["sequence"] = 1
                # Adapter-private fsynced journal precedes the CLI intent/permit.
                with (root / "worker-intents.jsonl").open("a") as stream:
                    stream.write(json.dumps(intent) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                answer = exchange("effect", intent)
                assert answer["type"] == "permit" and answer["body"] == {
                    **intent,
                    "expires_at": request["expires_at"],
                }
                if mode == "execute-duplicate-intent":
                    exchange("effect", intent)
                if mode == "execute-pending-heartbeat":
                    exchange("heartbeat", {})
                if mode == "execute-correlated-pending-heartbeat":
                    exchange("heartbeat", {"sequence": index, "intent_ref": intent["intent_ref"]})
                if mode == "execute-worker-lease":
                    # A permit is not evergreen, even if the coordinator has not closed IPC.
                    time.sleep(request["liveness_seconds"] + 0.2)
                live()
                if mode == "die-after-intent":
                    return 7
                if kind == "launch":
                    info = os.fstat(lock)
                    # Fabricated Python child only, proving the descriptor is not inherited.
                    code = """import os,sys
for name in os.listdir('/proc/self/fd'):
 try: s=os.fstat(int(name))
 except OSError: continue
 if (s.st_dev,s.st_ino)==(int(sys.argv[1]),int(sys.argv[2])): raise SystemExit(9)
"""
                    subprocess.run(
                        [
                            settings["interpreter"],
                            "-I",
                            "-S",
                            "-c",
                            code,
                            str(info.st_dev),
                            str(info.st_ino),
                        ],
                        check=True,
                        close_fds=True,
                    )
                with (root / "effects.jsonl").open("a") as stream:
                    stream.write(json.dumps(kind) + "\n")
                if mode == "execute-dispatched-heartbeat":
                    exchange("heartbeat", {})
                if mode == "pause-after-effect":
                    (root / "effect-waiting").touch()
                    while not (root / "effect-release").exists():
                        time.sleep(0.01)
                result = {
                    "sequence": index,
                    "intent_ref": intent["intent_ref"],
                    "outcome": "observed",
                    "evidence_ref": "e" * 64,
                }
                if mode == "execute-bad-result":
                    result["sequence"] = index + 1
                exchange("effect-result", result)
                if mode == "execute-duplicate-result":
                    exchange("effect-result", result)
            send("result", settings["proof"])
            if mode == "execute-nonzero-final":
                return 7
        else:
            raise AssertionError("invalid phase")
        return 0
    except (EOFError, BrokenPipeError, ConnectionResetError, socket.timeout):
        # No signal, service repair, retry, rollback or synthetic new effect on disconnect.
        (root / "cancelled").touch()
        return 8
    finally:
        reader.close()
        channel.close()


if __name__ == "__main__":
    raise SystemExit(backend_main())
