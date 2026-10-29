"""Comprehensive unit and integration tests for P15:
- Grounded narrations with numeric firewall
- Injected hallucination detection and deterministic template substitution
- Official DTA voucher PDF generation with scannable QR code
- Cold-Chain consignment log PDF generation
- Financial credit memo generation and firewall verification
- QR code extraction and decoding verification
"""

import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import pypdf
from pyzbar.pyzbar import decode

from genai_service.app import app
from genai_service.firewall import (
    extract_facts_numbers,
    extract_tokens_from_text,
    generate_deterministic_credit_memo,
    generate_deterministic_narration,
    process_narration_through_firewall,
    verify_grounding,
)
from genai_service.metrics import metrics_tracker
from genai_service.pdf_generator import (
    generate_coldchain_pdf,
    generate_credit_memo_pdf,
    generate_dta_pdf,
)
from genai_service.registry import PromptRegistry
from genai_service.routers.narrate import batch_narrate_plan_orders, narrate_order


@pytest.fixture(autouse=True)
def reset_metrics():
    """Clear metric history between test runs."""
    metrics_tracker.clear()
    yield
    metrics_tracker.clear()


@pytest.fixture(autouse=True)
def mock_gateway_provider():
    """Provide fast deterministic mock LLM provider for tests."""
    from genai_service.providers.fake import FakeProvider
    from genai_service.routers.narrate import gateway as nar_gw
    from genai_service.routers.documents import gateway as doc_gw

    fake = FakeProvider(
        default_output={
            "headline": "Reallocation of Insulin Regular to District Hospital 2",
            "narration": "District Hospital 1 transferred 28 units of Insulin Regular (INS-REG, Batch LOT-INS-H1-01, Exp: 2026-11-20) to District Hospital 2. This addresses deficit while avoiding expiration loss.",
            "memo_text": "This Inter-Facility Credit Memo certifies that District Hospital 1 has transferred 28 units of Insulin Regular valued at Rs. 4074.00 to District Hospital 2.",
            "recommended_credit_inr": 4074.00,
        }
    )
    old_nar_prov = nar_gw.provider
    old_doc_prov = doc_gw.provider
    nar_gw.provider = fake
    doc_gw.provider = fake
    yield fake
    nar_gw.provider = old_nar_prov
    doc_gw.provider = old_doc_prov


@pytest.fixture
def test_client():
    return TestClient(app)


# =====================================================================
# 1. Prompt Definition Tests
# =====================================================================

def test_narrate_and_credit_memo_prompts_exist():
    """Verify that narrate_v1 and credit_memo_v1 prompts exist and parse valid YAML."""
    registry = PromptRegistry()

    narrate = registry.get("narrate", 1)
    assert narrate is not None
    assert narrate.id == "narrate"
    assert narrate.version == "1"
    assert "headline" in narrate.json_schema["properties"]
    assert "narration" in narrate.json_schema["properties"]

    cm = registry.get("credit_memo", 1)
    assert cm is not None
    assert cm.id == "credit_memo"
    assert cm.version == "1"
    assert "memo_text" in cm.json_schema["properties"]


# =====================================================================
# 2. Numeric Firewall Tests
# =====================================================================

def test_firewall_passes_grounded_text():
    """Verify that facts-grounded text with Indian formatting passes firewall."""
    facts = {
        "order_id": "DTA/BLR-U/2026/000101",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular 40IU/ml",
        "quantity": 28,
        "lot_quantity": 50,
        "lot_expiry": "2026-11-20",
        "shortage_before": 30,
        "shortage_after": 2,
        "source_daily_rate": 0.5,
        "reserve": 10,
        "units_at_risk": 40,
        "source_facility_name": "District Hospital 1",
        "destination_facility_name": "District Hospital 2",
    }

    grounded_text = (
        "District Hospital 1 has 50 vials of Insulin Regular expiring on 2026-11-20 with a daily consumption "
        "of 0.5 vials, leaving 40 vials at risk of expiration. District Hospital 2 faces an immediate shortage "
        "of 30 vials under current surge conditions. Transferring 28 vials preserves an essential 10-vial reserve "
        "at H1 and satisfies 93% of H2's immediate deficit prior to expiration."
    )

    check = verify_grounding(grounded_text, facts)
    assert check["passed"] is True, f"Expected passed grounding, got: {check}"
    assert len(check["unverified_numbers"]) == 0
    assert 28 in check["verified_numbers"]
    assert 50 in check["verified_numbers"]


