"""Retain and revalidate ONLY the recorded launched host's working directory."""

import os


def pin(fd):
    info = os.fstat(fd)
    return {"device": info.st_dev, "inode": info.st_ino}


class Directory:
    def __init__(self, path, expected, process):
        self.path, self.expected, self.process = path, expected, process
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.validate()
        except BaseException:
            self.close()
            raise

    def validate(self):
        self.process.live()
        if pin(self.fd) != self.expected:
            raise ValueError("held launch directory changed")
        fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if pin(fd) != self.expected:
                raise ValueError("recorded launch directory path replaced")
        finally:
            os.close(fd)
        path = f"/proc/{self.process.pin['pid']}/cwd"
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            actual = pin(fd)
            if actual != self.expected or os.readlink(path) != os.path.realpath(self.path):
                raise ValueError("launched host cwd differs from recorded directory")
        finally:
            os.close(fd)
        self.process.live()
        return {"path": self.path, "directory": self.expected, "process_directory": actual}

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
