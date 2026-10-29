"""Tests for shared Pydantic data models."""

from datetime import date, datetime, timezone
import pytest
from pydantic import ValidationError

from medbal_common.models import (
    Drug,
    Facility,
    Lot,
    Position,
    Route,
    TransferOrder,
    Vehicle,
)


def test_models_creation():
    facility = Facility(
        id="SIM-HOSP-01",
        name="District Hospital",
        facility_type="Hospital",
        cold_storage_available=True,
    )
    assert facility.id == "SIM-HOSP-01"

    drug = Drug(
        code="AMOX-500",
        name="Amoxicillin 500mg",
        category="E",
        unit="capsule",
        pack_size=10,
        storage_condition="ambient",
        min_residual_days=30,
    )
    assert drug.category == "E"

    lot = Lot(
        facility_id="SIM-HOSP-01",
        drug_code="AMOX-500",
        batch_no="B123",
        expiry=date(2027, 1, 1),
        quantity=500,
    )
    assert lot.quantity == 500

    order = TransferOrder(
        id="DTA/BLR-U/2026/000123",
        source_facility_id="SIM-HOSP-01",
        destination_facility_id="SIM-HOSP-02",
        drug_code="AMOX-500",
        batch_no="B123",
        quantity=100,
        status="DRAFT",
        created_at=datetime.now(timezone.utc),
    )
    assert order.id == "DTA/BLR-U/2026/000123"


def test_transfer_order_id_regex_validation():
    """Ensure DTA format is enforced."""
    with pytest.raises(ValidationError):
        TransferOrder(
            id="INVALID-FORMAT",
            source_facility_id="SIM-HOSP-01",
            destination_facility_id="SIM-HOSP-02",
            drug_code="AMOX-500",
            batch_no="B123",
            quantity=100,
            status="DRAFT",
            created_at=datetime.now(timezone.utc),
        )
