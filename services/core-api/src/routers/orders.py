"""Transfer orders lifecycle management: list, get, approve, reject, and audit logging."""

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from medbal_common.audit import append as audit_append
from medbal_common.bus import publish
from medbal_common.clock import now as sim_now
from medbal_common.db import session_scope
from src.db_models import LotModel, TransferOrderModel
from src.routers.plans import generate_qr_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Orders"])

_genai_offline_until: float = 0.0


async def _trigger_genai_docs(order_id: str) -> None:
    """Asynchronously trigger GenAI DTA voucher and credit memo generation on order approval."""
    global _genai_offline_until
    import time
    now_t = time.time()
    if now_t < _genai_offline_until:
        return

    genai_url = os.getenv("GENAI_URL", "http://genai:8003")
    try:
        from medbal_common.http import create_client
        async with create_client(timeout=0.3) as client:
            try:
                await client.post(f"{genai_url}/docs/dta/{order_id}")
            except Exception as e:
                logger.debug(f"Async DTA generation triggered: {e}")
            try:
                await client.post(f"{genai_url}/docs/credit-memo/{order_id}")
            except Exception as e:
                logger.debug(f"Async credit memo generation triggered: {e}")
    except Exception as exc:
        _genai_offline_until = now_t + 30.0
        logger.debug(f"Could not trigger GenAI docs for order {order_id}: {exc}")


async def _trigger_auto_scan(order_id: str) -> None:
    """Automatically execute custody dispatch and receive after transit time."""
    try:
        from src.routers.custody import execute_auto_scan
        await execute_auto_scan(order_id)
    except Exception as exc:
        logger.warning(f"Auto-scan failed for order {order_id}: {exc}")


class RejectOrderPayload(BaseModel):
    reason: Optional[str] = None


class UpdateOrderNarrationPayload(BaseModel):
    narration: str
    headline: Optional[str] = None


def _format_order(order: TransferOrderModel, lot_qty: Optional[int] = None) -> Dict[str, Any]:
    qr_token = order.qr_token or f"tok-{hashlib.sha256(order.id.encode()).hexdigest()[:16]}"
    return {
        "id": order.id,
        "plan_id": order.plan_run_id,
        "source_facility_id": order.source_facility_id,
        "destination_facility_id": order.destination_facility_id,
        "drug_code": order.drug_code,
        "batch_no": order.batch_no,
        "lot_quantity": lot_qty if lot_qty is not None else order.quantity,
        "quantity": order.quantity,
        "usable_quantity": order.usable_quantity or order.quantity,
        "status": order.status,
        "temperature_controlled": bool(order.temperature_controlled),
        "savings_inr": float(order.savings_inr) if order.savings_inr is not None else 0.0,
        "qr_token": qr_token,
        "audit_hash": order.audit_hash,
        "narration": order.narration,
        "headline": order.headline,
        "approved_by": order.approved_by,
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }


@router.get("/orders", response_model=List[Dict[str, Any]])
def get_orders(
    plan_id: Optional[str] = Query(None, description="Filter by plan ID"),
    status: Optional[str] = Query(None, description="Filter by order status"),
) -> List[Dict[str, Any]]:
    """List transfer orders with optional plan_id and status filters."""
    with session_scope() as session:
        stmt = select(TransferOrderModel)
        if plan_id:
            stmt = stmt.where(TransferOrderModel.plan_run_id == plan_id)
        if status:
            stmt = stmt.where(TransferOrderModel.status == status)

        orders = session.execute(stmt.order_by(TransferOrderModel.created_at.asc())).scalars().all()

        # Map lot quantities if available
        result = []
        for o in orders:
            lot = session.execute(
                select(LotModel).where(
                    LotModel.facility_id == o.source_facility_id,
                    LotModel.drug_code == o.drug_code,
                    LotModel.batch_no == o.batch_no,
                )
            ).scalar_one_or_none()
            lot_qty = lot.quantity if lot else None
            result.append(_format_order(o, lot_qty))
        return result


