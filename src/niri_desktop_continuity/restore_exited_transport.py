"""Persistent read-only Niri LF protocol; authenticate the reply-bearing FD every time."""

import os
import select
import socket
import stat
import struct
from pathlib import Path

from . import restore_exited_values as v
from . import restore_observation as observation
from . import restore_state as states
from .restore_exited_resources import close_failed
from .restore_reader import same
from .restore_retained import json_bytes
from .restore_wire import remaining

MAX_FRAME = 8 * 1024**2  # Includes the terminating LF.
REQUESTS = {
    name: ('"' + name + '"\n').encode("ascii")
    for name in ("Version", "Windows", "Workspaces", "Outputs")
}


def endpoint(identity):
    v.identity(identity)
    route = Path(identity["niri_socket"])
    uid = os.getuid()
    if uid != os.geteuid():
        raise ValueError("real/effective UID mismatch")
    for ancestor in reversed(route.parents):
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, uid) or info.st_mode & 0o022:
            raise ValueError("unsafe endpoint ancestry")
    parent, info = route.parent.lstat(), route.lstat()
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != uid
        or info.st_mode & 0o022
        or info.st_dev != identity["socket_device"]
        or info.st_ino != identity["socket_inode"]
    ):
        raise ValueError("retained socket route changed or unsafe")
    return {
        "path": str(route),
        "directory": {"device": parent.st_dev, "inode": parent.st_ino},
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
    }


class Transport:
    def __init__(self, identity, deadline):
        self.identity, self.deadline, self.socket = identity, deadline, None
        self.endpoint = endpoint(identity)
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if self.socket.get_inheritable():
                raise ValueError("IPC descriptor must be CLOEXEC")
            self.socket.settimeout(remaining(deadline))
            self.socket.connect(identity["niri_socket"])
            self.credentials = self.peer()
            self.check()
        except BaseException:
            close_failed(self.close)
            raise

    def peer(self):
        raw = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("iII"))
        pid, uid, gid = struct.unpack("iII", raw)  # pid_t signed; uid_t/gid_t unsigned.
        v.pid(pid)
        if uid != os.getuid() or uid != os.geteuid() or gid < 0:
            raise ValueError("foreign or unmapped peer credentials")
        return {"pid": pid, "uid": uid, "gid": gid}

    def check(self):
        remaining(self.deadline)
        if not same(self.peer(), self.credentials) or not same(
            endpoint(self.identity), self.endpoint
        ):
            raise ValueError("authenticated route/peer changed")

    def surplus(self):
        if select.select([self.socket], [], [], 0)[0]:
            raise ValueError("unsolicited bytes or closed IPC stream")

    def query(self, name):
        if name not in REQUESTS:
            raise ValueError("read-only literal Niri request required")
        self.check()
        self.surplus()
        self.socket.settimeout(remaining(self.deadline))
        self.socket.sendall(REQUESTS[name])
        data = bytearray()
        while b"\n" not in data:
            self.socket.settimeout(remaining(self.deadline))
            chunk = self.socket.recv(min(65536, MAX_FRAME - len(data)))
            remaining(self.deadline)
            if not chunk:
                raise ValueError("truncated or oversized IPC reply")
            data.extend(chunk)
            if len(data) >= MAX_FRAME and b"\n" not in data:
                raise ValueError("IPC reply exceeds bound")
        if data[-1:] != b"\n" or data.count(b"\n") != 1:
            raise ValueError("extra IPC frame")
        value = json_bytes(bytes(data).decode("utf-8", "strict"))
        states.fields(value, "Ok")
        states.fields(value["Ok"], name)
        payload = value["Ok"][name]
        v.metadata(payload)
        if name == "Version":
            v.text(payload)
        elif not isinstance(payload, dict if name == "Outputs" else list):
            raise ValueError("wrong Niri response payload type")
        self.check()  # SO_PEERCRED on precisely the FD from which this reply was read.
        self.surplus()
        remaining(self.deadline)
        return payload

    def topology(self):
        windows = self.query("Windows")
        workspaces = self.query("Workspaces")
        outputs = self.query("Outputs")
        # Validate raw inputs before record() can supply defaults or erase duplicates.
        if (
            len(windows) > 512
            or len(workspaces) > 512
            or len(outputs) > 512
            or any(not isinstance(w, dict) for w in [*windows, *workspaces])
        ):
            raise ValueError("invalid bounded topology")
        for w in windows:
            for k in ("id", "workspace_id"):
                v.integer(w[k])
            v.pid(w["pid"])
            for k in ("is_focused", "is_floating"):
                if type(w[k]) is not bool:
                    raise ValueError("missing/invalid window flag")
            states.fields(
                {
                    k: w["layout"][k]
                    for k in (
                        "pos_in_scrolling_layout",
                        "tile_size",
                        "window_size",
                        "tile_pos_in_workspace_view",
                    )
                },
                "pos_in_scrolling_layout tile_size window_size tile_pos_in_workspace_view",
            )
        for w in workspaces:
            for k in ("is_focused", "is_active"):
                if type(w[k]) is not bool:
                    raise ValueError("missing/invalid workspace flag")
            for k in ("id", "idx", "output", "name", "active_window_id"):
                w[k]
        if len({w["id"] for w in windows}) != len(windows):
            raise ValueError("duplicate window ID")
        for name, output in outputs.items():
            if output.get("name") != name:
                raise ValueError("output key/name mismatch")
        observation.output_inventory(outputs)
        value = states.record(
            ({w["id"]: w for w in windows}, workspaces, states.output_scales(outputs, workspaces))
        )
        v.state(value)
        return value

    def close(self):
        if self.socket is not None:
            sock, self.socket = self.socket, None
            sock.close()
