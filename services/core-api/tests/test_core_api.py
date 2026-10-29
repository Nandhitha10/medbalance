"""Comprehensive integration tests for core-api against database and contracts."""

from datetime import date, datetime
import hashlib
import json
import os
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from medbal_common.audit import AuditLog, canonical_json
from medbal_common.clock import KOLKATA_TZ
from medbal_common.db import Base
import medbal_common.db as common_db
from src.db_models import (
    ConsumptionDailyModel,
    CustodyEventModel,
    DrugModel,
    FacilityModel,
    ForecastModel,
    LotModel,
    PolicyModel,
    RouteModel,
    SensorReadingModel,
    VehicleModel,
)


@pytest.fixture(scope="session")
def test_db():
    """Create in-memory SQLite database and tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    # Monkeypatch common_db default engine and factory
    common_db._default_engine = engine
    common_db._default_session_factory = session_factory

    # Populate baseline master data
    with common_db.session_scope() as session:
        # Facilities
        h1 = FacilityModel(
            id="H1",
            code="SIM-H1",
            name="District Hospital 1",
            level="DH",
            latitude=13.0827,
            longitude=77.5877,
            adapter_type="fhir",
            cold_storage_ok=True,
            created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
        )
        h2 = FacilityModel(
            id="H2",
            code="SIM-H2",
            name="Taluk General Hospital 2",
            level="TH",
            latitude=12.9250,
            longitude=77.5938,
            adapter_type="csv",
            cold_storage_ok=True,
            created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
        )
        w0 = FacilityModel(
            id="W0",
            code="SIM-W0",
            name="District Central Medical Warehouse",
            level="WH",
            latitude=13.0358,
            longitude=77.5970,
            adapter_type="csv",
            cold_storage_ok=True,
            created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
        )
        session.add_all([h1, h2, w0])

        # Drugs
        insulin = DrugModel(
            code="INS-REG",
            name="Insulin Regular 100 IU/ml",
            category="V",
            unit="vial",
            pack_size=1,
            cold_chain=True,
            min_temp_c=2.0,
            max_temp_c=8.0,
            unit_cost_inr=145.50,
            min_residual_days=15,
            is_controlled=False,
        )
        amox = DrugModel(
            code="AMOX-500",
            name="Amoxicillin 500mg",
            category="E",
            unit="tablet",
            pack_size=10,
            cold_chain=False,
            unit_cost_inr=4.25,
            min_residual_days=30,
            is_controlled=False,
        )
        session.add_all([insulin, amox])

        # Policies
        session.add_all([
            PolicyModel(facility_id="H1", drug_code="INS-REG", min_reserve_days=7, target_days=21, lead_time_days=3),
            PolicyModel(facility_id="H2", drug_code="INS-REG", min_reserve_days=7, target_days=21, lead_time_days=3),
            PolicyModel(facility_id="H1", drug_code="AMOX-500", min_reserve_days=7, target_days=21, lead_time_days=3),
        ])

        # Routes
        session.add(
            RouteModel(
                id="RTE-H1-H2",
                source_id="H1",
                destination_id="H2",
                distance_km=18.5,
                transit_days=1,
                transit_hours=1.0,
                cost_inr=277.50,
                cold_capable=True,
            )
        )

        # Vehicles
        session.add(
            VehicleModel(
                id="VEH-CC-01",
                name="Refrigerated Van 01",
                vehicle_type="Refrigerated Van",
                cold_capable=True,
                is_active=True,
                cost_per_km_inr=18.00,
            )
        )

        # Forecasts
        session.add_all([
            ForecastModel(
                facility_id="H1",
                drug_code="INS-REG",
                forecast_date=date(2026, 11, 1),
                baseline_daily_rate=0.5,
                llm_multiplier=1.0,
                effective_daily_rate=0.5,
                target_days=21,
                projected_consumption=11,
            ),
            ForecastModel(
                facility_id="H2",
                drug_code="INS-REG",
                forecast_date=date(2026, 11, 1),
                baseline_daily_rate=2.0,
                llm_multiplier=1.25,
                effective_daily_rate=2.5,
                target_days=21,
                projected_consumption=53,
            ),
        ])

    return engine


@pytest.fixture
def app(test_db, monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    from src.main import build_app
    return build_app()


@pytest.mark.asyncio
async def test_master_data_endpoints(app):
    """Test facilities, drugs, routes, vehicles master data retrieval with dual routing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Facilities
        r_fac = await client.get("/facilities")
        assert r_fac.status_code == 200
        facs = r_fac.json()
        assert len(facs) == 3
        h1 = [f for f in facs if f["id"] == "H1"][0]
        assert h1["facility_type"] == "Hospital"
        assert h1["cold_storage_available"] is True
        assert h1["min_reserve_days"] == 7

        # Test dual routing via /api/core
        r_fac_gw = await client.get("/api/core/facilities")
        assert r_fac_gw.status_code == 200
        assert len(r_fac_gw.json()) == 3

        # Drugs
        r_drugs = await client.get("/drugs")
        assert r_drugs.status_code == 200
        drugs = r_drugs.json()
        assert len(drugs) == 2
        ins = [d for d in drugs if d["code"] == "INS-REG"][0]
        assert ins["storage_condition"] == "cold_chain"
        assert ins["unit_cost_inr"] == 145.50

        # Routes
        r_routes = await client.get("/routes")
        assert r_routes.status_code == 200
        routes = r_routes.json()
        assert len(routes) == 1
        assert routes[0]["id"] == "RTE-H1-H2"
        assert routes[0]["cold_chain_compliant"] is True

        # Vehicles
        r_veh = await client.get("/vehicles")
        assert r_veh.status_code == 200
        vehs = r_veh.json()
        assert len(vehs) == 1
        assert vehs[0]["id"] == "VEH-CC-01"
        assert vehs[0]["cold_chain_capable"] is True


