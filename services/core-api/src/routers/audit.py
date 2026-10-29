"""Audit chain verification and query endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from sqlalchemy import select

from medbal_common.audit import verify as verify_audit_chain, AuditLog
from medbal_common.db import session_scope

router = APIRouter(tags=["Audit"])


@router.get("/audit/verify", response_model=Dict[str, Any])
def verify_audit() -> Dict[str, Any]:
    """Verify integrity of the tamper-evident SHA-256 audit hash chain."""
    with session_scope() as session:
        return verify_audit_chain(session)


@router.get("/audit", response_model=List[Dict[str, Any]])
def get_audit_entries(
    entity: Optional[str] = Query(None, description="Filter by entity type (e.g. transfer_order, lot, plan_run)"),
    id: Optional[str] = Query(None, description="Filter by entity ID"),
) -> List[Dict[str, Any]]:
    """Query audit log entries with optional entity and entity ID filters."""
    with session_scope() as session:
        stmt = select(AuditLog)
        if entity:
            stmt = stmt.where(AuditLog.entity == entity)
        if id:
            stmt = stmt.where(AuditLog.entity_id == id)

        entries = session.execute(stmt.order_by(AuditLog.seq.asc())).scalars().all()

        return [
            {
                "seq": row.seq,
                "timestamp": row.timestamp.isoformat(),
                "actor": row.actor,
                "action": row.action,
                "entity": row.entity,
                "entity_id": row.entity_id,
                "payload": row.payload,
                "prev_hash": row.prev_hash,
                "hash": row.hash,
            }
            for row in entries
        ]
