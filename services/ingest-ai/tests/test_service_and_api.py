"""Integration tests for Ingest-AI service and API endpoints."""

from datetime import date, datetime
import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from medbal_common.clock import KOLKATA_TZ
from medbal_common.db import Base
import medbal_common.db as common_db
from ingest_ai.app import app
from ingest_ai.db_models import (
    DrugAliasModel,
    DrugModel,
    ExtractionItemModel,
    FacilityModel,
    LotModel,
    StockReportModel,
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

    common_db._default_engine = engine
    common_db._default_session_factory = session_factory

    # Populate baseline facilities and drugs from seed
    import yaml

    with open("data/seed/drugs.yaml", "r", encoding="utf-8") as f:
        drugs_data = yaml.safe_load(f)

    with common_db.session_scope() as session:
        h1 = FacilityModel(
            id="H1",
            code="SIM-H1",
            name="SIM-DH Jayanagar",
            level="DH",
            latitude=12.925,
            longitude=77.593,
            adapter_type="fhir",
            cold_storage_ok=True,
            created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
        )
        h4 = FacilityModel(
            id="H4",
            code="SIM-H4",
            name="SIM-PHC Hesaraghatta",
            level="PHC",
            latitude=13.137,
            longitude=77.491,
            adapter_type="text",
            cold_storage_ok=False,
            created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
        )
        session.add_all([h1, h4])

        for d in drugs_data.get("drugs", []):
            dm = DrugModel(
                code=d["code"],
                name=d["name"],
                category=d.get("category", "E"),
                unit=d.get("unit", "unit"),
                pack_size=d.get("pack_size", 1),
                cold_chain=d.get("cold_chain", False),
                unit_cost_inr=d.get("unit_cost_inr", 10.0),
                min_residual_days=d.get("min_residual_days", 30),
                created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
            )
            session.add(dm)
            for a in d.get("aliases", []):
                am = DrugAliasModel(
                    drug_code=d["code"],
                    alias=a["alias"],
                    language=a.get("language", "en"),
                    notes=a.get("notes"),
                    created_at=datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ),
                )
                session.add(am)

    return engine


@pytest.fixture
def client(test_db):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_ingest_fhir_report(client):
    report_path = Path("evals/golden/raw/fhir/report_01.json")
    with open(report_path, "r", encoding="utf-8") as f:
        fhir_json = f.read()

    resp = await client.post(
        "/ingest/H1",
        json={"raw_content": fhir_json, "source_type": "fhir"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PROCESSED"
    assert data["facility_code"] == "H1"
    assert data["extracted_items_count"] == 5
    assert data["anomalies_detected"] == 0


@pytest.mark.asyncio
async def test_ingest_bad_data_text_anomalies(client):
    bad_text = """DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: 01/11/2026
---------------------------------------------------------
10000 inzulin reg 100iu vials b.no B-999 exp 14/08/1999
paracetmol 500mg tabs: 300 tab b.no LOT-PCM-H4-01 exp 2026-12-16
---------------------------------------------------------
"""
    resp = await client.post(
        "/ingest/H4",
        json={"raw_content": bad_text, "source_type": "text"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Bad data should flag anomalies (spike & 1999 expiry)
    assert data["status"] == "NEEDS_REVIEW"
    assert data["anomalies_detected"] >= 1


@pytest.mark.asyncio
async def test_reviews_queue_and_resolve_override(client):
    # 1. Fetch pending reviews
    resp = await client.get("/reviews")
    assert resp.status_code == 200
    reviews = resp.json()
    assert len(reviews) >= 1

    rev_item = reviews[0]
    rev_id = rev_item["id"]
    assert rev_item["status"] in ("PENDING", "needs_review")
    assert rev_item["facility_code"] == "H4"

    # 2. Pharmacist corrects the item: override drug, batch, expiry, and quantity
    override_patch = {
        "drug_code": "INS-REG",
        "batch_no": "LOT-INS-CORRECTED",
        "expiry": "2026-11-25",
        "quantity": 50,
    }
    res_resp = await client.post(
        f"/reviews/{rev_id}/resolve",
        json={"action": "OVERRIDE", "override_data": override_patch},
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "resolved"

    # 3. Verify it was marked RESOLVED and alias learned in database
    with common_db.session_scope() as session:
        item = session.get(ExtractionItemModel, int(rev_id))
        assert item.review_status == "RESOLVED"
        assert item.quantity == 50

        # Check newly inserted drug_alias
        aliases = session.scalars(
            select(DrugAliasModel).where(DrugAliasModel.drug_code == "INS-REG")
        ).all()
        assert len(aliases) >= 1


@pytest.mark.asyncio
async def test_reports_listing(client):
    resp = await client.get("/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) >= 2


@pytest.mark.asyncio
async def test_pull_run_endpoint(client):
    resp = await client.post("/pull/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["facilities_polled"] == 2
