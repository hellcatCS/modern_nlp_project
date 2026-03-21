from datetime import time

from src.functions import _validate_booking_slot, cancel_booking


class DummyRestaurant:
    opening_time = time(12, 0)
    closing_time = time(23, 0)


def test_validate_booking_slot_ok():
    start_at, end_at, error = _validate_booking_slot(DummyRestaurant(), "2026-03-24", "18:30")
    assert error is None
    assert start_at.hour == 18
    assert end_at.hour == 20


def test_validate_booking_slot_requires_30_minutes():
    _, _, error = _validate_booking_slot(DummyRestaurant(), "2026-03-24", "18:10")
    assert "кратно 30 минутам" in error


def test_validate_booking_slot_in_open_hours():
    _, _, error = _validate_booking_slot(DummyRestaurant(), "2026-03-24", "22:00")
    assert "рабочие часы" in error


def test_cancel_booking_not_found(monkeypatch):
    from src import functions

    monkeypatch.setattr(functions.Booking, "get_or_none", lambda *args, **kwargs: None)
    result = cancel_booking.invoke({"booking_id": "ABC1234"})
    assert "не найдено" in result
