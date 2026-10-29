"""LLM router providing POST /llm/complete and GET /ai/health."""

import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from medbal_common.settings import get_settings
from genai_service.gateway import LLMGateway
from genai_service.metrics import metrics_tracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GenAI Gateway"])

# Global gateway instance (overridable in tests)
gateway = LLMGateway()


class LlmRequest(BaseModel):
    purpose: str
    prompt_id: str
    version: Union[str, int]
    input: Dict[str, Any]
    model: Optional[str] = Field(default="fast")


class LlmResponse(BaseModel):
    request_id: str
    purpose: str
    prompt_id: str
    version: str
    model: str
    confidence: float
    output: Dict[str, Any]
    cached: bool = False
    execution_time_sec: float
    ok: Optional[bool] = True
    fallback: Optional[bool] = False
    error: Optional[str] = None


@router.post("/llm/complete", response_model=LlmResponse)
async def complete(req: LlmRequest) -> Dict[str, Any]:
    """Execute completion request through gateway."""
    return await gateway.complete(
        purpose=req.purpose,
        prompt_id=req.prompt_id,
        version=req.version,
        input_data=req.input,
        model_override=req.model,
    )


@router.get("/ai/health")
async def ai_health() -> Dict[str, Any]:
    """GenAI health status, provider information, and rolling 24h metrics."""
    settings = get_settings()
    summary = metrics_tracker.get_summary()

    fast_model = getattr(gateway.provider, "fast_model", settings.LLM_MODEL_FAST)
    smart_model = getattr(gateway.provider, "smart_model", settings.LLM_MODEL_SMART)

    return {
        "status": "healthy",
        "gateway": "genai-gateway",
        "primary_provider": gateway.get_provider_name(),
        "fast_model": fast_model,
        "smart_model": smart_model,
        "cache_mode": gateway.cache.demo_mode,
        "firewall_active": gateway.firewall_active,
        **summary,
        "metrics_24h": summary,
    }


# =====================================================================
# Additional OpenAPI Contract Stubs (for downstream services)
# =====================================================================

@router.post("/narrate/{order_id}")
async def narrate_order(order_id: str) -> Dict[str, Any]:
    """Generate clinician-friendly grounded narration for transfer order."""
    return {
        "order_id": order_id,
        "headline": f"Redistribution order {order_id} generated for stockout prevention",
        "explanation": f"Automated transfer of surplus near-expiry units under standard transport conditions.",
        "grounding_check": {
            "passed": True,
            "verified_numbers": [28.0],
            "unverified_numbers": [],
        },
    }


@router.post("/docs/dta/{order_id}")
async def docs_dta(order_id: str):
    """Generate official DTA PDF voucher."""
    dummy_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n"
        b"0000000053 00000 n\n0000000102 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n162\n%%EOF"
    )
    return Response(content=dummy_pdf, media_type="application/pdf")


@router.post("/docs/credit-memo/{order_id}")
async def docs_credit_memo(order_id: str) -> Dict[str, Any]:
    """Generate financial credit memo voucher."""
    return {
        "memo_id": f"CM-{order_id.replace('/', '-')}",
        "order_id": order_id,
        "creditor_facility_id": "H1",
        "debtor_facility_id": "H2",
        "drug_code": "INS-REG",
        "quantity": 50,
        "unit_cost_inr": 145.50,
        "total_credit_inr": 7275.00,
        "issue_date": "2026-11-01",
        "authorized_by": "Dr. Ramesh (District Health Officer)",
    }


@router.post("/copilot/chat")
async def copilot_chat(req: Dict[str, Any]):
    """Interactive district copilot chat stream."""
    async def sse_stream():
        yield "event: message\ndata: {\"token\": \"MedBalance-Q Copilot initialized.\"}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")
