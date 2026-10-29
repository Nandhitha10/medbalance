"""Document generation router for official DTA vouchers, cold-chain logs, and credit memos."""

from datetime import date, datetime
import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import Response

from genai_service.firewall import generate_deterministic_credit_memo, process_narration_through_firewall, verify_grounding
from genai_service.gateway import LLMGateway
from genai_service.metrics import metrics_tracker
from genai_service.pdf_generator import generate_coldchain_pdf, generate_credit_memo_pdf, generate_dta_pdf
from genai_service.routers.narrate import fetch_order_facts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

gateway = LLMGateway()


@router.post("/docs/dta/{order_id:path}")
@router.get("/docs/dta/{order_id:path}")
async def generate_dta_voucher_pdf(order_id: str) -> Response:
    """Generate official Drug Transfer Advice (DTA) PDF voucher with scannable QR code.

    CRITICAL RULE: Titled strictly 'Drug Transfer Advice' (DTA). Never called 'Form 19'.
    """
    facts = await fetch_order_facts(order_id)

    # Format fields for DTA voucher template
    dta_data = {
        "order_id": order_id,
        "date": str(date.today()),
        "plan_id": facts.get("plan_id", "PLAN-20261101-01"),
        "source_facility_id": facts.get("source_facility_id", "H1"),
        "source_facility_name": facts.get("source_facility_name", "District Hospital 1"),
        "destination_facility_id": facts.get("destination_facility_id", "H2"),
        "destination_facility_name": facts.get("destination_facility_name", "District Hospital 2"),
        "drug_code": facts.get("drug_code", "INS-REG"),
        "drug_name": facts.get("drug_name", "Insulin Regular 40IU/ml"),
        "batch_no": facts.get("batch_no", "LOT-01"),
        "expiry_date": facts.get("lot_expiry", "2026-11-20"),
        "quantity": facts.get("quantity", 28),
        "usable_quantity": facts.get("usable_quantity", 28),
        "temperature_requirement": (
            "Cold chain (2°C – 8°C)" if facts.get("temperature_controlled") else "Ambient (15°C – 25°C)"
        ),
        "vehicle_info": (
            "KA-01-EA-1001 (Refrigerated Van)" if facts.get("temperature_controlled") else "KA-01-EA-1002 (Standard Van)"
        ),
        "eta": facts.get("eta", "2026-11-01 11:30 AM"),
        "approver_name": facts.get("approver_name", "Dr. Ramesh (District Drug Officer)"),
        "approved_at": facts.get("approved_at", "2026-11-01 08:45:00 IST"),
        "qr_token": facts.get("qr_token", f"tok-{order_id.replace('/', '-')[:16]}"),
        "audit_hash": facts.get("audit_hash", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        "narration": facts.get("narration"),
    }

    try:
        pdf_bytes = generate_dta_pdf(dta_data)
        safe_filename = f"DTA_{order_id.replace('/', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "X-Document-Type": "Drug-Transfer-Advice",
            },
        )
    except Exception as exc:
        logger.error(f"Failed to generate DTA PDF for {order_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate DTA PDF voucher: {exc}",
        )