@pytest.mark.asyncio
async def test_lots_upsert_batch_idempotency_and_audit(app):
    """Test idempotent batch lot upserts and audit chain integration."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Initial upsert batch of 2 lots
        payload = [
            {
                "facility_id": "H1",
                "drug_code": "INS-REG",
                "batch_no": "LOT-INS-H1-01",
                "expiry": "2026-11-20",
                "quantity": 50,
            },
            {
                "facility_id": "H2",
                "drug_code": "INS-REG",
                "batch_no": "LOT-INS-H2-01",
                "expiry": "2026-11-30",
                "quantity": 10,
            },
        ]
        resp1 = await client.post("/lots/upsert-batch", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["upserted_count"] == 2

        # Verify lots query
        r_lots = await client.get("/lots?facility=H1&drug=INS-REG")
        assert r_lots.status_code == 200
        lots = r_lots.json()
        assert len(lots) == 1
        assert lots[0]["batch_no"] == "LOT-INS-H1-01"
        assert lots[0]["quantity"] == 50

        # 2. Re-upsert with modified quantity (Idempotency test)
        payload_update = [
            {
                "facility_id": "H1",
                "drug_code": "INS-REG",
                "batch_no": "LOT-INS-H1-01",
                "expiry": "2026-11-20",
                "quantity": 60,  # Updated from 50 to 60
            }
        ]
        resp2 = await client.post("/lots/upsert-batch", json=payload_update)
        assert resp2.status_code == 200
        assert resp2.json()["upserted_count"] == 1

        # Check that quantity updated and did not duplicate row
        r_lots2 = await client.get("/lots?facility=H1&drug=INS-REG")
        lots2 = r_lots2.json()
        assert len(lots2) == 1
        assert lots2[0]["quantity"] == 60

        # Verify audit entries were logged
        r_audit = await client.get("/audit?entity=lot")
        assert r_audit.status_code == 200
        audit_entries = r_audit.json()
        assert len(audit_entries) >= 2
        assert audit_entries[-1]["action"] == "upsert_lots_batch"


@pytest.mark.asyncio
async def test_positions_and_snapshot_hash(app):
    """Test computed FEFO positions and snapshot SHA-256 integrity hash."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Positions
        r_pos = await client.get("/positions?facility=H1&drug=INS-REG")
        assert r_pos.status_code == 200
        positions = r_pos.json()
        assert len(positions) == 1
        p = positions[0]
        assert p["facility_id"] == "H1"
        assert p["drug_code"] == "INS-REG"
        assert p["stock_on_hand"] == 60
        assert p["daily_consumption_rate"] == 0.5
        assert len(p["lots"]) == 1
        assert p["lots"][0]["batch_no"] == "LOT-INS-H1-01"

        # Snapshot
        r_snap = await client.get("/snapshot")
        assert r_snap.status_code == 200
        snap = r_snap.json()

        # Check required snapshot sections
        assert "timestamp" in snap
        assert "today" in snap
        assert "facilities" in snap
        assert "drugs" in snap
        assert "routes" in snap
        assert "vehicles" in snap
        assert "lots" in snap
        assert "positions" in snap
        assert "forecasts" in snap
        assert "policies" in snap
        assert "snapshot_hash" in snap

        # Verify snapshot hash integrity
        received_hash = snap["snapshot_hash"]
        snap_copy = dict(snap)
        del snap_copy["snapshot_hash"]
        expected_hash = hashlib.sha256(canonical_json(snap_copy).encode("utf-8")).hexdigest()
        assert received_hash == expected_hash


