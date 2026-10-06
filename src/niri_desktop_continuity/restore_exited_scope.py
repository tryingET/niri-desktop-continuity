"""Root-init-free v3 self-coordinate theorem and retained live generations."""

import errno
import os
import select
import stat

from . import restore_exited_syscalls as calls
from . import restore_exited_values as v
from . import restore_host as host
from .restore_exited_proc import READ, Proc, pin
from .restore_exited_resources import FD, _Callbacks, close_failed, resources
from .restore_exited_syscalls import procfs  # Kept for the checked ABI test surface.
from .restore_reader import same
from .restore_wire import remaining


def absence(process):
    v.process(process)
    # ONLY errno from this exact primitive invocation can prove vacancy.
    try:
        fd = host.open_pidfd(process["pid"])
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            raise
    else:
        os.close(fd)
        raise ValueError("original PID slot occupied, including zombies or replacement generations")
    return {"process": process, "primitive": "linux-pidfd-open", "flags": 0, "errno": "ESRCH"}


class Scope(Proc):
    def __init__(self, deadline):
        self.stack = _Callbacks()
        self.deadline = deadline
        try:
            calls.profile()
            self.uid, self.caller_pid = os.getuid(), v.pid(os.getpid())
            if self.uid != os.geteuid() or self.caller_pid == 1:
                raise ValueError("same real/effective user and non-init caller required")
            self.fd = self.open(self.stack, None, "/proc", READ | os.O_DIRECTORY)
            self.step(procfs, self.fd)
            self.root_identity = self.step(calls.identity, self.fd, deadline=self.deadline)
            if stat.S_IFMT(self.root_identity[2]) != stat.S_IFDIR:
                raise ValueError("proc root must be a directory")
            self.mount_id = self.root_identity[-1]
            self.root = pin(self.step(os.fstat, self.fd))
            self.self_fd, self.self_identity = self.component(
                self.stack, self.fd, "self", stat.S_IFLNK
            )
            self.public()
            self.boot = self.boot_read()
            # This pidfd uses the caller's own C coordinates, independently of proc M.
            self.own_fd = self.pidfd(self.stack, self.caller_pid)
            self.pidns, self.userns = self.namespaces(self.stack, self.own_fd)
            self.own_directory = self.directory(self.stack, self.caller_pid)
            self.live(self.own_fd)
            self.own_row = self.info(self.caller_pid, directory=self.own_directory)
            self.check()
            # Genuine self + singleton NSpid/NStgid proves M=C (including nested M=C).
            self.value = {
                "pid_namespace": self.pidns[1],
                "user_namespace": self.userns[1],
                "procfs": {
                    **self.root,
                    "filesystem": "proc",
                    "mount_id": self.mount_id,
                    "pid_namespace": self.pidns[1],
                },
            }
        except BaseException:
            close_failed(self.stack.close)
            raise

    def pidfd(self, stack, pid):
        v.pid(pid)
        if pid == 1:
            raise ValueError("init pidfd forbidden")
        remaining(self.deadline)
        fd = host.open_pidfd(pid)
        FD(fd, stack)
        remaining(self.deadline)
        if self.step(os.get_inheritable, fd):
            raise ValueError("pidfd must be CLOEXEC")
        return fd

    def namespaces(self, stack, pidfd):
        result = []
        for command in (0xFF05, 0xFF09):
            remaining(self.deadline)
            fd = calls.namespace(pidfd, command)
            v.integer(fd, 0, 2147483647)
            FD(fd, stack)
            remaining(self.deadline)
            if self.step(os.get_inheritable, fd):
                raise ValueError("namespace FD must be CLOEXEC")
            result.append((fd, pin(self.step(os.fstat, fd))))
        return tuple(result)

    def live(self, fd):
        poll = select.poll()
        poll.register(fd, select.POLLIN)
        if self.step(poll.poll, 0):
            raise ValueError("process generation exited")

    def refresh(self, pidfd, namespaces):
        self.live(pidfd)
        with resources() as files:
            fresh = self.namespaces(files, pidfd)
            for held, observed, expected in zip(namespaces, fresh, (self.pidns, self.userns)):
                if (
                    not same(pin(self.step(os.fstat, held[0])), held[1])
                    or not same(observed[1], held[1])
                    or not same(held[1], expected[1])
                ):
                    raise ValueError("active process namespace differs")
        self.live(pidfd)

    def check(self):
        self.public()
        if self.boot_read() != self.boot:
            raise ValueError("boot changed")
        self.live(self.own_fd)
        if self.info(self.caller_pid, directory=self.own_directory) != self.own_row:
            raise ValueError("caller generation/parent/UID changed")
        self.refresh(self.own_fd, (self.pidns, self.userns))
        if self.info(self.caller_pid, directory=self.own_directory) != self.own_row:
            raise ValueError("caller changed around namespace refresh")
        self.live(self.own_fd)
        self.public()

    def close(self):
        self.stack.close()


