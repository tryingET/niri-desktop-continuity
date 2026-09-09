"""Fabricated additive endpoint; no compositor/native calls and no production validators."""

import hashlib
import json
import os
import socket
import time
from pathlib import Path

SCHEMA = "desktop-continuity.saved-reopen.v1"
SAVED_SET = "9" * 64
REF = "c" * 64


def address(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def provision(root, *, present=False, mode="normal"):
    from test_recovery_backend import private_json
    from test_recovery_backend import provision as base

    data = base(root, mode=mode)
    settings = json.loads((root / "settings.json").read_text())
    observed = settings["observation"]
    observed.update(
        processes=[],
        saved_set=SAVED_SET,
        selection_proved=True,
        saved_selection={
            "missing_refs": [] if present else [REF],
            "present_refs": [REF] if present else [],
            "unresolved_refs": [],
        },
    )
    settings["proof"]["dimensions"] = {
        key: {"status": "proved", "evidence_ref": "e" * 64}
        for key in ("causal_ownership", "new_images", "focus", "protected_preservation")
    }
    settings["mode"] = mode
    private_json(root / "settings.json", settings)
    (root / "endpoint.py").write_bytes(Path(__file__).read_bytes())
    platform = root / "platform.txt"
    platform.write_text("fabricated owner platform")
    platform.chmod(0o600)
    profile = data["profile"]
    profile["schema"] = SCHEMA
    profile["platform"] = {"kind": "owner-trusted-application-platform", "pins": [pin(platform)]}
    profile["endpoint"] = pin(root / "endpoint.py")
    profile["sources"] = [pin(root / "settings.json")]
    private_json(root / "profile.json", profile)
    private_json(
        root / "config.json",
        {
            "schema": SCHEMA,
            "profile_digest": address(profile),
            "interpreter": profile["interpreter"],
            "endpoint": profile["endpoint"],
        },
    )
    return data


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def backend_main():
    root = Path(__file__).resolve().parent
    settings = json.loads((root / "settings.json").read_text())
    profile = json.loads((root / "profile.json").read_text())
    mode = settings["mode"]
    channel = socket.socket(fileno=int(os.environ["NDC_RECOVERY_FD"]))
    channel.settimeout(5)
    os.set_inheritable(channel.fileno(), False)
    reader = channel.makefile("rb")
    request = json.loads(reader.readline(1024 * 1024 + 1))
    phase = request["phase"]
    assert request["protocol"] == SCHEMA and request["profile_digest"] == address(profile)
    for item in [
        profile["interpreter"],
        profile["endpoint"],
        *profile["sources"],
        *profile["platform"]["pins"],
    ]:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    with (root / "phases.jsonl").open("a") as stream:
        stream.write(json.dumps(phase) + "\n")

    def send(kind, body):
        channel.sendall(
            json.dumps(
                {
                    "protocol": SCHEMA,
                    "request_digest": address(request),
                    "phase": phase,
                    "type": kind,
                    "body": body,
                }
            ).encode()
            + b"\n"
        )

    def exchange(kind, body):
        send(kind, body)
        raw = reader.readline(1024 * 1024 + 1)
        if not raw:
            raise EOFError
        reply = json.loads(raw)
        assert reply["request_digest"] == address(request) and reply["phase"] == phase
        return reply

    try:
        if phase in ("verify", "inspect"):
            for name in ("grouping", "diagnostics"):
                assert request["payload"]["admitted"].get(name) == settings["observation"].get(name)
        if phase in ("observe", "admit"):
            payload = request["payload"]
            assert payload["mode"] == "additive" and payload["saved_set"] == SAVED_SET
            assert all(not value for value in payload["selection"].values())
            assert payload["omission_pins"] == []
            for name in ("grouping", "diagnostics"):
                if phase == "observe":
                    assert name not in payload
                else:
                    assert payload.get(name) == settings["observation"].get(name)
            send("result", settings["observation"])
        elif phase == "inspect":
            send(
                "result",
                {
                    "legacy": settings["observation"]["legacy"],
                    "interrupted": False,
                    "unresolved_children": 0,
                },
            )
        elif phase == "verify":
            send("result", settings["proof"])
        elif phase == "execute":
            payload = request["payload"]
            assert payload["approval"]["mode"] == "additive"
            assert payload["approval"]["saved_set"] == SAVED_SET
            assert address(payload["approval"]) == payload["attempt_digest"]
            for name in ("grouping", "diagnostics"):
                assert payload["admitted"].get(name) == settings["observation"].get(name)
            ledger = Path(profile["ledger_root"])
            attempt = payload["attempt_digest"]
            prepared = json.loads((ledger / "recovery-prepared" / (attempt + ".json")).read_text())
            ready = json.loads((ledger / "recovery-ready" / (attempt + ".json")).read_text())
            assert (
                ready
                == prepared["binding"]
                == json.loads(Path(prepared["cli_used_path"]).read_text())
            )
            assert request["lock_fd"] is not None
            os.set_inheritable(request["lock_fd"], False)
            with (root / "endpoint-consumed").open("x") as stream:
                stream.write(attempt)
            missing = payload["admitted"]["saved_selection"]["missing_refs"]
            effects = [("launch", ref) for ref in missing]
            if missing:
                effects.append(("focus", payload["admitted"]["focus_digest"]))
            if mode in ("shutdown", "service", "layout"):
                effects = [(mode, REF)]
            elif mode == "duplicate":
                effects.insert(1, ("launch", REF))
            elif mode == "wrong-ref":
                effects[0] = ("launch", "0" * 64)
            elif mode == "early-focus":
                effects.reverse()
            elif mode == "wrong-focus":
                effects[-1] = ("focus", "0" * 64)
            elif mode == "no-op-launch":
                effects = [("launch", REF)]
            elif mode == "omitted-launch":
                effects = []
            for index, (kind, target) in enumerate(effects):
                from datetime import datetime, timezone

                assert datetime.now(timezone.utc) < datetime.fromisoformat(request["expires_at"])
                intent = {
                    "sequence": index,
                    "kind": kind,
                    "intent_ref": str(index + 1) * 64,
                    "target_ref": target,
                }
                reply = exchange("effect", intent)
                assert reply["type"] == "permit" and reply["body"] == {
                    **intent,
                    "expires_at": request["expires_at"],
                }
                if mode == "disconnect":
                    return 7
                if mode.startswith("pending-") and index == 0:
                    beat = {"sequence": index, "intent_ref": intent["intent_ref"]}
                    if mode == "pending-empty":
                        beat = {}
                    elif mode == "pending-wrong-sequence":
                        beat["sequence"] = 1
                    elif mode == "pending-bool-sequence":
                        beat["sequence"] = False
                    elif mode == "pending-wrong-intent":
                        beat["intent_ref"] = "0" * 64
                    elif mode == "pending-extra":
                        beat["target_ref"] = target
                    if mode == "pending-stall":
                        time.sleep(5.2)
                    repetitions = 7 if mode == "pending-long" else 1
                    if mode == "pending-expiry":
                        repetitions = 40
                    for _ in range(repetitions):
                        if mode in {"pending-long", "pending-expiry"}:
                            time.sleep(0.8)
                        answer = exchange("heartbeat", beat)
                        assert answer["type"] == "continue" and answer["body"] == beat
                    if mode == "pending-second-effect":
                        exchange("effect", {**intent, "sequence": 1})
                    if mode == "pending-disconnect":
                        return 7
                    assert datetime.now(timezone.utc) < datetime.fromisoformat(
                        request["expires_at"]
                    )
                with (root / "effects.jsonl").open("a") as stream:
                    stream.write(json.dumps({"kind": kind, "target_ref": target}) + "\n")
                reply = exchange(
                    "effect-result",
                    {
                        "sequence": index,
                        "intent_ref": intent["intent_ref"],
                        "outcome": "observed",
                        "evidence_ref": "e" * 64,
                    },
                )
                assert reply["type"] == "continue"
            send("result", settings["proof"])
        else:
            raise AssertionError("unknown phase")
        return 0
    except (EOFError, BrokenPipeError, ConnectionResetError, socket.timeout):
        (root / "cancelled").touch()
        return 8
    finally:
        reader.close()
        channel.close()


if __name__ == "__main__":
    raise SystemExit(backend_main())
