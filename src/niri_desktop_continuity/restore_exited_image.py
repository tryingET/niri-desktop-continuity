"""Guarded root-relative proc exe lookup, not an atomic pinned-symlink follow."""

import os
import stat

from .restore_exited_resources import FD, FDImage, resources
from .restore_wire import remaining


def image(scope, peer):
    """Return an owned measured Image. All temporary route/target FDs close on failure.

    A transient privileged graft restored across the follow can escape postchecks.
    This is the accepted sampled-route trust limit, not a containment guarantee.
    """
    with resources() as files:
        scope.check()
        peer.check()
        pid = peer.row["process"]["pid"]
        parent, identity = scope.directory(files, pid)
        if identity != peer.directory[1]:
            raise ValueError("peer directory changed before image")
        link, expected = scope.component(files, parent, "exe", stat.S_IFLNK, scope.uid)

        def check():
            scope.bracket(link, expected, parent, "exe", stat.S_IFLNK, scope.uid)
            scope.bracket(parent, identity, scope.fd, str(pid), stat.S_IFDIR, scope.uid)
            scope.check()
            peer.check()

        check()
        remaining(scope.deadline)
        fd = os.open("exe", os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOCTTY, dir_fd=parent)
        target = FD(fd, files)
        remaining(scope.deadline)
        check()  # Authenticate route before ANY accepted target data read.
        target.fd = None  # FDImage takes ownership on entry, including constructor failure.
        measured = FDImage(fd, deadline=scope.deadline)
        try:
            check()
        except BaseException:
            from .restore_exited_resources import close_failed

            close_failed(measured.close)
            raise
        # Transfer only after temporary-route cleanup succeeds.
        try:
            files.close()
        except BaseException:
            from .restore_exited_resources import close_failed

            close_failed(measured.close)
            raise
        return measured
