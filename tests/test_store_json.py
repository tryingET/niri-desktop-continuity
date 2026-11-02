"""Stored artifacts parse strictly: a duplicate key or non-finite number never reaches a caller."""

import pytest

from niri_desktop_continuity.store import Store


def placed(tmp_path, body: bytes) -> tuple[Store, str]:
    """A fabricated artifact written directly, so the refusal comes from reading it."""
    store = Store(tmp_path / "state")
    key = "0" * 64
    path = store.path("receipts", key)
    path.write_bytes(body)
    path.chmod(0o600)
    return store, key


@pytest.mark.parametrize(
    "body", [b'{"x":1e999}', b'{"x":{"y":-1e999}}', b'{"x":[0,{"y":1e999}]}', b'{"x":NaN}']
)
def test_get_refuses_nonfinite_numbers_at_any_depth(tmp_path, body):
    store, key = placed(tmp_path, body)
    with pytest.raises(ValueError, match="nonfinite"):
        store.get("receipts", key)


@pytest.mark.parametrize("body", [b'{"type":"a","type":"b"}', b'{"x":{"y":1,"y":2}}'])
def test_get_refuses_duplicate_fields_at_any_depth(tmp_path, body):
    store, key = placed(tmp_path, body)
    with pytest.raises(ValueError, match="duplicate"):
        store.get("receipts", key)


def test_get_refuses_a_top_level_that_is_not_an_object(tmp_path):
    store, key = placed(tmp_path, b"[]")
    with pytest.raises(ValueError, match="integrity"):
        store.get("receipts", key)


def test_finite_floats_survive_the_round_trip_exactly(tmp_path):
    store = Store(tmp_path / "state")
    value = {"x": [1e308, -0.5]}
    assert store.get("receipts", store.put("receipts", value)) == value
