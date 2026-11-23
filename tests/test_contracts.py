import pytest

from ingestion.contracts import validate_event

BASE = {
    "event_id": "evt_1", "event_name": "level_completed", "user_id": "user_1",
    "session_id": "s1", "event_timestamp": "2026-09-02T10:00:00Z", "country": "TR",
    "platform": "Android", "app_version": "1.4.2", "level_id": 3, "duration_seconds": 100,
}


def ok(**kw):
    return validate_event({**BASE, **kw})


def test_valid_event_normalized():
    ev, reason = ok()
    assert reason is None and ev["event_timestamp"] == "2026-09-02T10:00:00.000000Z"


def test_timezone_offset_converted_to_utc():
    ev, _ = ok(event_timestamp="2026-09-02T13:00:00+03:00")
    assert ev["event_timestamp"].startswith("2026-09-02T10:00:00")


@pytest.mark.parametrize("patch,reason", [
    ({"event_name": "level_skipped"}, "unknown_event_name"),
    ({"user_id": None}, "missing_required_field:user_id"),
    ({"level_id": None}, "missing_required_field:level_id"),
    ({"country": "XX"}, "invalid_value:country"),
    ({"platform": "Windows"}, "invalid_value:platform"),
    ({"event_timestamp": "2026-09-02T10:00:00"}, "invalid_value:event_timestamp"),
    ({"event_timestamp": "garbage"}, "invalid_value:event_timestamp"),
    ({"level_id": 0}, "invalid_value:level_id"),
    ({"app_version": "1.4"}, "invalid_value:app_version"),
    ({"hack": "1"}, "unknown_field:hack"),
    ({"user_id": "a'; DROP TABLE x;--"}, "invalid_value:user_id"),
    ({"purchase_amount": 1.0}, "unexpected_field_for_event:purchase_amount"),
])
def test_invalid_events(patch, reason):
    ev, got = ok(**patch)
    assert ev is None and got == reason


def test_purchase_requires_amount():
    ev, reason = validate_event({**BASE, "event_name": "purchase_completed", "level_id": None,
                                 "duration_seconds": None})
    assert ev is None and reason == "missing_required_field:purchase_amount"


def test_non_dict_payload():
    assert validate_event("x") == (None, "invalid_payload")
