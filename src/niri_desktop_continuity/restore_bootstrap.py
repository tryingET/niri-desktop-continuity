"""Short-lived installed Niri bootstrap. No host executes before one complete bound permit."""

from __future__ import annotations

import errno
import os
import socket
import sys
from pathlib import Path

from . import restore_host as host
from . import restore_wire as wire
from .model import digest


def directory_pin(fd: int) -> dict:
    info = os.fstat(fd)
    return {"device": info.st_dev, "inode": info.st_ino}


def binding(nonce, spec, identity, image, directory, process, environment):
    return digest(
        {
            "nonce": nonce,
            "spec": spec,
            "identity": identity,
            "image": image,
            "directory": directory,
            "process": process,
            "environment": environment,
        }
    )


def execute(image_fd: int, argv: list[str], env: dict, cwd_fd: int, deadline: float):
    """ELF descriptor exec in THIS process. No subprocess or child fallback."""
    if os.execve not in os.supports_fd:
        raise ValueError("descriptor exec required")
    os.fchdir(cwd_fd)
    # Remove even inherited descriptors that Niri/Python did not explicitly hand to us.
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd >= 3 and fd != image_fd:
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
                # The enumerator's own transient directory descriptor is already closed.
    null = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in (0, 1, 2):
            os.dup2(null, fd, inheritable=True)
    finally:
        if null > 2:
            os.close(null)
    os.set_inheritable(image_fd, False)
    wire.remaining(deadline)
    os.execve(image_fd, argv, env)
    raise AssertionError("exec unexpectedly returned")


def handshake(connection, nonce: str, deadline: float, parent_pin: dict):
    pid = wire.peer_pid(connection, parent_pin["pid"])
    with (
        host.Process(pid) as parent,
        host.Image(str(Path(sys.executable).resolve()), deadline=deadline) as python,
    ):
        if parent.pin != parent_pin:
            raise ValueError("coordinator start identity changed")

        def check():
            parent.validate(python.pin, deadline=deadline)

        check()
        wire.send(connection, {"type": "hello", "nonce": nonce}, deadline, check)
        request = wire.receive(connection, deadline, check)
        wire.closed(request, {"nonce", "spec", "identity", "image", "directory"}, "prepare")
        if request["nonce"] != nonce:
            raise ValueError("bootstrap attempt mismatch")
        spec = request["spec"]
        if not isinstance(spec, dict) or set(spec) != {"argv", "cwd"}:
            raise ValueError("closed host specification required")
        recipe = {**spec, "kind": "command" if "-e" in spec["argv"] else "shell"}
        if host.admit(recipe) != spec:
            raise ValueError("uncontrolled host specification")
        host.route(request["identity"])
        # Python startup may coerce LC_CTYPE in os.environ. Bind the actual Niri-provided
        # initial environment from /proc instead, identically observed by the coordinator.
        with host.Process(os.getpid()) as own_process:
            env = host.environment(own_process.environment())
            own = own_process.pin
        cwd_fd = os.open(spec["cwd"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if directory_pin(cwd_fd) != request["directory"]:
                raise ValueError("working directory identity changed")
            with host.Image(spec["argv"][0], deadline=deadline) as image:
                if image.pin != request["image"]:
                    raise ValueError("executable identity changed before handshake")
                bound = binding(
                    nonce, spec, request["identity"], image.pin, request["directory"], own, env
                )
                wire.send(
                    connection, {"type": "ready", "nonce": nonce, "binding": bound}, deadline, check
                )
                permit = wire.receive(connection, deadline, check)
                wire.closed(permit, {"nonce", "binding"}, "exec")
                if permit != {"type": "exec", "nonce": nonce, "binding": bound}:
                    raise ValueError("complete exact exec permit required")
                host.route(request["identity"])
                image.validate()
                if directory_pin(cwd_fd) != request["directory"]:
                    raise ValueError("working directory changed before exec")
                wire.remaining(deadline)
                check()
                # After this point, peer death is NOT evidence of no effect. The coordinator
                # persisted the permit intent before sending; its fence remains authoritative.
                connection.close()
                parent.close()
                python.close()
                execute(image.fd, spec["argv"], env, cwd_fd, deadline)
        finally:
            try:
                os.close(cwd_fd)
            except OSError:
                pass


def main(argv=None) -> int:
    try:
        endpoint, nonce, expiry, pid, start, boot = list(sys.argv[1:] if argv is None else argv)
        if not endpoint.startswith("ndc-") or len(endpoint) > 80 or len(nonce) != 64:
            raise ValueError("invalid bootstrap routing")
        deadline = float(expiry)
        wire.remaining(deadline)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(wire.remaining(deadline))
            connection.connect("\0" + endpoint)
            handshake(
                connection,
                nonce,
                deadline,
                {"pid": int(pid), "start_ticks": int(start), "boot_id": boot},
            )
    except (OSError, ValueError, TypeError, KeyError, EOFError):
        return 2  # No private arguments, environment or endpoint diagnostics on stderr.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
