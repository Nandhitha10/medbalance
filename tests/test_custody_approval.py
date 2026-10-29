"""Tests for Phase P17: Per-order approval, QR custody scanning, deviation detection, and hospital closed loop.

Verifies:
1. Per-order approve / reject workflow with audit trail and async doc generation triggers.
2. HMAC-SHA256 custody token validation and 401 rejection on invalid tokens.
3. State machine enforcement: APPROVED -> IN_TRANSIT (dispatch) -> DELIVERED (receive) -> COMPLETED (consume),
   with 400 Bad Request rejection on out-of-order scans.
4. Deviation detection:
   - Quantity mismatch: qty received != dispatched -> records qty_mismatch.
   - Temperature excursion: cold chain reading > 8.0°C or < 2.0°C -> records temperature_excursion and quarantines lot.
   - Late arrival: scan timestamp > ETA + 1 day -> records late_arrival.
5. Auto-scan execution: automated dispatch -> transit -> receive loop.
6. Admin tamper demo and restore:
   - Tamper demo mutates an audit payload; GET /audit/verify fails.
   - Restore demo returns original payload; GET /audit/verify passes.
7. Closed-loop acceptance with simulated hospitals:
   - Approval and physical dispatch decrements source hospital /state inventory.
   - Physical receive increments destination hospital /state inventory.
   - Custody timeline records complete trail and audit chain remains verified.
"""

import asyncio
from datetime import date, datetime, timedelta
import os
import sys
from typing import Any, Dict
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Ensure microservices are importable
core_api_path = os.path.abspath("services/core-api")
sim_hosp_path = os.path.abspath("services/sim-hospital")
if core_api_path not in sys.path:
    sys.path.insert(0, core_api_path)
if sim_hosp_path not in sys.path:
    sys.path.append(sim_hosp_path)

import medbal_common.db as common_db
from medbal_common.audit import AuditLog, verify as verify_audit_chain
from medbal_common.clock import KOLKATA_TZ, now as sim_now
from src.db_models import (
    Base,
    CustodyEventModel,
    DrugModel,
    FacilityModel,
    LotModel,
    RouteModel,
    TransferOrderModel,
)
from src.main import build_app as build_core_app
from src.routers.custody import HOSPITAL_URLS, execute_auto_scan
from src.routers.plans import generate_qr_token


from sqlalchemy.pool import StaticPool

