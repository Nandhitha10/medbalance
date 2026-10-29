"""Deterministic simulation clock module.

Provides today() and now() synchronized with sim-control or elapsed SIM_START_DATE.
Domain logic MUST use this module instead of datetime.now().
"""

from datetime import date, datetime, timedelta, timezone
import time
from typing import Optional
import httpx
from dateutil import parser

from medbal_common.settings import get_settings

# Fallback timezone: Asia/Kolkata (UTC+5:30)
try:
    from zoneinfo import ZoneInfo
    KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    KOLKATA_TZ = timezone(timedelta(hours=5, minutes=30))

_process_start_monotonic: float = time.monotonic()
_cached_now: Optional[datetime] = None
_cached_at_monotonic: float = 0.0
_cache_ttl_seconds: float = 1.0


def _parse_sim_start_date(val: str) -> datetime:
    """Parse SIM_START_DATE string into an Asia/Kolkata timezone-aware datetime."""
    try:
        dt = parser.parse(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KOLKATA_TZ)
        else:
            dt = dt.astimezone(KOLKATA_TZ)
        return dt
    except Exception:
        # Fallback to 2026-11-01T08:00:00 IST
        return datetime(2026, 11, 1, 8, 0, 0, tzinfo=KOLKATA_TZ)


def _get_fallback_now() -> datetime:
    """Calculate current sim time based on SIM_START_DATE + elapsed wall clock time."""
    settings = get_settings()
    base_dt = _parse_sim_start_date(settings.SIM_START_DATE)
    elapsed_seconds = time.monotonic() - _process_start_monotonic
    return base_dt + timedelta(seconds=elapsed_seconds)


def now() -> datetime:
    """Return the current simulation datetime in Asia/Kolkata timezone.
    
    Queries sim-control /clock with a 1-second cache. Falls back to
    SIM_START_DATE + elapsed time if sim-control is unreachable.
    """
    global _cached_now, _cached_at_monotonic
    current_mono = time.monotonic()

    if _cached_now is not None and (current_mono - _cached_at_monotonic < _cache_ttl_seconds):
        # Adjust cached datetime by elapsed fractions within the 1-second window
        return _cached_now + timedelta(seconds=(current_mono - _cached_at_monotonic))

    settings = get_settings()
    url = f"{settings.SIM_CONTROL_URL.rstrip('/')}/clock"

    try:
        with httpx.Client(timeout=0.2) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                raw_ts = data.get("now") or data.get("clock") or data.get("timestamp")
                if raw_ts:
                    parsed = parser.parse(raw_ts)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=KOLKATA_TZ)
                    else:
                        parsed = parsed.astimezone(KOLKATA_TZ)
                    _cached_now = parsed
                    _cached_at_monotonic = current_mono
                    return _cached_now
    except Exception:
        pass

    fallback = _get_fallback_now()
    _cached_now = fallback
    _cached_at_monotonic = current_mono
    return fallback


def today() -> date:
    """Return the current simulation calendar date."""
    return now().date()