@router.get("/orders/{id:path}", response_model=Dict[str, Any])
def get_order_by_id(id: str) -> Dict[str, Any]:
    """Retrieve transfer order details by DTA ID."""
    with session_scope() as session:
        order = session.get(TransferOrderModel, id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {id} not found")

        lot = session.execute(
            select(LotModel).where(
                LotModel.facility_id == order.source_facility_id,
                LotModel.drug_code == order.drug_code,
                LotModel.batch_no == order.batch_no,
            )
        ).scalar_one_or_none()
        return _format_order(order, lot.quantity if lot else None)


@router.post("/orders/{id:path}/approve", response_model=Dict[str, Any])
async def approve_order(
    id: str,
    actor: str = "district_officer",
    auto_scan: bool = Query(False, description="Automatically dispatch and receive order after transit time"),
) -> Dict[str, Any]:
    """Approve a transfer order for physical execution with audit log and event bus emission."""
    import asyncio
    current_time = sim_now()
    src_facility = ""
    dst_facility = ""
    with session_scope() as session:
        order = session.get(TransferOrderModel, id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {id} not found")

        old_status = order.status
        order.status = "APPROVED"
        order.updated_at = current_time
        order.approved_by = actor
        order.approved_at = current_time
        src_facility = order.source_facility_id
        dst_facility = order.destination_facility_id

        # Audit entry in same transaction
        audit_entry = audit_append(
            session=session,
            actor=actor,
            action="approve_order",
            entity="transfer_order",
            entity_id=id,
            payload={
                "old_status": old_status,
                "new_status": "APPROVED",
                "quantity": order.quantity,
                "drug_code": order.drug_code,
                "source_facility_id": src_facility,
                "destination_facility_id": dst_facility,
            },
            timestamp=current_time,
        )

        order.audit_hash = audit_entry.hash
        if not order.qr_token:
            order.qr_token = generate_qr_token(order.id)

        formatted = _format_order(order)

    # Publish Redis stream order.status
    try:
        event_payload = {
            "event_id": f"evt-ord-{uuid4().hex[:8]}",
            "event_type": "order.status",
            "timestamp": current_time.isoformat(),
            "data": {
                "order_id": id,
                "old_status": old_status,
                "new_status": "APPROVED",
                "actor": actor,
                "source_facility_id": src_facility,
                "destination_facility_id": dst_facility,
                "notes": "Approved for priority dispatch",
            },
        }
        await asyncio.wait_for(publish("order.status", event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish order.status event: {exc}")

    # Asynchronously trigger GenAI DTA voucher and credit memo generation
    asyncio.create_task(_trigger_genai_docs(id))

    # Auto-scan if requested or configured
    if auto_scan or os.getenv("AUTO_SCAN", "0").lower() in ("1", "true", "yes"):
        asyncio.create_task(_trigger_auto_scan(id))

    return formatted


@router.post("/orders/{id:path}/reject", response_model=Dict[str, Any])
async def reject_order(
    id: str,
    payload: Optional[RejectOrderPayload] = None,
    actor: str = "district_officer",
) -> Dict[str, Any]:
    """Reject/cancel a transfer order with audit log and event bus emission."""
    current_time = sim_now()
    reason = payload.reason if payload and payload.reason else "Cancelled by district authority"

    with session_scope() as session:
        order = session.get(TransferOrderModel, id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {id} not found")

        old_status = order.status
        order.status = "CANCELLED"
        order.updated_at = current_time

        # Audit entry in same transaction
        audit_append(
            session=session,
            actor=actor,
            action="reject_order",
            entity="transfer_order",
            entity_id=id,
            payload={
                "old_status": old_status,
                "new_status": "CANCELLED",
                "reason": reason,
                "quantity": order.quantity,
                "drug_code": order.drug_code,
            },
            timestamp=current_time,
        )

        formatted = _format_order(order)

    # Publish Redis stream order.status
    try:
        event_payload = {
            "event_id": f"evt-ord-{uuid4().hex[:8]}",
            "event_type": "order.status",
            "timestamp": current_time.isoformat(),
            "data": {
                "order_id": id,
                "old_status": old_status,
                "new_status": "CANCELLED",
                "actor": actor,
                "notes": reason,
            },
        }
        import asyncio
        await asyncio.wait_for(publish("order.status", event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish order.status event: {exc}")

    return formatted


@router.put("/orders/{id:path}/narration", response_model=Dict[str, Any])
def update_order_narration(id: str, payload: UpdateOrderNarrationPayload) -> Dict[str, Any]:
    """Store grounded narration and headline directly on the transfer order."""
    with session_scope() as session:
        order = session.get(TransferOrderModel, id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {id} not found")

        order.narration = payload.narration
        if payload.headline:
            order.headline = payload.headline

        # Also store in term_breakdown
        tb = dict(order.term_breakdown or {})
        tb["narration"] = payload.narration
        tb["headline"] = payload.headline
        order.term_breakdown = tb

        lot = session.execute(
            select(LotModel).where(
                LotModel.facility_id == order.source_facility_id,
                LotModel.drug_code == order.drug_code,
                LotModel.batch_no == order.batch_no,
            )
        ).scalar_one_or_none()
        return _format_order(order, lot.quantity if lot else None)

