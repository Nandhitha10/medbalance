"""Inventory lots management and idempotent batch upserts."""

from datetime import date
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from medbal_common.audit import append as audit_append
from medbal_common.bus import publish
from medbal_common.clock import now as sim_now
from medbal_common.db import session_scope
from src.db_models import LotModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Lots"])


class LotBatchItem(BaseModel):
    facility_id: str
    drug_code: str
    batch_no: str
    expiry: date
    quantity: int = Field(ge=0)


class UpsertBatchResponse(BaseModel):
    status: str = "ok"
    upserted_count: int


@router.get("/lots", response_model=List[Dict[str, Any]])
def get_lots(
    facility: Optional[str] = Query(None, description="Facility ID filter"),
    drug: Optional[str] = Query(None, description="Drug code filter"),
) -> List[Dict[str, Any]]:
    """Query current inventory lots with optional facility and drug filtering."""
    with session_scope() as session:
        stmt = select(LotModel)
        if facility:
            stmt = stmt.where(LotModel.facility_id == facility)
        if drug:
            stmt = stmt.where(LotModel.drug_code == drug)

        stmt = stmt.order_by(LotModel.expiry.asc(), LotModel.batch_no.asc())
        lots = session.execute(stmt).scalars().all()

        return [
            {
                "id": lt.id,
                "facility_id": lt.facility_id,
                "drug_code": lt.drug_code,
                "batch_no": lt.batch_no,
                "expiry": lt.expiry.isoformat(),
                "quantity": lt.quantity,
                "created_at": lt.created_at.isoformat() if lt.created_at else None,
            }
            for lt in lots
        ]


@router.post("/lots/upsert-batch", response_model=UpsertBatchResponse)
async def upsert_lots_batch(items: List[LotBatchItem]) -> UpsertBatchResponse:
    """Idempotently batch upsert lots on (facility_id, drug_code, batch_no) with audit log and event publish."""
    ts = sim_now()
    affected_facility = items[0].facility_id if items else "UNKNOWN"
    affected_drugs = list(set(it.drug_code for it in items))

    with session_scope() as session:
        for item in items:
            existing = session.execute(
                select(LotModel).where(
                    LotModel.facility_id == item.facility_id,
                    LotModel.drug_code == item.drug_code,
                    LotModel.batch_no == item.batch_no,
                )
            ).scalar_one_or_none()

            if existing is not None:
                existing.expiry = item.expiry
                existing.quantity = item.quantity
                existing.updated_at = ts
            else:
                new_lot = LotModel(
                    facility_id=item.facility_id,
                    drug_code=item.drug_code,
                    batch_no=item.batch_no,
                    expiry=item.expiry,
                    quantity=item.quantity,
                    created_at=ts,
                    updated_at=ts,
                )
                session.add(new_lot)

        # Append audit entry in the same transaction
        audit_payload = {
            "upserted_count": len(items),
            "facility_id": affected_facility,
            "drug_codes": affected_drugs,
            "batches": [it.batch_no for it in items],
        }
        audit_append(
            session=session,
            actor="ingest-ai",
            action="upsert_lots_batch",
            entity="lot",
            entity_id=affected_facility,
            payload=audit_payload,
            timestamp=ts,
        )

    # Publish Redis stream event inventory.updated
    try:
        event_payload = {
            "event_id": f"evt-inv-{uuid4().hex[:8]}",
            "event_type": "inventory.updated",
            "timestamp": ts.isoformat(),
            "data": {
                "facility_code": affected_facility,
                "updated_lots_count": len(items),
                "lots": [
                    {
                        "drug_code": it.drug_code,
                        "batch_no": it.batch_no,
                        "expiry": it.expiry.isoformat(),
                        "quantity": it.quantity,
                    }
                    for it in items
                ],
            },
        }
        import asyncio
        await asyncio.wait_for(publish("inventory.updated", event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish inventory.updated to Redis stream: {exc}")

    return UpsertBatchResponse(status="ok", upserted_count=len(items))
