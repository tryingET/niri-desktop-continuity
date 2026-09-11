"""Data-only schemas of the retained State/Journal and one-shot bootstrap records.

No owner imports, filesystem discovery through payload paths, or native queries. These
are historical byte contracts, not permission to execute the retained startup inputs.
"""

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from .model import digest
from .recovery_profile import pin_spec
from .recovery_projection import validate as projections
from .recovery_protocol import fields, hexkey, require

DIRECTORIES = ("objects", "attempts", "events", "children", "finished", "bootstraps")
CATALOG = {"schema": "workstation.saved-reopen.catalog.v1", "directories": list(DIRECTORIES)}
STARTUP = (
    "schema",
    "agent_dir",
    "presence_dir",
    "tmp_dir",
    "pi_version",
    "settings",
    "auth",
    "models_store",
    "presence",
)


def number(value, minimum=0):
    require(type(value) is int and minimum <= value < 2**63)


def text(value):
    require(type(value) is str and 0 < len(value) <= 4096 and "\0" not in value)


def absolute(value):
    text(value)
    p = Path(value)
    require(p.is_absolute() and str(p) == value and ".." not in p.parts)


def boot(value):
    text(value)
    require(str(UUID(value)) == value)


def expiry(value):
    text(value)
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(0))


def selection(value):
    fields(value, ("file", "id", "cwd"))
    absolute(value["file"])
    absolute(value["cwd"])
    boot(value["id"])


def metadata(value, item):
    fields(value, ("header", "bytes", "sha256", "device", "inode"))
    fields(value["header"], ("id", "cwd", "parentSession"))
    require(value["header"]["id"] == item["id"] and value["header"]["cwd"] == item["cwd"])
    parent = value["header"]["parentSession"]
    if parent is not None:
        absolute(parent)
    for key in ("bytes", "device", "inode"):
        number(value[key])
    require(0 < value["bytes"] <= 256 * 1024 * 1024)
    hexkey(value["sha256"])


def manifest(value):
    fields(
        value,
        (
            "saved_set",
            "identity_digest",
            "state_fingerprint",
            "focus_digest",
            "focus",
            "protected",
            "items",
            "saved_selection",
            "projections",
        )
        + (("groups",) if "groups" in value else ()),
    )
    for key in ("saved_set", "identity_digest", "state_fingerprint", "focus_digest"):
        hexkey(value[key])
    fields(value["focus"], ("windows", "workspaces"))
    require(digest(value["focus"]) == value["focus_digest"])
    fields(value["protected"], ("identity", "windows", "processes"))
    require(digest(value["protected"]["identity"]) == value["identity_digest"])
    require(type(value["protected"]["windows"]) is list)
    require(type(value["protected"]["processes"]) is list)
    items = value["items"]
    require(type(items) is dict and 1 <= len(items) <= 256)
    files, ids = set(), set()
    for ref, row in items.items():
        hexkey(ref)
        fields(row, ("selection", "metadata", "present"))
        item = row["selection"]
        selection(item)
        require(ref == digest({"kind": "pi", **item}))
        files.add(item["file"])
        ids.add(item["id"])
        if row["metadata"] is not None:
            metadata(row["metadata"], item)
        if row["present"] is not None:
            from .resolution_worker_history_native import native

            native(row["present"])
            require(all(row["present"][k] == item[k] for k in ("file", "id", "cwd")))
    require(len(files) == len(ids) == len(items))
    dispositions = value["saved_selection"]
    fields(dispositions, ("missing_refs", "present_refs", "unresolved_refs"))
    all_refs = []
    for refs in dispositions.values():
        require(type(refs) is list and refs == sorted(set(refs)))
        all_refs.extend(refs)
    require(sorted(all_refs) == sorted(items))
    for ref in dispositions["missing_refs"] + dispositions["present_refs"]:
        require(items[ref]["metadata"] is not None)
        require((items[ref]["present"] is not None) == (ref in dispositions["present_refs"]))
    public = value["projections"]
    fields(public, ("diagnostics",) + (("grouping",) if "groups" in value else ()))
    projections(public, value["saved_set"], sorted(items), dispositions)
    if "groups" in value:
        groups = value["groups"]
        require(type(groups) is list and 1 <= len(groups) <= 256)
        seen, projected = [], []
        for group in groups:
            fields(group, ("session_ids", "refs", "provenance", "reviewed", "sequence"))
            require(type(group["refs"]) is list and bool(group["refs"]))
            require(all(ref in items for ref in group["refs"]))
            require(group["session_ids"] == [items[r]["selection"]["id"] for r in group["refs"]])
            seen.extend(group["refs"])
            projected.append(
                {
                    "session_refs": group["refs"],
                    **{
                        k: group[k]
                        for k in (
                            "provenance",
                            "reviewed",
                            "sequence",
                        )
                    },
                }
            )
        require(sorted(seen) == sorted(items))
        require(public["grouping"]["groups"] == projected)


