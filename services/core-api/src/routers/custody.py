"""Chain of custody endpoints and scan event handling."""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from medbal_common.db import session_scope
from src.db_models import CustodyEventModel

router = APIRouter(tags=["Custody"])


@router.post("/custody/scan", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def record_custody_scan() -> Dict[str, Any]:
    """Record physical custody scan event.
    
    Per milestone constraints, P17 physical custody scanning is reserved for subsequent milestone.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Custody scanning is reserved for a future milestone.",
    )


@router.get("/custody/{order_id:path}", response_model=List[Dict[str, Any]])
def get_custody_trail(order_id: str) -> List[Dict[str, Any]]:
    """Retrieve physical custody event trail for a given transfer order."""
    with session_scope() as session:
        events = session.execute(
            select(CustodyEventModel)
            .where(CustodyEventModel.order_id == order_id)
            .order_by(CustodyEventModel.timestamp.asc(), CustodyEventModel.id.asc())
        ).scalars().all()

        return [
            {
                "id": c.id,
                "order_id": c.order_id,
                "actor": c.actor,
                "event_type": c.event_type,
                "timestamp": c.timestamp.isoformat(),
                "location": c.location,
                "temperature_c": float(c.temperature_c) if c.temperature_c is not None else None,
                "signature_hash": c.signature_hash,
                "notes": c.notes,
            }
            for c in events
        ]
