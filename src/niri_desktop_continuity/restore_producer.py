"""Launch-bound process producer shared by standalone probes and ordinary restore."""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

from . import restore_host as host
from . import restore_wire as wire
from .restore_attempt import Attempt
from .restore_bootstrap import binding, directory_pin
from .restore_history import fence_path  # noqa: F401 - lower-level inspection API


class LaunchProof:
    """Held process evidence only. Closing proof never terminates the application."""

    def __init__(self, process, image, spec, env, identity, receipt, directory, cwd_fd):
        self.process, self.image, self.spec = process, image, spec
        self.environment, self.identity, self.receipt = env, identity, receipt
        self.directory, self.cwd_fd = dict(directory), cwd_fd
        self.invalid = False

    def validate(self, *, deadline=None):
        if self.invalid:
            raise ValueError("launch proof has been invalidated")

        def check():
            if deadline is not None:
                wire.remaining(deadline)

        try:
            check()
            host.route(self.identity)
            check()
            self.validate_cwd(deadline)
            check()
            self.process.validate(self.image, deadline=deadline)
            check()
            if self.process.argv() != self.spec["argv"]:
                raise ValueError("running argv changed")
            check()
            # Compare raw /proc initial environment, never a sanitized projection of it.
            if self.process.environment() != self.environment:
                raise ValueError("initial process environment changed")
            check()
            self.process.validate(self.image, deadline=deadline)
            check()
            self.validate_cwd(deadline)
            check()
        except BaseException:
            self.invalid = True
            raise

    def validate_cwd(self, deadline):
        def check():
            if deadline is not None:
                wire.remaining(deadline)
            self.process.live()
            if deadline is not None:
                wire.remaining(deadline)

        check()
        if directory_pin(self.cwd_fd) != self.directory:
            raise ValueError("held working directory changed")
        check()
        if directory_pin_for_path(self.spec["cwd"]) != self.directory:
            raise ValueError("working directory pathname changed")
        check()
        fd = os.open(
            f"/proc/{self.process.pin['pid']}/cwd", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )  # Follow only the pinned host's proc cwd, never a utility child.
        try:
            if directory_pin(fd) != self.directory:
                raise ValueError("host cwd differs from admitted directory")
        finally:
            os.close(fd)
        check()

    def close(self):
        self.invalid = True
        try:
            self.process.close()
        finally:
            if self.cwd_fd is not None:
                fd, self.cwd_fd = self.cwd_fd, None
                os.close(fd)  # never retry an ambiguous descriptor close

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def niri_spawn(argv, identity, deadline):
    host.route(identity)
    wire.remaining(deadline)
    command = ["niri", "msg", "action", "spawn", "--", *argv]
    # Only the IPC client is a service child. Niri itself launches the bootstrap/host.
    # Unlike subprocess.run(timeout=...), wait never kills on deadline or ambiguity.
    client = subprocess.Popen(
        command,
        env={**os.environ, "NIRI_SOCKET": identity["niri_socket"]},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    status = client.wait(timeout=min(10, wire.remaining(deadline)))
    if status:
        raise subprocess.CalledProcessError(status, command)
    host.route(identity)


def produce(store, snapshot_key, recipe, identity, *, timeout=25.0, dispatch=None) -> LaunchProof:
    """Standalone process-only probe; uses the same attempt/ticket path and stays unresolved."""
    deadline = time.monotonic() + timeout
    spec = host.admit(recipe)
    with host.Image(spec["argv"][0], deadline=deadline):
        pass  # read-only preflight; no history or effect admission on invalid images
    with ExitStack() as orphan:
        with Attempt(store, snapshot_key, identity) as attempt:
            attempt.prepare({"mode": "process-probe", "entries": [{"recipe": {**recipe, **spec}}]})
            proof = launch(
                attempt, attempt.ticket(0), timeout=wire.remaining(deadline), dispatch=dispatch
            )
            orphan.callback(proof.close)
            attempt.proofs.remove(proof)
        # Caller ownership starts only AFTER successful attempt exit. BaseException on
        # exit closes the detached proof; a close failure remains chained to that error.
        orphan.pop_all()
        return proof


def launch(attempt, ticket, *, timeout=25.0, dispatch=None) -> LaunchProof:
    """Consume one bound ticket without reacquiring flock; retain proof in its attempt owner."""
    if type(attempt) is not Attempt:
        raise ValueError("explicit restore attempt required")
    recipe = attempt.consume(ticket)
    deadline = time.monotonic() + timeout
    wire.remaining(deadline)
    spec = host.admit(recipe)
    identity = attempt.identity
    nonce, endpoint = secrets.token_hex(32), "ndc-" + secrets.token_hex(24)
    process = None
    with ExitStack() as stack:
        host.route(identity)
        image = stack.enter_context(host.Image(spec["argv"][0], deadline=deadline))
        python = stack.enter_context(
            host.Image(str(Path(sys.executable).resolve()), deadline=deadline)
        )
        cwd = os.open(spec["cwd"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        cwd_owner = stack.enter_context(ExitStack())
        cwd_owner.callback(os.close, cwd)
        directory = directory_pin(cwd)
        listener = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
        listener.bind("\0" + endpoint)
        listener.listen(1)
        parent = host.process_pin(os.getpid())
        argv = [
            sys.executable,
            "-I",
            "-m",
            "niri_desktop_continuity.restore_bootstrap",
            endpoint,
            nonce,
            repr(deadline),
            str(parent["pid"]),
            str(parent["start_ticks"]),
            parent["boot_id"],
        ]
        attempt.intent(
            "bootstrap",
            {
                "entry": ticket.index,
                "nonce": nonce,
                "spec": spec,
                "image": image.pin,
                "directory": directory,
            },
        )
        try:
            (dispatch or niri_spawn)(argv, identity, deadline)
            listener.settimeout(wire.remaining(deadline))
            connection, _ = listener.accept()
            stack.enter_context(connection)
            listener.close()  # One connection, no replacement bootstrap or second permit.
            process = host.Process(wire.peer_pid(connection))

            def check():
                process.validate(python.pin, deadline=deadline)

            check()
            hello = wire.receive(connection, deadline, check)
            if hello != {"type": "hello", "nonce": nonce}:
                raise ValueError("bootstrap attempt mismatch")
            wire.send(
                connection,
                {
                    "type": "prepare",
                    "nonce": nonce,
                    "spec": spec,
                    "identity": identity,
                    "image": image.pin,
                    "directory": directory,
                },
                deadline,
                check,
            )
            ready = wire.receive(connection, deadline, check)
            env = host.environment(process.environment())
            bound = binding(nonce, spec, identity, image.pin, directory, process.pin, env)
            if ready != {"type": "ready", "nonce": nonce, "binding": bound}:
                raise ValueError("bootstrap binding mismatch")
            host.route(identity)
            image.validate()
            if directory_pin(cwd) != directory or directory_pin_for_path(spec["cwd"]) != directory:
                raise ValueError("working directory changed")
            check()
            attempt.observed({"bootstrap": process.pin, "binding": bound})
            attempt.intent(
                "exec", {"entry": ticket.index, "process": process.pin, "binding": bound}
            )
            attempt.check()  # both original receipt and canonical intent precede permit bytes
            wire.send(
                connection,
                {"type": "exec", "nonce": nonce, "binding": bound},
                deadline,
                process.live,
            )
            connection.close()
            while True:
                wire.remaining(deadline)
                process.live()
                with host.Image(
                    f"/proc/{process.pin['pid']}/exe", proc=True, deadline=deadline
                ) as running:
                    current_image = running.pin
                process.live()
                if current_image == image.pin:
                    # Linux may expose an empty cmdline during the admitted exec transition.
                    # Poll observation only; this never authorizes another dispatch or permit.
                    raw_argv = process.read("cmdline")
                    if not raw_argv:
                        time.sleep(min(0.01, wire.remaining(deadline)))
                        continue
                    if raw_argv != b"".join(os.fsencode(a) + b"\0" for a in spec["argv"]):
                        raise ValueError("unexpected argv after admitted exec")
                    proof = LaunchProof(
                        process, image.pin, spec, env, identity, None, directory, cwd
                    )
                    proof.validate(deadline=deadline)
                    evidence = {
                        "phase": "process-observed",
                        "ownership": "process-only",
                        "process": process.pin,
                        "binding": bound,
                        "window_ownership": "not-proved",
                        "placement": "not-attempted",
                        "native_session": "not-proved",
                        "settlement": "unresolved",
                    }
                    proof.receipt = attempt.store.put("receipts", evidence)
                    attempt.observed(evidence)
                    attempt.proofs.append(proof)
                    cwd_owner.pop_all()  # proof now exclusively owns the retained CLOEXEC fd
                    return proof
                if current_image != python.pin:
                    raise ValueError("unexpected running executable after permit")
                time.sleep(min(0.01, wire.remaining(deadline)))
        except BaseException:
            if process is not None:
                process.close()
            # Even EOF or a fully exited helper is not an automatic no-effect settlement.
            attempt.poisoned = True
            raise


def directory_pin_for_path(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return directory_pin(fd)
    finally:
        os.close(fd)
