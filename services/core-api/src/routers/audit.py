"""Audit chain verification and query endpoints."""

import copy
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from medbal_common.audit import verify as verify_audit_chain, AuditLog
from medbal_common.db import session_scope

router = APIRouter(tags=["Audit"])

# In-memory storage for restoring original payloads in demo tamper tests
_tamper_backups: Dict[int, Any] = {}


@router.get("/audit/verify", response_model=Dict[str, Any])
def verify_audit() -> Dict[str, Any]:
    """Verify integrity of the tamper-evident SHA-256 audit hash chain."""
    with session_scope() as session:
        return verify_audit_chain(session)


@router.post("/admin/tamper-demo", response_model=Dict[str, Any])
def tamper_demo(
    seq: Optional[int] = Query(None, description="Audit entry sequence to tamper; defaults to latest"),
) -> Dict[str, Any]:
    """Admin-only endpoint to intentionally tamper with an audit row payload to demonstrate hash-chain verification failure."""
    with session_scope() as session:
        if seq is not None:
            target = session.get(AuditLog, seq)
        else:
            target = session.execute(
                select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
            ).scalar_one_or_none()

        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No audit log entries found to tamper",
            )

        # Back up original payload
        _tamper_backups[target.seq] = copy.deepcopy(target.payload)

        # Mutate payload directly without recomputing hash
        tampered = copy.deepcopy(target.payload) if isinstance(target.payload, dict) else {"original": target.payload}
        tampered["_tampered"] = True
        tampered["tamper_demo_note"] = "Unauthorized byte flip for audit chain tamper demonstration"
        target.payload = tampered
        session.commit()

        verification = verify_audit_chain(session)
        return {
            "status": "tampered",
            "tampered_seq": target.seq,
            "verification": verification,
        }


@router.post("/admin/restore-demo", response_model=Dict[str, Any])
def restore_demo(
    seq: Optional[int] = Query(None, description="Audit entry sequence to restore; defaults to all tampered"),
) -> Dict[str, Any]:
    """Admin-only endpoint to restore original audit row payload, returning hash-chain verify to ok=True."""
    with session_scope() as session:
        if seq is not None:
            if seq not in _tamper_backups:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No tamper backup found for sequence {seq}",
                )
            target = session.get(AuditLog, seq)
            if target:
                target.payload = _tamper_backups.pop(seq)
        else:
            if not _tamper_backups:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active tamper demo backups to restore",
                )
            for s, original_payload in list(_tamper_backups.items()):
                target = session.get(AuditLog, s)
                if target:
                    target.payload = original_payload
            _tamper_backups.clear()

        session.commit()
        verification = verify_audit_chain(session)
        return {
            "status": "restored",
            "verification": verification,
        }


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

