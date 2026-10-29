"""Transfer orders lifecycle management: list, get, approve, reject, and audit logging."""

import logging
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Orders"])


class RejectOrderPayload(BaseModel):
    reason: Optional[str] = None


def _format_order(order: TransferOrderModel, lot_qty: Optional[int] = None) -> Dict[str, Any]:
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
async def approve_order(id: str, actor: str = "district_officer") -> Dict[str, Any]:
    """Approve a transfer order for physical execution with audit log and event bus emission."""
    current_time = sim_now()
    with session_scope() as session:
        order = session.get(TransferOrderModel, id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {id} not found")

        old_status = order.status
        order.status = "APPROVED"
        order.updated_at = current_time

        # Audit entry in same transaction
        audit_append(
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
                "new_status": "APPROVED",
                "actor": actor,
                "notes": "Approved for priority dispatch",
            },
        }
        import asyncio
        await asyncio.wait_for(publish("order.status", event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish order.status event: {exc}")

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
