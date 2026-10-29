"""Tests for deterministic simulation clock."""

from datetime import date, datetime
from medbal_common.clock import now, today


def test_clock_today_and_now():
    """Verify that today() and now() return valid datetime/date without throwing."""
    n = now()
    t = today()

    assert isinstance(n, datetime)
    assert isinstance(t, date)
    assert t == n.date()
    assert n.year == 2026
