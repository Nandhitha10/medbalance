"""Deterministic date parsing and resolution utilities for clinical reports."""

import calendar
from datetime import date, datetime
import re
from typing import Optional


def parse_mmyyyy_to_last_day(mmyyyy_str: str) -> Optional[date]:
    """Parse MM/YYYY (or MM-YYYY) format into the last calendar day of that month.
    
    Example: '11/2026' -> 2026-11-30, '02/2028' -> 2028-02-29.
    """
    clean_str = mmyyyy_str.strip()
    match = re.match(r"^(\d{1,2})[/\-](\d{4})$", clean_str)
    if not match:
        return None

    month = int(match.group(1))
    year = int(match.group(2))
    if month < 1 or month > 12:
        return None

    _, last_day = calendar.monthrange(year, month)
    return date(year, month, last_day)


def resolve_clinical_date(date_raw: str, report_date: Optional[date] = None) -> Optional[date]:
    """Deterministically resolve raw date strings into ISO date objects.
    
    Supports:
    - ISO format: YYYY-MM-DD (e.g. 2026-11-21)
    - Full DD/MM/YYYY or DD-MM-YYYY (e.g. 14/08/1999, 21/11/2026)
    - Short MM/YYYY (e.g. 11/2026 -> last day of month)
    - Relative short date DD/MM (e.g. 15/11 -> next occurrence on or after report_date)
    """
    if not date_raw:
        return None

    date_str = date_raw.strip()
    ref_date = report_date or date.today()

    # 1. ISO format: YYYY-MM-DD
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            return None

    # 2. MM/YYYY format
    mmyyyy_res = parse_mmyyyy_to_last_day(date_str)
    if mmyyyy_res:
        return mmyyyy_res

    # 3. Full DD/MM/YYYY or DD-MM-YYYY
    dmy_match = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", date_str)
    if dmy_match:
        try:
            d = int(dmy_match.group(1))
            m = int(dmy_match.group(2))
            y = int(dmy_match.group(3))
            return date(y, m, d)
        except ValueError:
            return None

    # 4. Short DD/MM/YY (e.g. 15/11/26 -> 2026-11-15)
    dmy2_match = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})$", date_str)
    if dmy2_match:
        try:
            d = int(dmy2_match.group(1))
            m = int(dmy2_match.group(2))
            y = 2000 + int(dmy2_match.group(3))
            return date(y, m, d)
        except ValueError:
            return None

    # 5. Relative DD/MM (e.g. 15/11 or 06/12) -> next occurrence on or after report_date
    dm_match = re.match(r"^(\d{1,2})[/\-](\d{1,2})$", date_str)
    if dm_match:
        try:
            d = int(dm_match.group(1))
            m = int(dm_match.group(2))
            year = ref_date.year

            # Handle leap year edge case if day is 29 and month is 2
            try:
                candidate = date(year, m, d)
            except ValueError:
                # If invalid day for that year (e.g. Feb 29 in non-leap), try next leap year
                candidate = date(year + 1, m, d)

            if candidate < ref_date:
                candidate = date(year + 1, m, d)

            return candidate
        except Exception:
            return None

    return None
