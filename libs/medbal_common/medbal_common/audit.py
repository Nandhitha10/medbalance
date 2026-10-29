"""Tamper-evident audit chain using canonical JSON and SHA-256."""

from datetime import datetime
import hashlib
import json
from typing import Any
from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from medbal_common.clock import KOLKATA_TZ, now as sim_now
from medbal_common.db import Base

GENESIS_HASH = "0" * 64


class AuditLog(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


def canonical_json(data: Any) -> str:
    """Produce deterministic canonical JSON representation."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _format_timestamp(dt: datetime | str) -> str:
    """Format datetime into consistent ISO string."""
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KOLKATA_TZ)
    return dt.isoformat()


def compute_hash(prev_hash: str, entry_dict: dict[str, Any]) -> str:
    """Compute SHA-256 hash = sha256(prev_hash + canonical_json(entry))."""
    payload_str = canonical_json(entry_dict)
    combined = f"{prev_hash}{payload_str}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def append(
    session: Session,
    actor: str,
    action: str,
    entity: str,
    entity_id: str,
    payload: dict[str, Any],
    timestamp: datetime | None = None,
) -> AuditLog:
    """Append a new tamper-evident audit record to the chain within the current session."""
    latest = session.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    ).scalar_one_or_none()

    if latest is None:
        seq = 1
        prev_hash = GENESIS_HASH
    else:
        seq = latest.seq + 1
        prev_hash = latest.hash

    ts = timestamp or sim_now()
    ts_str = _format_timestamp(ts)

    entry_data = {
        "seq": seq,
        "timestamp": ts_str,
        "actor": actor,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "payload": payload,
    }

    entry_hash = compute_hash(prev_hash, entry_data)

    record = AuditLog(
        seq=seq,
        timestamp=ts,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=entry_hash,
    )
    session.add(record)
    session.flush()
    return record


def verify(session: Session) -> dict[str, Any]:
    """Verify integrity of the audit chain.
    
    Returns:
        {"ok": bool, "entries": int, "first_bad_seq": int | None}
    """
    rows = session.execute(
        select(AuditLog).order_by(AuditLog.seq.asc())
    ).scalars().all()

    if not rows:
        return {"ok": True, "entries": 0, "first_bad_seq": None}

    expected_seq = 1
    expected_prev_hash = GENESIS_HASH
    verified_count = 0

    for row in rows:
        if row.seq != expected_seq:
            return {"ok": False, "entries": verified_count, "first_bad_seq": row.seq}

        if row.prev_hash != expected_prev_hash:
            return {"ok": False, "entries": verified_count, "first_bad_seq": row.seq}

        entry_data = {
            "seq": row.seq,
            "timestamp": _format_timestamp(row.timestamp),
            "actor": row.actor,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "payload": row.payload,
        }

        recomputed = compute_hash(expected_prev_hash, entry_data)
        if recomputed != row.hash:
            return {"ok": False, "entries": verified_count, "first_bad_seq": row.seq}

        expected_prev_hash = row.hash
        expected_seq += 1
        verified_count += 1

    return {"ok": True, "entries": verified_count, "first_bad_seq": None}
