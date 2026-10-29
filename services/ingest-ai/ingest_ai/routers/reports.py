"""Stock reports listing router."""

from typing import Any, Dict, List
from fastapi import APIRouter
from medbal_common.db import session_scope
from ingest_ai.service import IngestService

router = APIRouter(tags=["reports"])


@router.get("/reports")
def get_reports():
    """List all ingested stock reports."""
    with session_scope() as session:
        service = IngestService(session)
        return service.list_reports()