@pytest.fixture(scope="module")
def sqlite_engine():
    """Create in-memory SQLite database for core-api test isolation."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    AuditLog.__table__.create(engine, checkfirst=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def setup_db(sqlite_engine, monkeypatch):
    """Point medbal_common.db to the in-memory SQLite engine and seed master data."""
    factory = sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(common_db, "_default_engine", sqlite_engine)
    monkeypatch.setattr(common_db, "_default_session_factory", factory)
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("DTA_HMAC_SECRET", "test_secret_key_2026")

    # Clear tables and seed minimal master data
    with common_db.session_scope() as session:
        session.query(CustodyEventModel).delete()
        session.query(TransferOrderModel).delete()
        session.query(LotModel).delete()
        session.query(AuditLog).delete()
        session.query(RouteModel).delete()
        session.query(DrugModel).delete()
        session.query(FacilityModel).delete()

        # Seed facilities
        h1 = FacilityModel(
            id="H1",
            code="H1",
            name="District Hospital 1",
            level="DH",
            taluk="Bengaluru North",
            latitude=12.9716,
            longitude=77.5946,
            adapter_type="fhir",
            cold_storage_ok=True,
        )
        h2 = FacilityModel(
            id="H2",
            code="H2",
            name="Taluk Hospital 2",
            level="TH",
            taluk="Yelahanka",
            latitude=13.1007,
            longitude=77.5963,
            adapter_type="csv",
            cold_storage_ok=True,
        )
        session.add_all([h1, h2])

        # Seed drugs
        ins = DrugModel(code="INS-REG", name="Regular Insulin", category="V", unit="vial", cold_chain=True, unit_cost_inr=150.0)
        pcm = DrugModel(code="PCM-500", name="Paracetamol 500mg", category="E", unit="tablet", cold_chain=False, unit_cost_inr=1.5)
        session.add_all([ins, pcm])

        # Seed route
        route = RouteModel(id="R-H1-H2", source_id="H1", destination_id="H2", distance_km=25.0, transit_hours=2.0)
        session.add(route)


@pytest.fixture
def core_client():
    """Async HTTP client for core-api."""
    app = build_core_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ==============================================================================
# 1. Per-Order Approval & Rejection Workflow
# ==============================================================================

@pytest.mark.asyncio
async def test_order_approve_and_audit(core_client: AsyncClient):
    """Approving an order sets status to APPROVED, records audit entry, and sets HMAC qr_token."""
    order_id = "DTA/BLR-U/2026/000101"
    now_ts = sim_now()

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="INS-REG",
            batch_no="BAT-INS-01",
            quantity=50,
            usable_quantity=50,
            status="DRAFT",
            temperature_controlled=True,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Approve order
    resp = await core_client.post(f"/orders/{order_id}/approve?actor=dr_sharma")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "APPROVED"
    assert data["approved_by"] == "dr_sharma"
    assert data["qr_token"] == generate_qr_token(order_id)
    assert data["audit_hash"] is not None

    # Check audit log
    with common_db.session_scope() as session:
        verify = verify_audit_chain(session)
        assert verify["ok"] is True
        assert verify["entries"] >= 1

        audit_entry = session.execute(
            select(AuditLog).where(AuditLog.entity_id == order_id, AuditLog.action == "approve_order")
        ).scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.actor == "dr_sharma"
        assert audit_entry.payload["new_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_order_reject_and_audit(core_client: AsyncClient):
    """Rejecting an order sets status to CANCELLED with audit logging."""
    order_id = "DTA/BLR-U/2026/000102"
    now_ts = sim_now()

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-01",
            quantity=100,
            usable_quantity=100,
            status="DRAFT",
            temperature_controlled=False,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    resp = await core_client.post(
        f"/orders/{order_id}/reject?actor=dr_sharma",
        json={"reason": "Hospital H2 has sufficient safety stock"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "CANCELLED"

    with common_db.session_scope() as session:
        verify = verify_audit_chain(session)
        assert verify["ok"] is True


# ==============================================================================
# 2. HMAC-SHA256 Token Verification & Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_custody_hmac_verification(core_client: AsyncClient):
    """Scan requires valid HMAC-SHA256 token matching the order, else 401 Unauthorized."""
    order_id = "DTA/BLR-U/2026/000201"
    now_ts = sim_now()
    valid_token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="INS-REG",
            batch_no="BAT-INS-02",
            quantity=30,
            status="APPROVED",
            qr_token=valid_token,
            temperature_controlled=True,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # 1. Invalid token should return 401
    bad_resp = await core_client.post(
        "/custody/scan",
        json={
            "token": "invalid_forged_hmac_token_123456",
            "event": "dispatch",
            "qty": 30,
            "actor": "driver_ravi",
            "order_id": order_id,
        },
    )
    assert bad_resp.status_code == 401
    assert "Invalid HMAC" in bad_resp.json()["detail"]

    # 2. Valid token should succeed
    good_resp = await core_client.post(
        "/custody/scan",
        json={
            "token": valid_token,
            "event": "dispatch",
            "qty": 30,
            "actor": "driver_ravi",
            "location": "H1 Cold Storage Bay",
            "order_id": order_id,
        },
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["status"] == "recorded"
    assert good_resp.json()["order_status"] == "IN_TRANSIT"


# ==============================================================================
# 3. State Machine Order Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_custody_state_machine_enforcement(core_client: AsyncClient):
    """Enforces strict state order: APPROVED -> IN_TRANSIT -> DELIVERED -> COMPLETED."""
    order_id = "DTA/BLR-U/2026/000301"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-03",
            quantity=40,
            status="DRAFT",  # starts in DRAFT
            qr_token=token,
            temperature_controlled=False,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # 1. Cannot dispatch DRAFT order (must be APPROVED)
    res_draft_dispatch = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 40, "actor": "driver_ravi", "order_id": order_id},
    )
    assert res_draft_dispatch.status_code == 400
    assert "must be in APPROVED state" in res_draft_dispatch.json()["detail"]

    # Approve the order
    await core_client.post(f"/orders/{order_id}/approve?actor=dr_sharma")

    # 2. Cannot receive order before dispatch
    res_premature_receive = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "receive", "qty": 40, "actor": "nurse_deepa", "order_id": order_id},
    )
    assert res_premature_receive.status_code == 400
    assert "must be in IN_TRANSIT state" in res_premature_receive.json()["detail"]

    # 3. Valid dispatch -> status becomes IN_TRANSIT
    res_dispatch = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 40, "actor": "driver_ravi", "order_id": order_id},
    )
    assert res_dispatch.status_code == 200
    assert res_dispatch.json()["order_status"] == "IN_TRANSIT"

    # 4. Cannot dispatch again while IN_TRANSIT
    res_re_dispatch = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 40, "actor": "driver_ravi", "order_id": order_id},
    )
    assert res_re_dispatch.status_code == 400

    # 5. Cannot consume while IN_TRANSIT
    res_premature_consume = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "consume", "qty": 40, "actor": "nurse_deepa", "order_id": order_id},
    )
    assert res_premature_consume.status_code == 400

    # 6. Valid receive -> status becomes DELIVERED
    res_receive = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "receive", "qty": 40, "actor": "pharmacist_h2", "order_id": order_id},
    )
    assert res_receive.status_code == 200
    assert res_receive.json()["order_status"] == "DELIVERED"

    # 7. Valid consume -> status becomes COMPLETED
    res_consume = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "consume", "qty": 40, "actor": "nurse_deepa", "order_id": order_id},
    )
    assert res_consume.status_code == 200
    assert res_consume.json()["order_status"] == "COMPLETED"


# ==============================================================================
# 4. Deviation Detection
# ==============================================================================

@pytest.mark.asyncio
async def test_deviation_quantity_mismatch(core_client: AsyncClient):
    """Quantity mismatch (received != dispatched) is recorded in custody_event.deviation."""
    order_id = "DTA/BLR-U/2026/000401"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-04",
            quantity=50,
            status="APPROVED",
            qr_token=token,
            temperature_controlled=False,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Dispatch full 50
    await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 50, "actor": "driver_ravi", "order_id": order_id},
    )

    # Receive 42 (shortage of 8)
    rec_resp = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "receive", "qty": 42, "actor": "pharmacist_h2", "order_id": order_id},
    )
    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["deviation"] is not None
    assert "qty_mismatch" in data["deviation"]
    qm = data["deviation"]["qty_mismatch"]
    assert qm["dispatched"] == 50
    assert qm["received"] == 42
    assert qm["diff"] == -8
    assert "Quantity mismatch" in data["notes"]


@pytest.mark.asyncio
async def test_deviation_temperature_excursion_quarantines_lot(core_client: AsyncClient):
    """Cold-chain temperature excursion (>8.0°C) records deviation and sets destination lot status to quarantined."""
    order_id = "DTA/BLR-U/2026/000402"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        # Source lot at H1
        src_lot = LotModel(
            facility_id="H1",
            drug_code="INS-REG",
            batch_no="BAT-INS-EXCURSION",
            expiry=date(2026, 12, 31),
            quantity=60,
            status="active",
            created_at=now_ts,
        )
        session.add(src_lot)

        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="INS-REG",
            batch_no="BAT-INS-EXCURSION",
            quantity=30,
            status="APPROVED",
            qr_token=token,
            temperature_controlled=True,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Dispatch at safe temperature 4.2°C
    await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 30, "actor": "driver_ravi", "temperature_c": 4.2, "order_id": order_id},
    )

    # Receive with critical excursion: 11.5°C
    rec_resp = await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "receive", "qty": 30, "actor": "pharmacist_h2", "temperature_c": 11.5, "order_id": order_id},
    )
    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["deviation"] is not None
    assert "temperature_excursion" in data["deviation"]
    te = data["deviation"]["temperature_excursion"]
    assert te["temperature_c"] == 11.5
    assert te["excursion_type"] == "OVERHEAT"
    assert "Cold-chain excursion" in data["notes"]

    # Verify destination lot in core-api DB is marked 'quarantined'
    with common_db.session_scope() as session:
        dest_lot = session.execute(
            select(LotModel).where(
                LotModel.facility_id == "H2",
                LotModel.drug_code == "INS-REG",
                LotModel.batch_no == "BAT-INS-EXCURSION",
            )
        ).scalar_one_or_none()
        assert dest_lot is not None
        assert dest_lot.quantity == 30
        assert dest_lot.status == "quarantined"


@pytest.mark.asyncio
async def test_deviation_late_arrival(core_client: AsyncClient):
    """Arrival later than ETA + 1 day records late_arrival deviation."""
    order_id = "DTA/BLR-U/2026/000403"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-LATE",
            quantity=20,
            status="APPROVED",
            qr_token=token,
            temperature_controlled=False,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Dispatch now
    await core_client.post(
        "/custody/scan",
        json={"token": token, "event": "dispatch", "qty": 20, "actor": "driver_ravi", "order_id": order_id},
    )

    # Receive 3 days later (> ETA 2h + 24h deadline)
    late_ts = (now_ts + timedelta(days=3)).isoformat()
    rec_resp = await core_client.post(
        "/custody/scan",
        json={
            "token": token,
            "event": "receive",
            "qty": 20,
            "actor": "pharmacist_h2",
            "timestamp": late_ts,
            "order_id": order_id,
        },
    )
    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["deviation"] is not None
    assert "late_arrival" in data["deviation"]
    assert data["deviation"]["late_arrival"]["delay_hours"] > 24.0
    assert "Late arrival" in data["notes"]


# ==============================================================================
# 5. Automated Scan Execution
# ==============================================================================

@pytest.mark.asyncio
async def test_auto_scan_approved_order(core_client: AsyncClient):
    """Auto-scan flows approved order from dispatch -> transit delay -> receive."""
    order_id = "DTA/BLR-U/2026/000501"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-AUTO",
            quantity=35,
            status="APPROVED",
            qr_token=token,
            temperature_controlled=False,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Execute auto-scan endpoint
    resp = await core_client.post(f"/custody/auto-scan/{order_id}?transit_delay_sec=0.05")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["dispatch_event_id"] is not None
    assert data["receive_event_id"] is not None

    # Check custody trail has both DISPATCH and RECEIVE
    trail_resp = await core_client.get(f"/custody/{order_id}")
    assert trail_resp.status_code == 200
    trail = trail_resp.json()
    assert len(trail) == 2
    assert trail[0]["event_type"] == "DISPATCH"
    assert trail[1]["event_type"] == "RECEIVE"

    # Order status is DELIVERED
    ord_resp = await core_client.get(f"/orders/{order_id}")
    assert ord_resp.status_code == 200
    assert ord_resp.json()["status"] == "DELIVERED"


# ==============================================================================
# 6. Admin Tamper Demo & Restore Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_admin_tamper_demo_and_restore(core_client: AsyncClient):
    """POST /admin/tamper-demo mutates audit row; verify fails. Restore demo returns ok=True."""
    # 0. Ensure an audit entry exists
    order_id = "DTA/BLR-U/2026/000777"
    now_ts = sim_now()
    with common_db.session_scope() as session:
        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="PCM-500",
            batch_no="BAT-PCM-TAMPER",
            quantity=10,
            status="DRAFT",
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)
    await core_client.post(f"/orders/{order_id}/approve?actor=dr_sharma")

    # 1. Ensure initial audit integrity is green
    ver_init = await core_client.get("/audit/verify")
    assert ver_init.status_code == 200
    assert ver_init.json()["ok"] is True

    # 2. Tamper with latest row
    tamper_resp = await core_client.post("/admin/tamper-demo")
    assert tamper_resp.status_code == 200
    tamper_data = tamper_resp.json()
    assert tamper_data["status"] == "tampered"
    assert tamper_data["verification"]["ok"] is False
    assert tamper_data["verification"]["first_bad_seq"] == tamper_data["tampered_seq"]

    # 3. Direct verify endpoint reflects tamper
    ver_fail = await core_client.get("/audit/verify")
    assert ver_fail.status_code == 200
    assert ver_fail.json()["ok"] is False

    # 4. Restore original payload
    restore_resp = await core_client.post("/admin/restore-demo")
    assert restore_resp.status_code == 200
    restore_data = restore_resp.json()
    assert restore_data["status"] == "restored"
    assert restore_data["verification"]["ok"] is True
    assert restore_data["verification"]["first_bad_seq"] is None

    # 5. Direct verify endpoint reflects clean integrity
    ver_pass = await core_client.get("/audit/verify")
    assert ver_pass.status_code == 200
    assert ver_pass.json()["ok"] is True


# ==============================================================================
# 7. Closed-Loop Acceptance with Simulated Hospitals
# ==============================================================================

@pytest.mark.asyncio
async def test_closed_loop_hospital_transfer_loop(core_client: AsyncClient, monkeypatch):
    """End-to-end acceptance:
    Approve order -> dispatch & receive -> both hospitals' stock reflects the move,
    custody timeline shows dispatch and receive, audit verify ok.
    """
    from sim_hospital.hospital import HospitalNode

    # Setup 2 simulated hospital nodes (H1 and H2)
    h1_node = HospitalNode(hospital_id="H1")
    h2_node = HospitalNode(hospital_id="H2")

    # Seed stock in H1
    h1_node.db.record_inbound_transfer(
        order_id="INIT-H1",
        drug_code="INS-REG",
        batch_no="BAT-INS-LOOP",
        expiry_str="2026-12-31",
        quantity=100,
        timestamp_str=sim_now().isoformat(),
    )

    # Initial states
    h1_init_stock = next((item["quantity"] for item in h1_node.get_state()["inventory"] if item["batch_no"] == "BAT-INS-LOOP"), 0)
    h2_init_stock = next((item["quantity"] for item in h2_node.get_state()["inventory"] if item["batch_no"] == "BAT-INS-LOOP"), 0)
    assert h1_init_stock == 100
    assert h2_init_stock == 0

    # Mock _call_hospital_transfer in custody.py to route directly to h1_node / h2_node
    async def mock_call_hospital(facility_id: str, endpoint: str, payload: Dict[str, Any]) -> None:
        ts = sim_now().isoformat()
        if facility_id == "H1" and endpoint == "/transfers/outbound":
            h1_node.db.record_outbound_transfer(
                order_id=payload["order_id"],
                drug_code=payload["drug_code"],
                batch_no=payload["batch_no"],
                quantity=payload["quantity"],
                timestamp_str=ts,
            )
        elif facility_id == "H2" and endpoint == "/transfers/inbound":
            h2_node.db.record_inbound_transfer(
                order_id=payload["order_id"],
                drug_code=payload["drug_code"],
                batch_no=payload["batch_no"],
                expiry_str=payload.get("expiry", "2026-12-31"),
                quantity=payload["quantity"],
                timestamp_str=ts,
            )

    monkeypatch.setattr("src.routers.custody._call_hospital_transfer", mock_call_hospital)

    # Setup transfer order for 25 units
    order_id = "DTA/BLR-U/2026/000999"
    now_ts = sim_now()
    token = generate_qr_token(order_id)

    with common_db.session_scope() as session:
        # Seed core-api source lot
        src_lot = LotModel(
            facility_id="H1",
            drug_code="INS-REG",
            batch_no="BAT-INS-LOOP",
            expiry=date(2026, 12, 31),
            quantity=100,
            status="active",
            created_at=now_ts,
        )
        session.add(src_lot)

        order = TransferOrderModel(
            id=order_id,
            source_facility_id="H1",
            destination_facility_id="H2",
            drug_code="INS-REG",
            batch_no="BAT-INS-LOOP",
            quantity=25,
            status="DRAFT",
            temperature_controlled=True,
            created_at=now_ts,
            updated_at=now_ts,
        )
        session.add(order)

    # Step 1: Approve order
    appr_resp = await core_client.post(f"/orders/{order_id}/approve?actor=dr_sharma")
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "APPROVED"

    # Step 2: Auto-scan dispatch & receive
    scan_resp = await core_client.post(f"/custody/auto-scan/{order_id}?transit_delay_sec=0.01")
    assert scan_resp.status_code == 200
    assert scan_resp.json()["status"] == "completed"

    # Step 3: Verify both hospitals' /state reflect the physical stock move
    h1_final_stock = next((item["quantity"] for item in h1_node.get_state()["inventory"] if item["batch_no"] == "BAT-INS-LOOP"), 0)
    h2_final_stock = next((item["quantity"] for item in h2_node.get_state()["inventory"] if item["batch_no"] == "BAT-INS-LOOP"), 0)
    assert h1_final_stock == 75, f"Expected H1 stock to decrement from 100 to 75, got {h1_final_stock}"
    assert h2_final_stock == 25, f"Expected H2 stock to increment from 0 to 25, got {h2_final_stock}"

    # Step 4: Verify custody timeline shows both dispatch and receive
    trail_resp = await core_client.get(f"/custody/{order_id}")
    assert trail_resp.status_code == 200
    events = trail_resp.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "DISPATCH"
    assert events[1]["event_type"] == "RECEIVE"
    assert events[0]["signature_hash"] == token
    assert events[1]["signature_hash"] == token

    # Step 5: Verify SHA-256 audit chain integrity is green
    verify_resp = await core_client.get("/audit/verify")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["ok"] is True
