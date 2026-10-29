"""Redistribution plan persistence, sequential DTA numbering, HMAC tokens, and audit integration."""

import hashlib
import hmac
import logging
import os
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from medbal_common.audit import append as audit_append
from medbal_common.bus import publish
from medbal_common.clock import now as sim_now
from medbal_common.db import session_scope
from src.db_models import (
    CandidateModel,
    PlanRunModel,
    RegretEntryModel,
    TransferOrderModel,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Plans"])

HMAC_SECRET = os.getenv("DTA_HMAC_SECRET", "medbal_secret_key_2026")


def generate_qr_token(order_id: str) -> str:
    """Generate tamper-proof HMAC-SHA256 QR token for transfer order."""
    return hmac.new(
        HMAC_SECRET.encode("utf-8"),
        order_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _get_next_dta_number(session, offset: int = 0) -> str:
    """Compute sequential DTA voucher number in DTA/BLR-U/2026/NNNNNN format."""
    orders = session.execute(
        select(TransferOrderModel.id).where(TransferOrderModel.id.like("DTA/BLR-U/2026/%"))
    ).scalars().all()

    max_seq = 0
    pattern = re.compile(r"^DTA/BLR-U/2026/(\d+)$")
    for oid in orders:
        m = pattern.match(oid)
        if m:
            val = int(m.group(1))
            if val > max_seq:
                max_seq = val

    next_seq = max_seq + 1 + offset
    return f"DTA/BLR-U/2026/{next_seq:06d}"


class PlanCreateResponse(BaseModel):
    status: str = "created"
    plan_id: str


@router.post("/plans", status_code=status.HTTP_201_CREATED, response_model=PlanCreateResponse)
async def persist_plan(payload: Dict[str, Any]) -> PlanCreateResponse:
    """Persist completed plan run with candidates, orders, and regret in a single atomic transaction."""
    current_time = sim_now()
    plan_id = payload.get("id") or f"PLAN-{current_time.strftime('%Y%m%d')}-{uuid4().hex[:4].upper()}"

    orders_input: List[Dict[str, Any]] = payload.get("orders", [])
    candidates_input: List[Dict[str, Any]] = payload.get("candidates", [])
    regret_input: List[Dict[str, Any]] = payload.get("regret", [])

    qr_tokens: Dict[str, str] = {}
    persisted_orders_count = 0
    total_units = 0

    with session_scope() as session:
        # 1. Check or upsert PlanRun
        existing_plan = session.get(PlanRunModel, plan_id)
        if existing_plan is not None:
            session.delete(existing_plan)
            session.flush()

        plan_run = PlanRunModel(
            id=plan_id,
            timestamp=current_time,
            status=payload.get("status", "COMPLETED"),
            mode=payload.get("mode", "live"),
            solver_tier=payload.get("solver_tier", "greedy"),
            execution_time_sec=float(payload.get("execution_time_sec", 0.0)),
            total_orders=int(payload.get("total_orders", len(orders_input))),
            total_units=int(payload.get("total_units", sum(int(o.get("quantity", 0)) for o in orders_input))),
            shortage_reduction=int(payload.get("shortage_reduction", 0)),
            expiry_avoided=int(payload.get("expiry_avoided", 0)),
            total_savings_inr=float(payload.get("total_savings_inr", 0.0)),
            solver_meta=payload.get("solver_meta", {}),
            summary=payload.get("summary", {}),
        )
        session.add(plan_run)

        # 2. Persist Transfer Orders
        for idx, o in enumerate(orders_input):
            raw_id = o.get("id")
            if raw_id and re.match(r"^DTA/[A-Z0-9\-]+/\d{4}/\d{6}$", raw_id):
                order_id = raw_id
            else:
                order_id = _get_next_dta_number(session, offset=idx)

            qr_token = generate_qr_token(order_id)
            qr_tokens[order_id] = qr_token

            order_qty = int(o.get("quantity", 0))
            total_units += order_qty

            order_model = TransferOrderModel(
                id=order_id,
                plan_run_id=plan_id,
                source_facility_id=o["source_facility_id"],
                destination_facility_id=o["destination_facility_id"],
                drug_code=o["drug_code"],
                batch_no=o["batch_no"],
                quantity=order_qty,
                usable_quantity=int(o.get("usable_quantity", order_qty)),
                status=o.get("status", "DRAFT"),
                temperature_controlled=bool(o.get("temperature_controlled", False)),
                savings_inr=float(o.get("savings_inr", 0.0)),
                term_breakdown=o.get("term_breakdown", {}),
                created_at=current_time,
                updated_at=current_time,
            )
            session.add(order_model)
            persisted_orders_count += 1

        # 3. Persist Candidates
        for idx, c in enumerate(candidates_input):
            cand_id = c.get("id") or f"CND-{plan_id[-6:]}-{idx+1:03d}"
            cand_model = CandidateModel(
                id=cand_id,
                plan_run_id=plan_id,
                lot_batch_no=c.get("lot_batch_no") or c.get("batch_no", ""),
                drug_code=c["drug_code"],
                source_facility_id=c["source_facility_id"],
                destination_facility_id=c["destination_facility_id"],
                chunk_quantity=int(c.get("chunk_quantity", 0)),
                usable_quantity=int(c.get("usable_quantity", 0)),
                is_feasible=bool(c.get("is_feasible", True)),
                feasibility_flags=c.get("feasibility_flags", {}),
                reward=float(c.get("reward", 0.0)),
                cost=float(c.get("cost", 0.0)),
            )
            session.add(cand_model)

        # 4. Persist Regret Entries
        for r in regret_input:
            order_id_ref = r.get("order_id")
            if not order_id_ref and orders_input:
                order_id_ref = orders_input[0].get("id")
            if order_id_ref:
                regret_model = RegretEntryModel(
                    plan_run_id=plan_id,
                    order_id=order_id_ref,
                    alternate_destination_id=r["alternate_destination_id"],
                    chosen_reward=float(r.get("chosen_reward", 0.0)),
                    alternate_reward=float(r.get("alternate_reward", 0.0)),
                    regret_delta=float(r.get("regret_delta", 0.0)),
                    reason=r.get("reason"),
                )
                session.add(regret_model)

        # 5. Atomic Audit Log entry
        audit_payload = {
            "plan_id": plan_id,
            "orders_count": persisted_orders_count,
            "total_units": total_units,
            "shortage_reduction": plan_run.shortage_reduction,
            "expiry_avoided": plan_run.expiry_avoided,
            "solver_tier": plan_run.solver_tier,
            "qr_tokens": qr_tokens,
        }
        audit_append(
            session=session,
            actor="optimizer",
            action="persist_plan",
            entity="plan_run",
            entity_id=plan_id,
            payload=audit_payload,
            timestamp=current_time,
        )

    # 6. Publish Redis Stream plan.completed
    try:
        event_payload = {
            "event_id": f"evt-plan-{uuid4().hex[:8]}",
            "event_type": "plan.completed",
            "timestamp": current_time.isoformat(),
            "data": {
                "plan_id": plan_id,
                "orders_count": persisted_orders_count,
                "units_transferred": total_units,
                "shortage_reduction": int(payload.get("shortage_reduction", 0)),
                "expiry_avoided": int(payload.get("expiry_avoided", 0)),
                "solver_tier": payload.get("solver_tier", "greedy"),
                "execution_time_sec": float(payload.get("execution_time_sec", 0.0)),
            },
        }
        import asyncio
        await asyncio.wait_for(publish("plan.completed", event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish plan.completed event: {exc}")

    return PlanCreateResponse(status="created", plan_id=plan_id)
