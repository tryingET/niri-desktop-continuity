"""Transport-only deadline oracles: in-memory peers, no executable or native process."""

import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from niri_desktop_continuity import recovery_adapter as transport
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_protocol import ADDITIVE, VERSION, VERSION2


def peer_fixture(monkeypatch, scenario, *, schema=VERSION, send_delay=False):
    received, errors, budgets = [], [], []
    pair = socket.socketpair

    class BoundedSend:
        def __init__(self, sock):
            self.sock, self.sends, self.budget = sock, 0, None

        def __getattr__(self, name):
            return getattr(self.sock, name)

        def settimeout(self, seconds):
            self.budget = seconds
            budgets.append(seconds)
            self.sock.settimeout(seconds)

        def sendall(self, raw):
            self.sends += 1
            if send_delay and self.sends == 2:
                # Model an OS send honoring the remaining timeout, not an evergreen lease.
                time.sleep(self.budget + 0.01)
                raise TimeoutError("fabricated blocked send")
            self.sock.sendall(raw)

    def sockets():
        parent, child = pair()
        return BoundedSend(parent), child

    class Process:
        def __init__(self, argv, **kwargs):
            assert kwargs["close_fds"] and kwargs["start_new_session"]
            assert argv == ["/fabricated/python", "-I", "-S", "/fabricated/endpoint"]
            child = socket.socket(fileno=os.dup(kwargs["pass_fds"][0]))
            child.settimeout(2)

            def run():
                try:
                    with child, child.makefile("rb") as reader:
                        request = json.loads(reader.readline())

                        def send(kind, body):
                            child.sendall(
                                json.dumps(
                                    {
                                        "protocol": schema,
                                        "request_digest": digest(request),
                                        "phase": "execute",
                                        "type": kind,
                                        "body": body,
                                    }
                                ).encode()
                                + b"\n"
                            )

                        def reply():
                            raw = reader.readline()
                            if raw:
                                answer = json.loads(raw)
                                received.append(answer)
                                return answer
                            return None

                        scenario(send, reply)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except BaseException as error:
                    errors.append(error)

            self.thread = threading.Thread(target=run)
            self.thread.start()

        def wait(self):
            self.thread.join(3)
            assert not self.thread.is_alive()
            return 0

    profile = {
        "schema": schema,
        "interpreter": {"path": "/fabricated/python"},
        "endpoint": {"path": "/fabricated/endpoint"},
    }
    monkeypatch.setattr(transport.socket, "socketpair", sockets)
    monkeypatch.setattr(transport.subprocess, "Popen", Process)
    monkeypatch.setattr(transport, "load_profile", lambda **_: profile)
    # Request parsing is independently tested; this fixture isolates transport deadlines.
    monkeypatch.setattr(transport, "request_payload", lambda *a, **kw: None)
    return transport.Adapter(profile), received, errors, budgets


def expiry(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def test_slow_journal_cannot_issue_a_late_permit(monkeypatch):
    def scenario(send, reply):
        send("effect", {"sequence": 0, "kind": "launch", "intent_ref": "a" * 64})
        assert reply() is None

    adapter, received, errors, _ = peer_fixture(monkeypatch, scenario)
    monkeypatch.setattr(transport, "LIVENESS_SECONDS", 0.1)
    with pytest.raises(ValueError):
        adapter.call(
            "execute", {}, lock_fd=99, expires_at=expiry(5), journal=lambda *args: time.sleep(0.15)
        )
    assert received == [] and errors == []


def test_reply_send_uses_remaining_lease_and_never_renews_after_timeout(monkeypatch):
    def scenario(send, reply):
        send("effect", {"sequence": 0, "kind": "launch", "intent_ref": "a" * 64})
        assert reply() is None

    adapter, received, errors, budgets = peer_fixture(monkeypatch, scenario, send_delay=True)
    monkeypatch.setattr(transport, "LIVENESS_SECONDS", 0.3)
    with pytest.raises(ValueError):
        adapter.call(
            "execute", {}, lock_fd=99, expires_at=expiry(5), journal=lambda *args: time.sleep(0.1)
        )
    assert 0 < budgets[-1] < 0.25
    assert received == [] and errors == []


@pytest.mark.parametrize("schema", [VERSION, VERSION2])
def test_frozen_replacement_final_observation_may_finish_after_effect_expiry(monkeypatch, schema):
    final = {"fabricated-final-observation": True}

    def scenario(send, reply):
        intent = {"sequence": 0, "kind": "launch", "intent_ref": "a" * 64}
        send("effect", intent)
        assert reply()["type"] == "permit"
        send(
            "effect-result",
            {
                "sequence": 0,
                "intent_ref": "a" * 64,
                "outcome": "observed",
                "evidence_ref": "b" * 64,
            },
        )
        assert reply()["type"] == "continue"
        time.sleep(0.3)
        send("result", final)

    adapter, received, errors, _ = peer_fixture(monkeypatch, scenario, schema=schema)
    assert (
        adapter.call("execute", {}, lock_fd=99, expires_at=expiry(0.2), journal=lambda *args: None)
        == final
    )
    assert [row["type"] for row in received] == ["permit", "continue"]
    assert errors == []


def test_additive_final_result_does_not_cross_its_explicit_expiry_gate(monkeypatch):
    def scenario(send, reply):
        time.sleep(0.3)
        send("result", {"fabricated-final": True})

    adapter, received, errors, _ = peer_fixture(monkeypatch, scenario, schema=ADDITIVE)
    with pytest.raises(ValueError):
        adapter.call(
            "execute",
            {"admitted": {"saved_selection": {"missing_refs": []}}},
            lock_fd=99,
            expires_at=expiry(0.2),
            journal=lambda *args: None,
        )
    assert received == [] and errors == []