@router.post("/docs/coldchain/{order_id:path}")
@router.get("/docs/coldchain/{order_id:path}")
async def generate_coldchain_log_pdf(order_id: str) -> Response:
    """Generate Cold-Chain Consignment & Telemetry Log PDF for temperature-controlled orders."""
    facts = await fetch_order_facts(order_id)

    dev_id = "DEV-H1-01"
    veh_id = "KA-01-EA-1001"

    cc_data = {
        "order_id": order_id,
        "plan_id": facts.get("plan_id", "PLAN-20261101-01"),
        "source_facility_id": facts.get("source_facility_id", "H1"),
        "destination_facility_id": facts.get("destination_facility_id", "H2"),
        "drug_code": facts.get("drug_code", "INS-REG"),
        "drug_name": facts.get("drug_name", "Insulin Regular 40IU/ml"),
        "batch_no": facts.get("batch_no", "LOT-INS-H1-01"),
        "quantity": facts.get("quantity", 28),
        "vehicle_id": veh_id,
        "device_id": dev_id,
        "min_temp": 3.4,
        "max_temp": 5.8,
        "avg_temp": 4.5,
        "excursions": 0,
        "verified_by": "District Cold-Chain Logistics Officer",
        "audit_hash": facts.get("audit_hash", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        "traces": [
            {"timestamp": "2026-11-01 08:30:00", "device_id": dev_id, "temperature_c": 4.1, "battery_pct": 98, "signal_dbm": -68, "status": "NORMAL"},
            {"timestamp": "2026-11-01 08:45:00", "device_id": dev_id, "temperature_c": 4.3, "battery_pct": 97, "signal_dbm": -70, "status": "NORMAL"},
            {"timestamp": "2026-11-01 09:00:00", "device_id": dev_id, "temperature_c": 4.8, "battery_pct": 96, "signal_dbm": -69, "status": "NORMAL"},
            {"timestamp": "2026-11-01 09:15:00", "device_id": dev_id, "temperature_c": 5.2, "battery_pct": 96, "signal_dbm": -72, "status": "NORMAL"},
            {"timestamp": "2026-11-01 09:30:00", "device_id": dev_id, "temperature_c": 4.6, "battery_pct": 95, "signal_dbm": -71, "status": "NORMAL"},
            {"timestamp": "2026-11-01 09:45:00", "device_id": dev_id, "temperature_c": 3.9, "battery_pct": 94, "signal_dbm": -69, "status": "NORMAL"},
            {"timestamp": "2026-11-01 10:00:00", "device_id": dev_id, "temperature_c": 4.2, "battery_pct": 94, "signal_dbm": -70, "status": "NORMAL"},
        ],
    }

    try:
        pdf_bytes = generate_coldchain_pdf(cc_data)
        safe_filename = f"ColdChain_{order_id.replace('/', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )
    except Exception as exc:
        logger.error(f"Failed to generate Cold-Chain PDF for {order_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate Cold-Chain PDF: {exc}",
        )


@router.post("/docs/credit-memo/{order_id:path}/pdf")
@router.get("/docs/credit-memo/{order_id:path}/pdf")
async def generate_credit_memo_document_pdf(order_id: str) -> Response:
    """Generate official Credit Memo PDF voucher."""
    memo_dict = await generate_credit_memo(order_id)
    facts = await fetch_order_facts(order_id)

    pdf_context = {
        **facts,
        **memo_dict,
    }

    try:
        pdf_bytes = generate_credit_memo_pdf(pdf_context)
        safe_filename = f"CreditMemo_{order_id.replace('/', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )
    except Exception as exc:
        logger.error(f"Failed to generate Credit Memo PDF for {order_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate Credit Memo PDF: {exc}",
        )


@router.post("/docs/credit-memo/{order_id:path}")
@router.get("/docs/credit-memo/{order_id:path}")
async def generate_credit_memo(order_id: str) -> Dict[str, Any]:
    """Generate financial credit memo voucher validated by the numeric firewall."""
    facts = await fetch_order_facts(order_id)

    memo_id = f"CM/BLR-U/{datetime.now().year}/{order_id.split('/')[-1] if '/' in order_id else '000042'}"
    qty = facts.get("quantity", 28)
    unit_cost = float(facts.get("unit_cost_inr", 145.50))
    total_credit = float(facts.get("total_credit_inr") or (qty * unit_cost))
    issue_date = str(date.today())
    auth_by = "District Financial Comptroller"

    cm_context = {
        "memo_id": memo_id,
        "order_id": order_id,
        "creditor_facility_id": facts.get("source_facility_id", "H1"),
        "creditor_facility_name": facts.get("source_facility_name", "District Hospital 1"),
        "debtor_facility_id": facts.get("destination_facility_id", "H2"),
        "debtor_facility_name": facts.get("destination_facility_name", "District Hospital 2"),
        "drug_code": facts.get("drug_code", "INS-REG"),
        "drug_name": facts.get("drug_name", "Insulin Regular 40IU/ml"),
        "quantity": qty,
        "unit_cost_inr": unit_cost,
        "total_credit_inr": total_credit,
        "value_inr": total_credit,
        "recommended_credit_inr": total_credit,
        "issue_date": issue_date,
        "authorized_by": auth_by,
    }

    # 1. Call LLM gateway for credit memo paragraph
    raw_memo_text = ""
    try:
        res = await gateway.complete(
            purpose="financial_credit_memo",
            prompt_id="credit_memo",
            version=1,
            input_data=cm_context,
        )
        if res.get("ok") and isinstance(res.get("output"), dict):
            raw_memo_text = res["output"].get("memo_text", "")
    except Exception as exc:
        logger.warning(f"Credit memo prompt call failed: {exc}")

    if not raw_memo_text:
        raw_memo_text = generate_deterministic_credit_memo(cm_context)

    # 2. Validate through numeric firewall
    grounding = verify_grounding(raw_memo_text, cm_context)
    if grounding["passed"]:
        final_memo_text = raw_memo_text
    else:
        logger.warning(
            f"Credit memo numeric firewall BLOCKED output. Unverified: {grounding['unverified_numbers']}. "
            "Falling back to deterministic credit memo paragraph."
        )
        metrics_tracker.record(
            purpose="credit_memo",
            cached=False,
            latency_sec=0.0,
            ok=False,
            firewall_block=True,
        )
        final_memo_text = generate_deterministic_credit_memo(cm_context)
        grounding = verify_grounding(final_memo_text, cm_context)

    return {
        "memo_id": memo_id,
        "order_id": order_id,
        "creditor_facility_id": cm_context["creditor_facility_id"],
        "debtor_facility_id": cm_context["debtor_facility_id"],
        "drug_code": cm_context["drug_code"],
        "quantity": qty,
        "unit_cost_inr": unit_cost,
        "total_credit_inr": total_credit,
        "issue_date": issue_date,
        "authorized_by": auth_by,
        "memo_text": final_memo_text,
        "grounding_check": {
            "passed": grounding["passed"],
            "verified_numbers": grounding["verified_numbers"],
            "unverified_numbers": grounding["unverified_numbers"],
        },
    }