def host(value):
    fields(
        value,
        (
            "pid",
            "start_ticks",
            "boot_id",
            "exe",
            "exe_sha256",
            "exe_inode",
            "exe_device",
            "cwd",
            "tty",
        ),
    )
    boot(value["boot_id"])
    for key in ("pid", "start_ticks", "exe_inode", "exe_device", "tty"):
        number(value[key])
    require(value["pid"] > 1 and value["start_ticks"] > 0)
    absolute(value["exe"])
    absolute(value["cwd"])
    hexkey(value["exe_sha256"])


def request(value):
    fields(
        value,
        (
            "attempt",
            "session_ref",
            "file",
            "id",
            "cwd",
            "file_sha256",
            "node",
            "pi",
            "bootstrap",
            "python",
            "expires_at",
        )
        + (("startup",) if "startup" in value else ()),
    )
    hexkey(value["attempt"])
    hexkey(value["session_ref"])
    selection({key: value[key] for key in ("file", "id", "cwd")})
    hexkey(value["file_sha256"])
    expiry(value["expires_at"])
    for key in ("node", "pi", "bootstrap", "python"):
        pin_spec(value[key])
    if "startup" in value:
        startup = value["startup"]
        fields(startup, STARTUP)
        require(
            startup["schema"]
            in (
                "workstation.saved-reopen.presence-only.v1",
                "workstation.saved-reopen.presence-only.v2",
            )
        )
        for key in ("agent_dir", "presence_dir", "tmp_dir"):
            absolute(startup[key])
        text(startup["pi_version"])
        require(len(startup["pi_version"]) <= 64)
        require(len(startup["pi_version"].split(".")) == 3)
        require(all(v.isdecimal() for v in startup["pi_version"].split(".")))
        for key in ("settings", "auth", "models_store", "presence"):
            pin_spec(startup[key])


def argv(value):
    result = [value["node"]["path"], value["pi"]["path"]]
    if "startup" in value:
        result += [
            "--no-extensions",
            "--offline",
            "--extension",
            value["startup"]["presence"]["path"],
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-approve",
            "--no-context-files",
        ]
    else:
        result += ["--offline"]
    return [*result, "--session", value["file"]]


def record(path, value):
    """Return an exact role; unknown object shapes/namespaces never fall back."""
    directory, name = path.split("/")
    key = name[:-5]
    if directory == "objects":
        require(digest(value) == hexkey(key))
        if "items" in value:
            manifest(value)
            return "manifest"
        layouts = {
            "intent": ("attempt", "sequence", "kind", "target_ref"),
            "measurement": ("attempt", "intent_ref", "measurement"),
            "result": ("sequence", "intent_ref", "outcome", "evidence_ref"),
            "ack": ("attempt", "sequence", "result_ref"),
        }
        roles = [role for role, keys in layouts.items() if set(value) == set(keys)]
        if not roles:
            from .resolution_worker_history_native import extra_object

            return extra_object(value)
        require(len(roles) == 1)
        role = roles[0]
        for k in ("attempt", "intent_ref", "target_ref", "evidence_ref", "result_ref"):
            if k in value:
                hexkey(value[k])
        if "sequence" in value:
            number(value["sequence"])
            require(value["sequence"] < 256)
        if role == "intent":
            require(value["kind"] in ("launch", "focus"))
        if role == "result":
            require(value["outcome"] == "observed")
        if role == "measurement":
            if type(value["measurement"]) is dict:
                fields(value["measurement"], ("focused",))
                number(value["measurement"]["focused"])
            else:
                number(value["measurement"], 2)
        return role
    if directory == "attempts":
        fields(value, ("request_digest",))
        hexkey(value["request_digest"])
    elif directory == "events":
        fields(value, ("intent_ref",))
        hexkey(value["intent_ref"])
    elif directory == "children":
        fields(
            value,
            ("attempt", "session_ref", "pid", "host")
            + (("dispatch_ref",) if "dispatch_ref" in value else ()),
        )
        if "dispatch_ref" in value:
            hexkey(value["dispatch_ref"])
        hexkey(value["attempt"])
        hexkey(value["session_ref"])
        number(value["pid"], 2)
        host(value["host"])
        require(value["pid"] == value["host"]["pid"])
    elif directory == "bootstraps":
        if key.endswith(".started"):
            fields(
                value,
                (
                    "request",
                    "request_sha256",
                    "pid",
                    "start_ticks",
                    "ppid",
                    "cwd",
                    "argv",
                    "boot_id",
                ),
            )
            absolute(value["request"])
            absolute(value["cwd"])
            hexkey(value["request_sha256"])
            boot(value["boot_id"])
            for k in ("pid", "start_ticks", "ppid"):
                number(value[k], 1)
            require(value["pid"] > 1 and value["ppid"] > 1)
            require(type(value["argv"]) is list and 1 <= len(value["argv"]) <= 32)
            for arg in value["argv"]:
                text(arg)
            return "claim"
        request(value)
        return "request"
    elif directory == "finished":
        from .resolution_worker_history_native import finished

        finished(value)
    else:
        require(False)
    return directory
