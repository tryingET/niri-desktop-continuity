"""Niri IPC transport for the restore command; read budget and constructor-only retry."""

from __future__ import annotations

import errno
import json
import math
import subprocess
import time

from .restore_wire import remaining


class LiveDesktop:
    """Niri IPC transport for restoration. Every mutation is an explicit action."""

    def windows(self, *, deadline=None) -> list[dict]:
        return self._query("windows", deadline=deadline)

    def workspaces(self, *, deadline=None) -> list[dict]:
        return self._query("workspaces", deadline=deadline)

    def ready(self) -> bool:
        try:
            self._query("version")
            return True
        except (subprocess.SubprocessError, ValueError, OSError):
            return False

    def spawn(self, argv: list[str]) -> None:
        self.action("spawn", "--", *argv)

    def action(self, *args: str) -> None:
        command = ["niri", "msg", "action", *args]
        client = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        status = client.wait(timeout=10)  # no timeout kill or retry after ambiguous IPC
        if status:
            raise subprocess.CalledProcessError(status, command)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()

    def _query(self, command: str, *, deadline=None):
        if command not in {"windows", "workspaces", "version", "outputs"}:
            raise ValueError("unsupported restore read query")
        argv = ["niri", "msg", "--json", command]
        if command == "outputs":
            # Required inventory retains its original single-dispatch transport and budget.
            if deadline is not None:
                remaining(deadline)
            client = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                close_fds=True,
            )
            stdout, _ = client.communicate(
                timeout=10 if deadline is None else min(10, remaining(deadline))
            )  # no automatic process termination
            if deadline is not None:
                remaining(deadline)
            if client.returncode:
                raise subprocess.CalledProcessError(client.returncode, argv)
            result = json.loads(stdout)
            if deadline is not None:
                remaining(deadline)
            return result

        start = self.monotonic()
        bound = start + 10.0
        last, traceback = None, None

        def budget(observed=None):
            checked = self.monotonic() if observed is None else observed
            left = bound - checked
            caller = None if deadline is None else deadline - checked
            invalid = caller is not None and (not math.isfinite(caller) or not 0 < caller <= 300)
            if invalid or not left > 0:
                if last is not None:
                    raise last.with_traceback(traceback)
                if invalid:
                    raise TimeoutError("bootstrap absolute deadline exceeded or invalid")
                raise subprocess.TimeoutExpired(argv, 10)
            return left if caller is None else min(left, caller)

        budget(start)
        for attempt in range(3):
            budget()
            try:
                client = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    close_fds=True,
                )
            except BlockingIOError as exc:
                if type(exc) is not BlockingIOError or exc.errno != errno.EAGAIN:
                    raise
                last, traceback = exc, exc.__traceback__
                if attempt == 2:
                    raise
                delay = (0.05, 0.10)[attempt]
                if budget() <= delay:
                    raise
                self.sleep(delay)
                continue
            # A created client is never retried, terminated, or implicitly cleaned up.
            stdout, _ = client.communicate(timeout=budget())
            budget()
            if client.returncode:
                raise subprocess.CalledProcessError(client.returncode, argv)
            result = json.loads(stdout)
            budget()
            return result
