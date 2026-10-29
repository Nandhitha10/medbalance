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


