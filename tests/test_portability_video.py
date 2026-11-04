"""The announcement video is the one reviewed video: no metadata box may carry text."""

from __future__ import annotations

import struct

import pytest
from test_portability import checker, put

FILM = "docs/announce/film.mp4"


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def hdlr(name: bytes) -> bytes:
    """version/flags, pre_defined, handler type, three reserved words, then the name."""
    return box(b"hdlr", bytes(4) + bytes(4) + b"vide" + bytes(12) + name + b"\x00")


def mp4(*moov: bytes, tail: bytes = b"") -> bytes:
    """Handwritten minimal MP4: ftyp, a moov holding mvhd plus the given boxes, then mdat."""
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2avc1mp41")
    return (
        ftyp
        + box(b"moov", box(b"mvhd", bytes(100)) + b"".join(moov))
        + box(b"mdat", b"\xff" * 16)  # a real payload is not text
        + tail
    )


def track(*mdia: bytes) -> bytes:
    return box(
        b"trak", box(b"tkhd", bytes(84)) + box(b"mdia", box(b"mdhd", bytes(24)) + b"".join(mdia))
    )


@pytest.fixture
def module(tmp_path, monkeypatch):
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def test_a_clean_video_in_docs_announce_is_admitted_and_only_there(module, tmp_path):
    put(tmp_path, FILM, mp4(track(hdlr(b"VideoHandler"))))
    assert module.check() == []
    put(tmp_path, "docs/assets/film.mp4", mp4())
    put(tmp_path, "docs/announce/nested/film.mp4", mp4())
    put(tmp_path, "docs/announce/film.mov", mp4())
    assert module.check() == [
        "docs/announce/film.mov: unreviewed binary artifact",
        "docs/announce/nested/film.mp4: unreviewed binary artifact",
        "docs/assets/film.mp4: unreviewed binary artifact",
    ]


@pytest.mark.parametrize(
    ("kind", "where"),
    [(b"udta", "moov"), (b"meta", "moov"), (b"uuid", "moov"), (b"udta", "trak"), (b"ilst", "mdia")],
)
def test_metadata_boxes_are_refused_at_any_depth(module, tmp_path, kind, where):
    private = "/".join(["", "home", "example", "capture.json"]).encode()
    text = box(kind, box(b"\xa9cmt", private))
    film = {"moov": mp4(text), "trak": mp4(track() + box(b"trak", text)), "mdia": mp4(track(text))}
    put(tmp_path, FILM, film[where])
    assert module.check() == [
        f"{FILM}: MP4 box {kind.decode()} not allowed (metadata can carry private text)"
    ]


def test_ffmpegs_empty_metadata_skeleton_is_admitted_and_nothing_more(module, tmp_path):
    # Handwritten: udta(61) > meta(53, version 0) > hdlr(33, "mdir"/"appl", no name) > ilst(8).
    skeleton = (
        b"\x00\x00\x00\x3dudta\x00\x00\x00\x35meta\x00\x00\x00\x00"
        b"\x00\x00\x00\x21hdlr\x00\x00\x00\x00\x00\x00\x00\x00mdirappl"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x08ilst"
    )
    put(tmp_path, FILM, mp4(track(hdlr(b"VideoHandler")), skeleton))
    assert module.check() == []
    with_item = skeleton[:-8] + box(b"ilst", box(b"\xa9too", b"Lavf63"))
    with_item = box(b"udta", box(b"meta", with_item[16:]))  # same skeleton, one ilst item
    put(tmp_path, FILM, mp4(with_item))
    assert module.check() == [f"{FILM}: MP4 box udta not allowed (metadata can carry private text)"]


def test_a_handler_name_can_only_be_a_standard_one(module, tmp_path):
    put(tmp_path, FILM, mp4(track(hdlr(b"Steve's capture"))))
    assert module.check() == [f"{FILM}: MP4 handler name not allowed (it can carry private text)"]


@pytest.mark.parametrize(
    "data",
    [
        b"not a video at all",  # no ftyp first
        mp4()[:-3],  # mdat cut short
        mp4(tail=struct.pack(">I", 4) + b"free"),  # a box shorter than its own header
        mp4(tail=struct.pack(">I", 64) + b"free"),  # a box longer than the file
        mp4(tail=b"\x00\x00"),  # trailing bytes that are not a box
    ],
)
def test_malformed_videos_are_refused(module, tmp_path, data):
    put(tmp_path, FILM, data)
    assert module.check() == [f"{FILM}: invalid MP4 asset"]


def test_video_size_is_bounded(module, tmp_path, monkeypatch):
    film = mp4()
    monkeypatch.setattr(module, "MAX_MP4_BYTES", len(film) - 1)
    put(tmp_path, FILM, film)
    assert module.check() == [f"{FILM}: MP4 asset exceeds {len(film) - 1} bytes"]
