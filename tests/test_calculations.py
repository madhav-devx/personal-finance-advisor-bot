from datetime import date
from decimal import Decimal as Dm

from app.calculations import format_money, goal_progress, month_bounds, pct, shift_month


def test_indian_and_western_money_formatting():
    assert format_money(1234567.5) == "₹12,34,567.50"
    assert format_money(-8000, "₹", 0) == "-₹8,000"
    assert format_money(1234567, "$", 0) == "$1,234,567"


def test_month_arithmetic():
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)
    assert month_bounds(2026, 12) == (date(2026, 12, 1), date(2027, 1, 1))


def test_pct_handles_zero():
    assert pct(5, 0) is None
    assert pct(25, 100) == 25.0


def test_goal_progress_basic():
    p = goal_progress(Dm(50000), Dm(10000), date(2026, 8, 1), date(2027, 2, 1), today=date(2026, 10, 15))
    assert p["percent"] == 20.0 and p["remaining"] == Dm(40000)
    assert p["required_monthly"] == Dm("10000.00") and p["status"] in ("on_track", "behind")


def test_goal_progress_states():
    today = date(2026, 10, 15)
    assert goal_progress(1000, 1000, today, date(2027, 1, 1), today=today)["status"] == "achieved"
    assert goal_progress(1000, 0, today, date(2027, 1, 1), today=today)["status"] == "not_started"
    assert goal_progress(1000, 100, date(2026, 1, 1), date(2026, 6, 1), today=today)["status"] == "overdue"
    over = goal_progress(1000, 1500, today, date(2027, 1, 1), today=today)
    assert over["percent"] == 100.0 and over["remaining"] == 0