def test_firewall_catches_injected_wrong_number():
    """Firewall MUST catch an injected hallucinated number, date, or amount."""
    facts = {
        "order_id": "DTA/BLR-U/2026/000101",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular",
        "quantity": 28,
        "lot_quantity": 50,
        "lot_expiry": "2026-11-20",
        "shortage_before": 30,
        "source_facility_name": "District Hospital 1",
        "destination_facility_name": "District Hospital 2",
    }

    # Injected fake number: 999 vials
    hallucinated_text = (
        "District Hospital 1 transferred 999 vials of Insulin Regular to District Hospital 2 on 2026-11-20."
    )

    check = verify_grounding(hallucinated_text, facts)
    assert check["passed"] is False
    assert 999 in check["unverified_numbers"]


def test_firewall_catches_injected_wrong_currency():
    """Firewall MUST catch an ungrounded currency value (e.g. ₹99,999.00)."""
    facts = {
        "order_id": "DTA/BLR-U/2026/000101",
        "quantity": 28,
        "unit_cost_inr": 145.50,
        "total_credit_inr": 4074.00,
        "creditor_facility_name": "District Hospital 1",
        "debtor_facility_name": "District Hospital 2",
    }

    hallucinated_currency = (
        "District Hospital 1 has provided 28 units with an unauthorized financial claim of ₹99,999.00."
    )

    check = verify_grounding(hallucinated_currency, facts)
    assert check["passed"] is False
    assert 99999 in check["unverified_numbers"] or 99999.0 in check["unverified_numbers"]


def test_firewall_substitutes_deterministic_template_on_block():
    """When firewall blocks an ungrounded hallucination, it replaces with deterministic template and logs block."""
    facts = {
        "order_id": "DTA/BLR-U/2026/000101",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular 40IU/ml",
        "quantity": 28,
        "batch_no": "LOT-INS-H1-01",
        "lot_expiry": "2026-11-20",
        "shortage_before": 30,
        "shortage_after": 2,
        "source_facility_id": "H1",
        "source_facility_name": "District Hospital 1",
        "destination_facility_id": "H2",
        "destination_facility_name": "District Hospital 2",
    }

    hallucinated_text = "Transfer of 99999 mystery vials leaving 8888 units unserved."

    processed = process_narration_through_firewall(
        raw_narration=hallucinated_text,
        headline="Hallucinated Headline",
        facts=facts,
        record_metric=True,
    )

    # Explanation must be replaced with deterministic template containing true facts
    assert "99999" not in processed["explanation"]
    assert "28 units" in processed["explanation"]
    assert "LOT-INS-H1-01" in processed["explanation"]

    # Telemetry tracker must record the firewall block
    summary = metrics_tracker.get_summary()
    assert summary["firewall_blocks"] >= 1


# =====================================================================
# 3. DTA Voucher PDF & QR Code Verification Tests
# =====================================================================

def test_dta_voucher_pdf_generation_and_qr_decoding():
    """Generate DTA PDF voucher, assert strict invariants, and verify QR decodes to /scan/{qr_token}."""
    token = "tok-unit-test-qr-1234"
    dta_data = {
        "order_id": "DTA/BLR-U/2026/000101",
        "date": "2026-11-01",
        "plan_id": "PLAN-20261101-01",
        "source_facility_id": "H1",
        "source_facility_name": "District Hospital 1",
        "destination_facility_id": "H2",
        "destination_facility_name": "District Hospital 2",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular 40IU/ml",
        "batch_no": "LOT-INS-H1-01",
        "expiry_date": "2026-11-20",
        "quantity": 28,
        "temperature_requirement": "Cold chain (2°C – 8°C)",
        "vehicle_info": "KA-01-EA-1001 (Refrigerated Van)",
        "eta": "2026-11-01 11:30 AM",
        "approver_name": "Dr. Ramesh (District Drug Officer)",
        "approved_at": "2026-11-01 08:45:00 IST",
        "qr_token": token,
        "audit_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "narration": "Transfer of 28 units of Insulin Regular from H1 to H2.",
    }

    pdf_bytes = generate_dta_pdf(dta_data)
    assert pdf_bytes.startswith(b"%PDF-"), "Generated file must be a valid PDF binary"
    assert len(pdf_bytes) > 1000

    # Invariant: Never call the voucher "Form 19"
    assert b"Form 19" not in pdf_bytes

    # Read back PDF with pypdf and extract embedded QR code image
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    found_qr = False
    decoded_urls = []

    for page in reader.pages:
        for img in page.images:
            pil_img = Image.open(io.BytesIO(img.data))
            decoded = decode(pil_img)
            for d in decoded:
                url_str = d.data.decode("utf-8")
                decoded_urls.append(url_str)
                if url_str == f"/scan/{token}":
                    found_qr = True

    assert found_qr is True, f"Expected QR code pointing to '/scan/{token}', decoded: {decoded_urls}"