class Generation:
    def __init__(self, scope, pid):
        self.scope, self.stack, self.fd = scope, _Callbacks(), None
        try:
            scope.check()  # No other numeric evidence before genuine-self theorem.
            self.directory = scope.directory(self.stack, pid)
            self.row = scope.info(pid, directory=self.directory)
            self.fd = scope.pidfd(self.stack, pid)
            self.pidns, self.userns = scope.namespaces(self.stack, self.fd)
            self.check()
        except BaseException:
            close_failed(self.close)
            raise

    def check(self):
        if self.fd is None:
            raise ValueError("closed process proof")
        s, pid = self.scope, self.row["process"]["pid"]
        s.public()
        s.live(self.fd)
        if s.info(pid, directory=self.directory) != self.row:
            raise ValueError("process generation/parent/UID changed")
        s.refresh(self.fd, (self.pidns, self.userns))
        if s.info(pid, directory=self.directory) != self.row:
            raise ValueError("process changed around namespace refresh")
        s.live(self.fd)
        s.public()

    def close(self):
        self.fd = None
        self.stack.close()


class AncestorGeneration:
    """Exclusion-only identity in proved proc coordinates; NOT a full-role proof.

    Singleton vectors establish the active PID coordinate, not user-namespace or
    executable identity. This type never supplies namespace handles to a full role.
    """

    def __init__(self, scope, pid):
        self.scope, self.stack, self.fd = scope, _Callbacks(), None
        try:
            scope.check()
            self.directory = scope.directory(self.stack, pid)
            self.row = scope.info(pid, directory=self.directory)
            self.fd = scope.pidfd(self.stack, pid)
            self.check()
        except BaseException:
            close_failed(self.close)
            raise

    def check(self):
        if self.fd is None:
            raise ValueError("closed ancestor proof")
        s, pid = self.scope, self.row["process"]["pid"]
        s.check()
        s.live(self.fd)
        if s.info(pid, directory=self.directory) != self.row:
            raise ValueError("ancestor generation/parent/UID changed")
        s.live(self.fd)
        s.public()

    def close(self):
        self.fd = None
        self.stack.close()


class Cohort:
    """Frozen full cohort acquired before any exclusion-only ancestor.

    No promotion, replacement or downgrade. The caller is full even without a
    window. After the initial walk, no new generation may enter the operation.
    The supplied peer is already fully authenticated before topology discovery.
    """

    def __init__(self, scope, stack, full_pids, absent, peer):
        self.scope, self.stack, self.absent = scope, stack, absent
        self.full_pids = frozenset(full_pids)
        self.generations = {}
        self.sealed = False
        peer_pid = peer.row["process"]["pid"]
        if scope.caller_pid not in self.full_pids or peer_pid not in self.full_pids:
            raise ValueError("caller and peer require full roles")
        if absent in self.full_pids:
            raise ValueError("original absent PID overlaps current proof cohort")
        if not isinstance(peer, Generation):
            raise ValueError("peer requires full generation")
        self.generations[peer_pid] = peer  # Nonowning; operation already owns peer.
        for pid in sorted(self.full_pids):
            self.full(pid)

    def full(self, pid):
        if pid == self.absent:
            raise ValueError("original absent PID overlaps current proof cohort")
        existing = self.generations.get(pid)
        if existing is not None and not isinstance(existing, Generation):
            raise ValueError("ancestor-only proof cannot satisfy full role")
        if pid not in self.full_pids:
            raise ValueError("full role outside frozen cohort")
        return self._acquire(pid, Generation)

    def ancestor(self, pid):
        if pid in self.full_pids:
            return self.full(pid)
        return self._acquire(pid, AncestorGeneration)

    def _acquire(self, pid, kind):
        if pid == self.absent:
            raise ValueError("original absent PID overlaps current proof cohort")
        if pid not in self.generations:
            if self.sealed:
                raise ValueError("caller ancestry changed outside frozen cohort")
            generation = kind(self.scope, pid)
            self.stack.callback(generation.close)
            self.generations[pid] = generation
        return self.generations[pid]


def ancestry(scope, acquire):
    rows, current, seen = [], scope.caller_pid, set()
    while current != 1:
        if current in seen or len(rows) >= 128:
            raise ValueError("unknown or cyclic caller ancestry")
        seen.add(current)
        generation = acquire(current)
        generation.check()
        rows.append(generation.row)
        current = generation.row["ppid"]
    result = {"process": rows[0]["process"], "ancestry": rows}
    v.caller(result, scope.boot, 0)
    return result
