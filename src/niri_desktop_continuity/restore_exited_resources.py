"""V3 FD release: attempt every close, retaining the primary failure if a close also fails."""

import os
import sys
from contextlib import contextmanager

from . import restore_host as host
from .restore_disposition_failure import cleanup_failed, latch


class _Callbacks:
    """Synchronous callback-only owner; close is terminal, once-only and nonsuppressing."""

    def __init__(self):
        self._pending = []
        self._closed = False

    def callback(self, func, /, *args, **kwargs):
        if self._closed:
            raise RuntimeError("proof-resource callbacks are closed")
        self._pending.append((func, args, kwargs))
        return func

    def close(self):
        if self._closed:
            return
        self._closed = True
        pending, self._pending = self._pending, []
        failures = []
        while pending:
            func, args, kwargs = pending.pop()
            try:
                func(*args, **kwargs)
            except BaseException as failure:
                cleanup_failed(failure)
                failures.append(failure)
        if len(failures) == 1:
            raise failures[0]
        if failures:
            raise BaseExceptionGroup("proof-resource callback failures", failures)


def close_failed(close):
    """Call only while handling the primary exception, never as a successful-path cleanup."""
    primary = sys.exception()
    previous = None if primary is None else BaseException.__cause__.__get__(primary)
    if primary is not None:
        latch(primary)
    try:
        close()
    except BaseException as failure:
        cleanup_failed(failure)
        if primary is None:
            raise
        if failure is primary:
            raise
        try:
            primary.add_note("proof-resource close also failed: " + type(failure).__name__)
        except BaseException:
            pass  # Diagnostic notes cannot replace the actual primary or cleanup objects.
        if previous is not None and previous is not failure:
            failure = BaseExceptionGroup("retained proof teardown failures", [previous, failure])
        raise primary from failure


class Image(host.Image):
    """Same held ELF measurement, with v3-only constructor failure preservation."""

    def __init__(self, path, *, proc=False, deadline=None):
        self.deadline = deadline
        self.check_deadline()
        self.fd = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | (0 if proc else os.O_NOFOLLOW)
        )
        try:
            self.pin = self.measure()
        except BaseException:
            close_failed(self.close)
            raise

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)


@contextmanager
def resources():
    stack = _Callbacks()
    try:
        yield stack
    except BaseException:
        close_failed(stack.close)
        raise
    else:
        stack.close()


class FD:
    """One owned descriptor; retire before close, including when close raises."""

    def __init__(self, fd, stack):
        self.fd = fd
        stack.callback(self.close)

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)


class FDImage(host.Image):
    """TAKES the authenticated target FD on entry; never reopens a pathname."""

    def __init__(self, fd, *, deadline):
        self.fd, self.deadline = fd, deadline
        try:
            self.pin = self.measure()
        except BaseException:
            close_failed(self.close)
            raise

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)