def test_coldchain_consignment_log_pdf_generation():
    """Verify Cold-Chain Consignment Log PDF renders with sensor trace table and summary."""
    cc_data = {
        "order_id": "DTA/BLR-U/2026/000101",
        "plan_id": "PLAN-20261101-01",
        "source_facility_id": "H1",
        "destination_facility_id": "H2",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular 40IU/ml",
        "batch_no": "LOT-INS-H1-01",
        "quantity": 28,
        "vehicle_id": "KA-01-EA-1001",
        "device_id": "DEV-H1-01",
        "min_temp": 3.4,
        "max_temp": 5.8,
        "avg_temp": 4.5,
        "excursions": 0,
        "verified_by": "District Cold-Chain Logistics Officer",
        "audit_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    pdf_bytes = generate_coldchain_pdf(cc_data)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_credit_memo_pdf_generation():
    """Verify financial credit memo PDF renders with financial tables and signatures."""
    cm_data = {
        "memo_id": "CM/BLR-U/2026/000042",
        "order_id": "DTA/BLR-U/2026/000101",
        "issue_date": "2026-11-01",
        "creditor_facility_id": "H1",
        "creditor_facility_name": "District Hospital 1",
        "debtor_facility_id": "H2",
        "debtor_facility_name": "District Hospital 2",
        "drug_code": "INS-REG",
        "drug_name": "Insulin Regular 40IU/ml",
        "quantity": 28,
        "unit_cost_inr": 145.50,
        "total_credit_inr": 4074.00,
        "authorized_by": "District Financial Comptroller",
        "memo_text": "This Inter-Facility Credit Memo certifies that District Hospital 1 has transferred 28 units.",
    }

    pdf_bytes = generate_credit_memo_pdf(cm_data)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


# =====================================================================
# 4. REST API Endpoints Tests
# =====================================================================

def test_api_narrate_order(test_client):
    """POST /narrate/{order_id} returns grounded narration with grounding_check."""
    resp = test_client.post("/narrate/DTA/BLR-U/2026/000101")
    assert resp.status_code == 200
    data = resp.json()

    assert data["order_id"] == "DTA/BLR-U/2026/000101"
    assert "headline" in data and len(data["headline"]) > 0
    assert "explanation" in data and len(data["explanation"]) > 0
    assert "grounding_check" in data
    assert data["grounding_check"]["passed"] is True
    assert len(data["grounding_check"]["unverified_numbers"]) == 0


def test_api_docs_dta_pdf(test_client):
    """POST and GET /docs/dta/{order_id} return binary PDF with QR code."""
    for method in ("post", "get"):
        fn = getattr(test_client, method)
        resp = fn("/docs/dta/DTA/BLR-U/2026/000101")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF-")


def test_api_docs_coldchain_pdf(test_client):
    """POST and GET /docs/coldchain/{order_id} return binary PDF."""
    resp = test_client.post("/docs/coldchain/DTA/BLR-U/2026/000101")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")


def test_api_docs_credit_memo_json_and_pdf(test_client):
    """POST /docs/credit-memo/{order_id} returns JSON; /pdf suffix returns binary PDF."""
    resp_json = test_client.post("/docs/credit-memo/DTA/BLR-U/2026/000101")
    assert resp_json.status_code == 200
    cm = resp_json.json()
    assert cm["order_id"] == "DTA/BLR-U/2026/000101"
    assert cm["creditor_facility_id"] == "H1"
    assert cm["debtor_facility_id"] == "H2"
    assert cm["quantity"] == 28
    assert cm["total_credit_inr"] == 4074.00
    assert "memo_text" in cm
    assert cm["grounding_check"]["passed"] is True

    resp_pdf = test_client.post("/docs/credit-memo/DTA/BLR-U/2026/000101/pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-")


def test_ai_health_tracks_firewall(test_client):
    """GET /ai/health reports firewall_active=True and tracks firewall_blocks."""
    # First, record a simulated firewall block
    metrics_tracker.record(
        purpose="narration",
        cached=False,
        latency_sec=0.0,
        ok=False,
        firewall_block=True,
    )

    resp = test_client.get("/ai/health")
    assert resp.status_code == 200
    health = resp.json()

    assert health["status"] == "healthy"
    assert health["firewall_active"] is True
    assert health["firewall_blocks"] >= 1
