"""Tests for date resolution and unit conversion utilities."""

from datetime import date
from ingest_ai.date_utils import parse_mmyyyy_to_last_day, resolve_clinical_date
from ingest_ai.unit_utils import normalize_quantity_and_unit


def test_parse_mmyyyy_to_last_day():
    # November 2026 has 30 days
    assert parse_mmyyyy_to_last_day("11/2026") == date(2026, 11, 30)
    # February 2028 is a leap year (29 days)
    assert parse_mmyyyy_to_last_day("02/2028") == date(2028, 2, 29)
    # February 2027 has 28 days
    assert parse_mmyyyy_to_last_day("02/2027") == date(2027, 2, 28)
    # With hyphen
    assert parse_mmyyyy_to_last_day("12-2026") == date(2026, 12, 31)


def test_resolve_clinical_date():
    ref_date = date(2026, 11, 1)

    # 1. ISO format
    assert resolve_clinical_date("2026-11-21", ref_date) == date(2026, 11, 21)

    # 2. MM/YYYY
    assert resolve_clinical_date("11/2026", ref_date) == date(2026, 11, 30)

    # 3. Full DD/MM/YYYY
    assert resolve_clinical_date("14/08/1999", ref_date) == date(1999, 8, 14)
    assert resolve_clinical_date("21/11/2026", ref_date) == date(2026, 11, 21)

    # 4. Short DD/MM/YY
    assert resolve_clinical_date("15/11/26", ref_date) == date(2026, 11, 15)

    # 5. Relative DD/MM
    # 15/11 relative to 2026-11-01 -> 2026-11-15 (same month)
    assert resolve_clinical_date("15/11", ref_date) == date(2026, 11, 15)
    # 15/10 relative to 2026-11-01 -> 2027-10-15 (past date in current year resolves to next year)
    assert resolve_clinical_date("15/10", ref_date) == date(2027, 10, 15)


def test_normalize_quantity_and_unit():
    # 10 strips of Paracetamol (pack_size=10) = 100 tablets
    qty, unit = normalize_quantity_and_unit(10, "strip", pack_size=10)
    assert qty == 100
    assert unit == "tablet"

    # 5 strips of IFA-W (pack_size=100) = 500 tablets
    qty_ifa, unit_ifa = normalize_quantity_and_unit(5, "strips", pack_size=100)
    assert qty_ifa == 500
    assert unit_ifa == "tablet"

    # Vials remain 1:1
    qty_vial, unit_vial = normalize_quantity_and_unit(50, "vials", pack_size=1)
    assert qty_vial == 50
    assert unit_vial == "vial"

    # Sachets remain 1:1
    qty_ors, unit_ors = normalize_quantity_and_unit(15, "pkt", pack_size=1)
    assert qty_ors == 15
    assert unit_ors == "sachet"
