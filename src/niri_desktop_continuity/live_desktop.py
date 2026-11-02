"""Niri IPC transport for the restore command; read budget and constructor-only retry."""

from __future__ import annotations

import errno
import json
import subprocess
import time


class LiveDesktop:
    """Niri IPC transport for restoration. Every mutation is an explicit action."""

    def windows(self) -> list[dict]:
        return self._query("windows")

    def workspaces(self) -> list[dict]:
        return self._query("workspaces")

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

    def _query(self, command: str):
        if command not in {"windows", "workspaces", "version"}:
            raise ValueError("unsupported restore read query")
        argv = ["niri", "msg", "--json", command]
        start = self.monotonic()
        bound = start + 10.0
        last, traceback = None, None

        def budget(observed=None):
            left = bound - (self.monotonic() if observed is None else observed)
            if not left > 0:
                if last is not None:
                    raise last.with_traceback(traceback)
                raise subprocess.TimeoutExpired(argv, 10)
            return left

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
