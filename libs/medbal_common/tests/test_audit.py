"""Tests for tamper-evident audit chain using SQLite."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from medbal_common.audit import AuditLog, append, verify
from medbal_common.db import Base


@pytest.fixture
def sqlite_session():
    """Create a temporary in-memory SQLite database and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_audit_append_and_verify_clean_chain(sqlite_session: Session):
    """Verify that an untampered audit chain passes verification."""
    # Append 3 entries
    e1 = append(
        sqlite_session,
        actor="system",
        action="FACILITY_CREATED",
        entity="Facility",
        entity_id="SIM-HOSP-01",
        payload={"name": "District Hospital 1"},
    )
    e2 = append(
        sqlite_session,
        actor="admin",
        action="LOT_INGESTED",
        entity="Lot",
        entity_id="LOT-100",
        payload={"drug_code": "AMOX-500", "qty": 1000},
    )
    e3 = append(
        sqlite_session,
        actor="optimizer",
        action="DTA_GENERATED",
        entity="TransferOrder",
        entity_id="DTA/BLR-U/2026/000001",
        payload={"from": "SIM-HOSP-01", "to": "SIM-HOSP-02", "units": 200},
    )

    res = verify(sqlite_session)
    assert res["ok"] is True
    assert res["entries"] == 3
    assert res["first_bad_seq"] is None
    assert e1.seq == 1
    assert e2.seq == 2
    assert e3.seq == 3
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash


def test_audit_verify_detects_tampered_payload(sqlite_session: Session):
    """Verify that modifying the payload of an existing row breaks chain verification."""
    append(
        sqlite_session,
        actor="user1",
        action="CREATE",
        entity="Drug",
        entity_id="D1",
        payload={"name": "Drug A"},
    )
    append(
        sqlite_session,
        actor="user2",
        action="CREATE",
        entity="Drug",
        entity_id="D2",
        payload={"name": "Drug B"},
    )
    append(
        sqlite_session,
        actor="user3",
        action="CREATE",
        entity="Drug",
        entity_id="D3",
        payload={"name": "Drug C"},
    )

    # Tamper with row 2's payload directly in DB
    row2 = sqlite_session.execute(
        select(AuditLog).where(AuditLog.seq == 2)
    ).scalar_one()
    row2.payload = {"name": "Drug B Tampered"}
    sqlite_session.flush()

    res = verify(sqlite_session)
    assert res["ok"] is False
    assert res["first_bad_seq"] == 2
    assert res["entries"] == 1  # 1 entry was verified before failure


def test_audit_verify_detects_tampered_prev_hash(sqlite_session: Session):
    """Verify that modifying prev_hash breaks chain verification."""
    append(
        sqlite_session,
        actor="user1",
        action="ACTION_A",
        entity="E",
        entity_id="1",
        payload={},
    )
    append(
        sqlite_session,
        actor="user2",
        action="ACTION_B",
        entity="E",
        entity_id="2",
        payload={},
    )

    # Tamper with row 2's prev_hash
    row2 = sqlite_session.execute(
        select(AuditLog).where(AuditLog.seq == 2)
    ).scalar_one()
    row2.prev_hash = "f" * 64
    sqlite_session.flush()

    res = verify(sqlite_session)
    assert res["ok"] is False
    assert res["first_bad_seq"] == 2


def test_audit_verify_empty_chain(sqlite_session: Session):
    """Verify that an empty table reports ok."""
    res = verify(sqlite_session)
    assert res["ok"] is True
    assert res["entries"] == 0
    assert res["first_bad_seq"] is None
