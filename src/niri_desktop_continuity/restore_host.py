"""Narrow Ghostty admission and Linux launch-process evidence, not window ownership."""

from __future__ import annotations

import ctypes
import hashlib
import os
import select
import shutil
import stat
from pathlib import Path

from .probe import compositor_identity, proc_stat
from .restore_wire import remaining

FLAGS = ["--config-default-files=false", "--gtk-single-instance=false", "--initial-window=true"]
KINDS = {"shell", "command", "declared", "pi", "claude"}
MAX_PROC = 128 * 1024


def admit(recipe: dict) -> dict:
    argv, cwd = recipe.get("argv"), recipe.get("cwd")
    if recipe.get("kind") not in KINDS or not isinstance(argv, list) or not argv:
        raise ValueError("unsupported launch kind")
    if not all(isinstance(a, str) and "\0" not in a for a in argv) or not argv[0]:
        raise ValueError("invalid literal launch argv")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise ValueError("explicit existing working directory required")
    if Path(argv[0]).name != "ghostty":
        raise ValueError("only the explicitly trusted native Ghostty host is admitted")
    executable = argv[0] if os.path.isabs(argv[0]) else shutil.which(argv[0])
    if not executable:
        raise ValueError("Ghostty executable unavailable")
    boundary = argv.index("-e") if "-e" in argv else len(argv)
    for arg in argv[1:boundary]:
        if arg not in FLAGS and arg != f"--working-directory={cwd}":
            raise ValueError("unsupported or conflicting captured host option")
    tail = argv[boundary:]
    if (recipe["kind"] == "shell" and tail) or (
        recipe["kind"] != "shell" and (len(tail) < 2 or not tail[1])
    ):
        raise ValueError("command tail does not match recipe kind")
    return {
        "argv": [str(Path(executable).resolve()), *FLAGS, f"--working-directory={cwd}", *tail],
        "cwd": cwd,
    }


def validate_environment(source: dict) -> None:
    if not isinstance(source, dict) or not all(
        isinstance(k, str)
        and k
        and "=" not in k
        and "\0" not in k
        and isinstance(v, str)
        and "\0" not in v
        for k, v in source.items()
    ):
        raise ValueError("invalid launch environment")


def environment(source: dict) -> dict:
    """Construct the desired launch environment; never normalize observed host evidence."""
    validate_environment(source)
    removed = {
        "WAYLAND_SOCKET",
        "DISPLAY",
        "NOTIFY_SOCKET",
        "INVOCATION_ID",
        "JOURNAL_STREAM",
        "SYSTEMD_EXEC_PID",
        "MANAGERPID",
        "MAINPID",
        "CONTROL_PID",
        "CREDENTIALS_DIRECTORY",
        "RUNTIME_DIRECTORY",
        "STATE_DIRECTORY",
        "CACHE_DIRECTORY",
        "LOGS_DIRECTORY",
        "CONFIGURATION_DIRECTORY",
        "SERVICE_RESULT",
        "EXIT_CODE",
        "EXIT_STATUS",
        "XDG_ACTIVATION_TOKEN",
        "DESKTOP_STARTUP_ID",
    }
    result = {
        k: v
        for k, v in source.items()
        if k not in removed and not k.startswith(("LISTEN_", "WATCHDOG_", "NDC_CONTROL_"))
    }
    result["GDK_BACKEND"] = "wayland"
    if not all(result.get(k) for k in ("NIRI_SOCKET", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")):
        raise ValueError("Niri Wayland launch environment required")
    if not os.path.isabs(result["XDG_RUNTIME_DIR"]):
        raise ValueError("absolute Wayland runtime directory required")
    return result


def route(identity: dict) -> None:
    if compositor_identity() != identity:
        raise ValueError("compositor route changed")


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def process_pin(pid: int) -> dict:
    return {"boot_id": boot_id(), "pid": pid, "start_ticks": proc_stat(pid)["start_ticks"]}


class Image:
    """Hold the exact ELF file; descriptor exec avoids a pathname replacement at exec."""

    def __init__(self, path: str, *, proc=False, deadline=None):
        self.deadline = deadline
        self.check_deadline()
        # Reject FIFOs at fstat without first waiting for a writer. O_NONBLOCK does not
        # bound every filesystem/kernel operation; the hash loop also checks expiry.
        self.fd = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | (0 if proc else os.O_NOFOLLOW)
        )
        try:
            self.pin = self.measure()
        except BaseException:
            self.close()
            raise

    def check_deadline(self):
        if self.deadline is not None:
            remaining(self.deadline)

    def measure(self) -> dict:
        self.check_deadline()
        before = os.fstat(self.fd)
        if not stat.S_ISREG(before.st_mode) or not 4 <= before.st_size <= 512 * 1024 * 1024:
            raise ValueError("bounded regular executable required")
        if not before.st_mode & 0o111 or os.pread(self.fd, 4, 0) != b"\x7fELF":
            raise ValueError("native ELF host required; scripts and wrappers refused")
        self.check_deadline()
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            self.check_deadline()
            block = os.pread(self.fd, min(1024 * 1024, before.st_size - offset), offset)
            self.check_deadline()
            if not block:
                raise ValueError("executable changed while hashing")
            digest.update(block)
            offset += len(block)
        after = os.fstat(self.fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in fields):
            raise ValueError("executable changed while hashing")
        self.check_deadline()
        return {"device": after.st_dev, "inode": after.st_ino, "sha256": digest.hexdigest()}

    def validate(self):
        if self.measure() != self.pin:
            raise ValueError("pinned executable changed")

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def open_pidfd(pid: int) -> int:
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid, 0)
    # Some portable Python builds omit the binding despite a capable Linux kernel/libc.
    # This is the same pidfd facility, never a PID-only approximation or raw syscall number.
    function = getattr(ctypes.CDLL(None, use_errno=True), "pidfd_open", None)
    if function is None:
        raise ValueError("Linux pidfd support required")
    function.argtypes, function.restype = [ctypes.c_int, ctypes.c_uint], ctypes.c_int
    fd = function(pid, 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "pidfd admission failed")
    return fd


