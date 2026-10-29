"""Pharmacist review queue router."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from medbal_common.db import session_scope
from ingest_ai.service import IngestService

router = APIRouter(tags=["reviews"])


class ResolveReviewRequest(BaseModel):
    action: str  # ACCEPT, OVERRIDE, REJECT (or accept, correct, reject)
    override_data: Optional[Dict[str, Any]] = None


@router.get("/reviews")
def get_reviews():
    """List pending anomaly review items for pharmacist verification."""
    with session_scope() as session:
        service = IngestService(session)
        return service.list_reviews()


@router.post("/reviews/{id}/resolve")
async def resolve_review(id: str, payload: ResolveReviewRequest):
    """Resolve an anomaly review item."""
    with session_scope() as session:
        service = IngestService(session)
        success, message = await service.resolve_review(
            review_id=id,
            action=payload.action,
            override_data=payload.override_data,
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {
            "status": "resolved",
            "review_id": id,
        }