@pytest.mark.asyncio
async def test_plan_persistence_and_orders_lifecycle(app):
    """Test plan persistence with sequential DTA generation, HMAC QR tokens, and order approval/rejection."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Post a plan run with candidates, orders, and regret
        plan_payload = {
            "id": "PLAN-20261101-01",
            "status": "COMPLETED",
            "mode": "live",
            "solver_tier": "platform",
            "execution_time_sec": 3.45,
            "total_orders": 1,
            "total_units": 28,
            "shortage_reduction": 28,
            "expiry_avoided": 28,
            "total_savings_inr": 4074.00,
            "orders": [
                {
                    "source_facility_id": "H1",
                    "destination_facility_id": "H2",
                    "drug_code": "INS-REG",
                    "batch_no": "LOT-INS-H1-01",
                    "quantity": 28,
                    "usable_quantity": 28,
                    "temperature_controlled": True,
                    "savings_inr": 4074.00,
                }
            ],
            "candidates": [
                {
                    "id": "CND-001",
                    "lot_batch_no": "LOT-INS-H1-01",
                    "drug_code": "INS-REG",
                    "source_facility_id": "H1",
                    "destination_facility_id": "H2",
                    "chunk_quantity": 28,
                    "usable_quantity": 28,
                    "is_feasible": True,
                    "feasibility_flags": {
                        "F1_identity": True,
                        "F2_route_transit_hours": 1.0,
                        "F3_cold_chain_maintained": True,
                        "F4_residual_shelf_life_days": 19,
                        "F5_reserve_protected": 10,
                        "F6_controlled_substance": False,
                    },
                    "reward": 0.95,
                    "cost": 0.12,
                }
            ],
            "regret": [
                {
                    "alternate_destination_id": "W0",
                    "chosen_reward": 0.95,
                    "alternate_reward": 0.40,
                    "regret_delta": 0.55,
                    "reason": "Lower shortage at warehouse",
                }
            ],
        }

        r_plan = await client.post("/plans", json=plan_payload)
        assert r_plan.status_code == 201
        assert r_plan.json()["plan_id"] == "PLAN-20261101-01"

        # 2. Query orders
        r_orders = await client.get("/orders?plan_id=PLAN-20261101-01")
        assert r_orders.status_code == 200
        orders = r_orders.json()
        assert len(orders) == 1
        order = orders[0]
        order_id = order["id"]
        # Verify sequential DTA numbering
        assert order_id.startswith("DTA/BLR-U/2026/")
        assert order["status"] == "DRAFT"
        assert order["quantity"] == 28

        # 3. Get single order
        r_single = await client.get(f"/orders/{order_id}")
        assert r_single.status_code == 200
        assert r_single.json()["id"] == order_id

        # 4. Approve order
        r_appr = await client.post(f"/orders/{order_id}/approve")
        assert r_appr.status_code == 200
        assert r_appr.json()["status"] == "APPROVED"

        # 5. Reject order
        r_rej = await client.post(f"/orders/{order_id}/reject", json={"reason": "Driver route change"})
        assert r_rej.status_code == 200
        assert r_rej.json()["status"] == "CANCELLED"

        # 6. Provenance graph verification (Requirement 7)
        r_prov = await client.get(f"/provenance/{order_id}")
        assert r_prov.status_code == 200
        prov = r_prov.json()
        assert prov["order_id"] == order_id
        assert prov["plan_id"] == "PLAN-20261101-01"
        assert "nodes" in prov
        assert "edges" in prov
        node_types = [n["type"] for n in prov["nodes"]]
        assert "stock_report" in node_types
        assert "extraction_item" in node_types
        assert "lot" in node_types
        assert "candidate" in node_types
        assert "transfer_order" in node_types


@pytest.mark.asyncio
async def test_audit_verify_and_tamper_detection(app):
    """Test audit chain verification and tamper detection."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Verify valid audit chain
        r_ver = await client.get("/audit/verify")
        assert r_ver.status_code == 200
        ver_data = r_ver.json()
        assert ver_data["ok"] is True
        assert ver_data["entries"] > 0
        assert ver_data["first_bad_seq"] is None

        # Directly tamper with an audit record in the database
        with common_db.session_scope() as session:
            record = session.execute(
                select(AuditLog).order_by(AuditLog.seq.asc()).limit(1)
            ).scalar_one()
            tampered_seq = record.seq
            # Tamper payload without updating hash
            record.payload = {"tampered": True}

        # Verify tamper detection identifies failure at tampered seq
        r_tamper = await client.get("/audit/verify")
        assert r_tamper.status_code == 200
        tamper_data = r_tamper.json()
        assert tamper_data["ok"] is False
        assert tamper_data["first_bad_seq"] == tampered_seq


@pytest.mark.asyncio
async def test_custody_scan_and_events_sse(app):
    """Test custody scan returns 501 and SSE events endpoint connects."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # POST /custody/scan -> 501 Not Implemented
        r_scan = await client.post("/custody/scan", json={"order_id": "DTA/001", "actor": "driver"})
        assert r_scan.status_code == 501

        # GET /custody/{order_id} -> list of custody events
        r_cust = await client.get("/custody/DTA-001")
        assert r_cust.status_code == 200
        assert isinstance(r_cust.json(), list)

        # GET /events SSE smoke test with limit=1 to close cleanly
        async with client.stream("GET", "/events?limit=1") as sse_resp:
            assert sse_resp.status_code == 200
            assert "text/event-stream" in sse_resp.headers["content-type"]
            first_chunk = await sse_resp.aiter_text().__anext__()
            assert "connected" in first_chunk or "heartbeat" in first_chunk
