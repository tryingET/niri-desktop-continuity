#!/usr/bin/env python3
"""Fail on home-specific paths, leaked runtime state, or nonportable runtime imports."""

from __future__ import annotations

import ast
import os
import re
import struct
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PARTS = {"state", "snapshots", "plans", "approvals", "previews", "receipts", "artifacts"}
# Documentation screenshots are the only reviewed binaries: rendered from fabricated fixtures,
# pixel and colour chunks only, because text/EXIF/ICC/time metadata can carry private strings.
PNG_ASSETS = Path("docs/assets")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_CHUNKS = {"IHDR", "PLTE", "tRNS", "IDAT", "IEND", "sRGB", "gAMA", "cHRM", "pHYs", "bKGD"}
MAX_PNG_BYTES = 512 * 1024
# The release announcement video is the only reviewed video: rendered from the fabricated demo
# desktop with every metadata box stripped (`ffmpeg -map_metadata -1 -fflags +bitexact`). Its
# boxes are walked; text-bearing ones are refused. Codec-private bytes inside mdat are not parsed.
MP4_ASSETS = Path("docs/announce")
MAX_MP4_BYTES = 8 * 1024 * 1024
MP4_CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl", "dinf", "edts", "mvex", "moof", "traf"}
MP4_METADATA = {"udta", "meta", "ilst", "keys", "uuid", "xml "}
# ffmpeg always writes this skeleton, which holds no text: udta > meta (version 0) > an unnamed
# "mdir" handler > an empty ilst. A udta box is admitted only with exactly these bytes.
EMPTY_UDTA = (
    struct.pack(">I", 53)
    + b"meta"
    + bytes(4)
    + struct.pack(">I", 33)
    + b"hdlr"
    + bytes(8)
    + b"mdirappl"
    + bytes(9)
    + struct.pack(">I", 8)
    + b"ilst"
)
MP4_HANDLERS = {b"", b"VideoHandler", b"SoundHandler"}


def mp4_problems(data: bytes) -> list[str]:
    if len(data) > MAX_MP4_BYTES:
        return [f"MP4 asset exceeds {MAX_MP4_BYTES} bytes"]
    if data[4:8] != b"ftyp":
        return ["invalid MP4 asset"]
    problems: set[str] = set()

    def walk(start: int, end: int) -> bool:
        offset = start
        while offset < end:
            if end - offset < 8:
                return False
            size, kind = (
                struct.unpack(">I", data[offset : offset + 4])[0],
                data[offset + 4 : offset + 8],
            )
            header = 8
            if size == 1 and end - offset >= 16:
                size, header = struct.unpack(">Q", data[offset + 8 : offset + 16])[0], 16
            if size < header or offset + size > end:
                return False
            name = kind.decode("latin-1")
            if name == "udta" and data[offset + header : offset + size] == EMPTY_UDTA:
                pass
            elif name in MP4_METADATA:
                problems.add(f"MP4 box {name} not allowed (metadata can carry private text)")
            elif name == "hdlr":
                handler = data[offset + header + 24 : offset + size].rstrip(b"\x00")
                if handler not in MP4_HANDLERS:
                    problems.add("MP4 handler name not allowed (it can carry private text)")
            elif name in MP4_CONTAINERS and not walk(offset + header, offset + size):
                return False
            offset += size
        return True

    if not walk(0, len(data)):
        return ["invalid MP4 asset"]
    return sorted(problems)


def png_problems(data: bytes) -> list[str]:
    if len(data) > MAX_PNG_BYTES:
        return [f"PNG asset exceeds {MAX_PNG_BYTES} bytes"]
    if not data.startswith(PNG_SIGNATURE):
        return ["invalid PNG asset"]
    offset, kinds = len(PNG_SIGNATURE), []
    while offset + 12 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        end = offset + 12 + length
        if end > len(data) or zlib.crc32(data[offset + 4 : end - 4]) != int.from_bytes(
            data[end - 4 : end], "big"
        ):
            return ["invalid PNG asset"]
        kinds.append(kind.decode("latin-1"))
        offset = end
    if offset != len(data) or kinds[:1] != ["IHDR"] or kinds[-1:] != ["IEND"]:
        return ["invalid PNG asset"]
    return [
        f"PNG chunk {kind} not allowed (metadata can carry private text)"
        for kind in sorted(set(kinds) - PNG_CHUNKS)
    ]


def source_paths():
    git = (ROOT / ".git").exists()
    paths = []
    ignore_devstate = False
    if git:
        # The index is independent of ignore rules, including forced additions and missing files.
        paths.extend(
            subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
        )
        ignore_devstate = (
            subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", ".ontology/"], cwd=ROOT, check=False
            ).returncode
            == 0
        )
    # Walk untracked inputs too: arbitrary ignore rules must not hide runtime leaks.
    # Never descend into private state, even when it is a rejected input.
    excluded = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "build"}

    def fail_walk(error: OSError) -> None:
        # os.walk otherwise suppresses scandir failures and yields an incomplete inventory.
        raise error

    for directory, dirs, files in os.walk(ROOT, followlinks=False, onerror=fail_walk):
        for name in list(dirs):
            path = Path(directory) / name
            relative = path.relative_to(ROOT)
            if path.is_symlink():
                paths.append(str(relative))
            elif relative == Path(".ontology") and ignore_devstate:
                pass
            elif name == ".ontology" or name in RUNTIME_PARTS:
                paths.append(str(relative))
            elif git and (name in excluded or relative == Path("docs/_core")):
                pass
            else:
                continue
            dirs.remove(name)
        paths.extend(str((Path(directory) / name).relative_to(ROOT)) for name in files)
    if git and (ROOT / ".git").is_file() and worktree_pointer(ROOT / ".git"):
        paths.remove(".git")  # a git worktree's link to its repository, never distributed
    return paths


def worktree_pointer(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return len(lines) == 1 and lines[0].startswith("gitdir: ")


def check() -> list[str]:
    try:
        paths = source_paths()
    except OSError:
        # Do not expose OS exception text, absolute paths or a partial-scan success.
        return ["source traversal failed: unable to enumerate source inputs"]
    failures = []
    home_path = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        parts = Path(name).parts
        if ".ontology" in parts:
            failures.append(
                f"{name}: optional development state must not be tracked or distributed"
            )
            continue
        if any(part in RUNTIME_PARTS for part in parts):
            failures.append(f"{name}: runtime state must not be distributed")
            continue
        if any(ROOT.joinpath(*parts[:end]).is_symlink() for end in range(1, len(parts) + 1)):
            failures.append(f"{name}: unreviewed source symlink")
            continue
        if not path.is_file():
            continue
        if Path(name).parent == PNG_ASSETS and path.suffix == ".png":
            failures.extend(f"{name}: {problem}" for problem in png_problems(path.read_bytes()))
            continue
        if Path(name).parent == MP4_ASSETS and path.suffix == ".mp4":
            failures.extend(f"{name}: {problem}" for problem in mp4_problems(path.read_bytes()))
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{name}: unreviewed binary artifact")
            continue
        if home_path.search(content):
            failures.append(f"{name}: hardcoded user home path")
        if name.startswith("src/") and path.suffix == ".py":
            try:
                tree = ast.parse(content, feature_version=(3, 11))
            except SyntaxError:
                failures.append(f"{name}: not Python 3.11 syntax")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    module = (node.module or "").split(".")[0]
                    if module.startswith("workstation_"):
                        failures.append(f"{name}: external machine-integration dependency")
    return failures


if __name__ == "__main__":
    errors = check()
    print("\n".join(errors) if errors else "portable-source check passed")
    raise SystemExit(bool(errors))