class Process:
    """Retained pidfd makes exit permanent; current image is checked separately from PID."""

    def __init__(self, pid: int):
        self.fd = open_pidfd(pid)  # No PID-only fallback on older Linux.
        self.dead = False
        try:
            self.pin = process_pin(pid)
            self.live()
        except BaseException:
            self.close()
            raise

    def live(self):
        if self.fd is None or self.dead:
            raise ValueError("launch process has exited or proof was closed")
        poll = select.poll()
        poll.register(self.fd, select.POLLIN)
        if poll.poll(0) or process_pin(self.pin["pid"]) != self.pin:
            self.dead = True
            raise ValueError("launch process identity ended")

    def validate(self, expected: dict, *, deadline=None):
        self.live()
        with Image(f"/proc/{self.pin['pid']}/exe", proc=True, deadline=deadline) as image:
            if image.pin != expected:
                raise ValueError("running image differs from admitted executable")
        self.live()

    def read(self, name: str) -> bytes:
        if name not in {"environ", "cmdline"}:
            raise ValueError("unsupported process observation")
        self.live()
        with open(f"/proc/{self.pin['pid']}/{name}", "rb") as stream:
            value = stream.read(MAX_PROC + 1)
        self.live()
        if len(value) > MAX_PROC:
            raise ValueError("process observation exceeds bound")
        return value

    def environment(self) -> dict:
        """Raw initial environment exposed by /proc, not current libc/Python environ state."""
        raw = self.read("environ")
        if not raw:
            return {}
        if not raw.endswith(b"\0"):
            raise ValueError("incomplete process environment")
        parts = raw[:-1].split(b"\0")
        pairs = [part.decode("utf-8", "surrogateescape").split("=", 1) for part in parts]
        if any(len(p) != 2 for p in pairs) or len({p[0] for p in pairs}) != len(pairs):
            raise ValueError("ambiguous process environment")
        observed = dict(pairs)
        validate_environment(observed)
        return observed

    def argv(self) -> list[str]:
        raw = self.read("cmdline")
        if not raw.endswith(b"\0"):
            raise ValueError("incomplete running argv")
        return [p.decode("utf-8", "surrogateescape") for p in raw[:-1].split(b"\0")]

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.dead = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
