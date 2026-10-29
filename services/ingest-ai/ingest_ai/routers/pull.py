"""Hospital polling router."""

from fastapi import APIRouter
from medbal_common.db import session_scope
from ingest_ai.service import IngestService

router = APIRouter(tags=["pull"])


@router.post("/pull/run")
async def trigger_pull():
    """Trigger active polling of hospital endpoints (H1 FHIR, H2 CSV)."""
    with session_scope() as session:
        service = IngestService(session)
        result = await service.poll_hospitals()
        return result
