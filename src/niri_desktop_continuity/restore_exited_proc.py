"""V3 held-root, same-FD proc provenance and bounded stable process projections."""

import os
import re
import stat

from . import restore_exited_syscalls as calls
from . import restore_exited_values as v
from .restore_exited_resources import FD, resources
from .restore_wire import remaining

READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOCTTY
PATH = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC


def pin(info):
    return {"device": info.st_dev, "inode": info.st_ino}


class Proc:
    def step(self, function, *args, **kwargs):
        remaining(self.deadline)
        result = function(*args, **kwargs)
        remaining(self.deadline)
        return result

    def open(self, stack, parent, name, flags):
        remaining(self.deadline)
        fd = os.open(name, flags, dir_fd=parent)
        FD(fd, stack)  # Own before any fallible postcheck.
        remaining(self.deadline)
        return fd

    def auth(self, fd, kind, uid=None):
        value = self.step(calls.identity, fd, deadline=self.deadline)
        if value[-1] != self.mount_id or stat.S_IFMT(value[2]) != kind:
            raise ValueError("foreign proc mount or component type")
        if uid is not None and value[3] != uid:
            raise ValueError("foreign process object owner")
        return value

    def component(self, stack, parent, name, kind, uid=None):
        if not name or "/" in name or name in (".", ".."):
            raise ValueError("one fixed proc component required")
        flags = READ if kind == stat.S_IFREG else PATH
        if kind == stat.S_IFDIR:
            flags |= os.O_DIRECTORY
        fd = self.open(stack, parent, name, flags)
        return fd, self.auth(fd, kind, uid)

    def bracket(self, fd, expected, parent, name, kind, uid=None):
        if self.auth(fd, kind, uid) != expected:
            raise ValueError("held proc component drift")
        with resources() as files:
            _, fresh = self.component(files, parent, name, kind, uid)
            if fresh != expected:
                raise ValueError("proc route drift")

    def public(self):
        remaining(self.deadline)
        if os.getpid() != self.caller_pid or os.getuid() != self.uid or os.geteuid() != self.uid:
            raise ValueError("caller changed within proof")
        with resources() as files:
            fd = self.open(files, None, "/proc", READ | os.O_DIRECTORY)
            if self.step(calls.identity, fd, deadline=self.deadline) != self.root_identity:
                raise ValueError("public proc root replaced")
        if self.step(calls.identity, self.fd, deadline=self.deadline) != self.root_identity:
            raise ValueError("held proc root changed")
        self.step(calls.procfs, self.fd)
        self.bracket(self.self_fd, self.self_identity, self.fd, "self", stat.S_IFLNK)
        text = self.step(os.readlink, "", dir_fd=self.self_fd)
        if (
            not re.fullmatch(r"[1-9][0-9]{0,9}", text, re.ASCII)
            or v.pid(int(text)) != self.caller_pid
        ):
            raise ValueError("genuine proc self coordinate mismatch")

    def read_leaf(self, parent, name, uid=None):
        with resources() as files:
            fd, expected = self.component(files, parent, name, stat.S_IFREG, uid)
            self.bracket(fd, expected, parent, name, stat.S_IFREG, uid)
            data = bytearray()
            while True:
                chunk = self.step(os.read, fd, min(16384, 128 * 1024 + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 128 * 1024:
                    raise ValueError("proc entry exceeds bound")
            self.bracket(fd, expected, parent, name, stat.S_IFREG, uid)
            return bytes(data)

    def boot_read(self):
        with resources() as files:
            parent, routes = self.fd, []
            for name in ("sys", "kernel", "random"):
                fd, expected = self.component(files, parent, name, stat.S_IFDIR)
                routes.append((fd, expected, parent, name))
                parent = fd
            raw = self.read_leaf(parent, "boot_id").decode("ascii")
            for fd, expected, parent, name in reversed(routes):
                self.bracket(fd, expected, parent, name, stat.S_IFDIR)
            result = raw.strip()
            v.text(result)
            return result

    def directory(self, stack, pid):
        v.pid(pid)
        if pid == 1:
            raise ValueError("init is not a process proof target")
        return self.component(stack, self.fd, str(pid), stat.S_IFDIR, self.uid)

    def info(self, pid, *, directory=None):
        with resources() as files:
            fd, expected = self.directory(files, pid)
            if directory is not None:
                held, previous = directory
                self.bracket(held, previous, self.fd, str(pid), stat.S_IFDIR, self.uid)
                if expected != previous:
                    raise ValueError("process directory generation changed")
            raw = self.read_leaf(fd, "stat", self.uid)
            status = self.read_leaf(fd, "status", self.uid)
            row = process_info(raw, status, pid, self.uid, self.boot)
            self.bracket(fd, expected, self.fd, str(pid), stat.S_IFDIR, self.uid)
            return row


def process_info(raw, status, pid, uid, boot):
    v.pid(pid)
    v.integer(uid, 0, 2**32 - 2)
    if any(
        not isinstance(x, bytes) or not x.endswith(b"\n") or b"\0" in x or len(x) > 128 * 1024
        for x in (raw, status)
    ):
        raise ValueError("invalid bounded proc framing")
    text = raw.decode("utf-8")
    match = re.fullmatch(r"([1-9][0-9]*) \((.*)\) ([RSDTtI]) (.*)\n", text, re.DOTALL)
    if match is None or match[1] != str(pid):
        raise ValueError("invalid, exited or zombie process stat")
    fields = match[4].split()
    if len(fields) < 19 or any(
        not re.fullmatch(r"[1-9][0-9]*", fields[i], re.ASCII) for i in (0, 18)
    ):
        raise ValueError("invalid stat parent/start")
    ppid, start = int(fields[0]), int(fields[18])
    v.pid(ppid)
    v.integer(start, 1)
    values = {}
    for line in status.decode("ascii").splitlines(keepends=True):
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*):[ \t]*([^\r\n]*)\n", line, re.ASCII)
        if match is None or match[1] in values or any(ord(c) < 32 and c != "\t" for c in match[2]):
            raise ValueError("malformed or duplicate status field")
        values[match[1]] = match[2].split()
    expected = {
        "Pid": [str(pid)],
        "Tgid": [str(pid)],
        "PPid": [str(ppid)],
        "Uid": [str(uid)] * 4,
        "NSpid": [str(pid)],
        "NStgid": [str(pid)],
    }
    if any(values.get(k) != value for k, value in expected.items()):
        raise ValueError("unmapped/foreign UID or inconsistent proc PID/parent/scope")
    return {"process": {"boot_id": boot, "pid": pid, "start_ticks": start}, "ppid": ppid}
