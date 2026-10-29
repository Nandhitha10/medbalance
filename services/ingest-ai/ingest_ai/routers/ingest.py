"""Document and payload ingestion router for ingest-ai."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from medbal_common.db import session_scope
from ingest_ai.service import IngestService

router = APIRouter(tags=["ingest"])


class IngestJsonPayload(BaseModel):
    raw_content: str
    source_type: str


@router.post("/ingest/{facility_code}")
async def ingest_document(
    facility_code: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
):
    """Ingest inventory report via multipart file upload or JSON payload."""
    raw_content = ""
    source_type = "text"
    file_name = ""

    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if isinstance(uploaded_file, UploadFile):
            content_bytes = await uploaded_file.read()
            raw_content = content_bytes.decode("utf-8", errors="replace")
            file_name = uploaded_file.filename or f"{facility_code}_upload.dat"
            if file_name.endswith(".csv"):
                source_type = "csv"
            elif file_name.endswith(".json"):
                source_type = "fhir"
            elif file_name.endswith(".pdf"):
                source_type = "pdf"
            elif file_name.endswith((".xlsx", ".xls")):
                source_type = "excel"
            else:
                source_type = "text"
        else:
            raise HTTPException(status_code=400, detail="No file found in multipart upload")
    else:
        # JSON payload
        try:
            body = await request.json()
            raw_content = body.get("raw_content", "")
            source_type = body.get("source_type", "text")
            file_name = body.get("file_name", f"{facility_code}_{source_type}.txt")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON or multipart payload")

    if not raw_content:
        raise HTTPException(status_code=400, detail="Payload content cannot be empty")

    with session_scope() as session:
        service = IngestService(session)
        report = await service.ingest_report(
            facility_code=facility_code,
            raw_content=raw_content,
            source_type=source_type,
            file_name=file_name,
        )

        meta = report.report_metadata or {}
        return {
            "id": report.id,
            "facility_code": report.facility_id,
            "received_at": report.received_at.isoformat() if report.received_at else None,
            "status": report.status,
            "source_type": report.source_type,
            "extracted_items_count": meta.get("extracted_items_count", 0),
            "anomalies_detected": meta.get("anomalies_detected", 0),
        }
