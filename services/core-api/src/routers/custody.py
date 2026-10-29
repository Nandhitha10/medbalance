"""Chain of custody endpoints, QR scan event handling, deviation detection, and simulated hospital sync."""

import asyncio
from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from medbal_common.audit import append as audit_append
from medbal_common.bus import publish
from medbal_common.clock import KOLKATA_TZ, now as sim_now
from medbal_common.db import session_scope
from medbal_common.http import create_client
from src.db_models import (
    CustodyEventModel,
    DrugModel,
    LotModel,
    RouteModel,
    TransferOrderModel,
)
from src.routers.plans import generate_qr_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Custody"])

HOSPITAL_URLS = {
    "H1": os.getenv("SIM_HOSPITAL_H1_URL", "http://sim-hospital-h1:8101"),
    "H2": os.getenv("SIM_HOSPITAL_H2_URL", "http://sim-hospital-h2:8102"),
    "H3": os.getenv("SIM_HOSPITAL_H3_URL", "http://sim-hospital-h3:8103"),
    "H4": os.getenv("SIM_HOSPITAL_H4_URL", "http://sim-hospital-h4:8104"),
}

# Circuit breakers to avoid timeout stalls when optional external microservices are offline
_hospital_offline_until: Dict[str, float] = {}
_genai_offline_until: float = 0.0


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure datetime has timezone awareness (defaulting to Asia/Kolkata)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KOLKATA_TZ)
    return dt


class CustodyScanPayload(BaseModel):
    token: str
    event: str = Field(description="Event name: dispatch, receive, or consume")
    qty: int = Field(gt=0, description="Quantity scanned")
    actor: str = Field(description="Actor / operator barcode ID or name")
    location: Optional[str] = None
    temperature_c: Optional[float] = None
    order_id: Optional[str] = None
    timestamp: Optional[str] = None
    notes: Optional[str] = None


async def _call_hospital_transfer(facility_id: str, endpoint: str, payload: Dict[str, Any]) -> None:
    """Notify the respective hospital simulation node of physical inbound or outbound transfer."""
    fac = facility_id.upper()
    now_t = time.time()
    if now_t < _hospital_offline_until.get(fac, 0.0):
        return

    primary_url = HOSPITAL_URLS.get(fac)
    if not primary_url:
        return

    candidate_urls = [primary_url]
    if "sim-hospital-" in primary_url:
        port = primary_url.split(":")[-1]
        candidate_urls.append(f"http://localhost:{port}")

    for base_url in candidate_urls:
        try:
            async with create_client(timeout=0.3) as client:
                resp = await client.post(f"{base_url}{endpoint}", json=payload)
                if resp.status_code in (200, 201):
                    return
        except Exception:
            continue

    _hospital_offline_until[fac] = now_t + 30.0
    logger.debug(f"Hospital sync for {facility_id} at {endpoint} offline; backed off for 30s")


async def _generate_deviation_summary(order_id: str, deviations: Dict[str, Any]) -> str:
    """Author a concise, firewalled one-line clinical deviation summary."""
    global _genai_offline_until
    parts = []
    if "qty_mismatch" in deviations:
        qm = deviations["qty_mismatch"]
        parts.append(f"Quantity mismatch: received {qm['received']} of {qm['dispatched']} units ({qm['diff']:+d})")
    if "late_arrival" in deviations:
        la = deviations["late_arrival"]
        parts.append(f"Late arrival: {la['delay_hours']}h delay beyond ETA")
    if "temperature_excursion" in deviations:
        te = deviations["temperature_excursion"]
        parts.append(f"Cold-chain excursion: {te['temperature_c']}°C exceeds safe 2.0-8.0°C range (quarantined)")

    deterministic_summary = "; ".join(parts) if parts else "No deviation"

    # Optional GenAI enhancement with firewall fallback and circuit breaker
    now_t = time.time()
    if now_t < _genai_offline_until:
        return deterministic_summary

    genai_url = os.getenv("GENAI_URL", "http://genai:8003")
    try:
        async with create_client(timeout=0.3) as client:
            resp = await client.post(
                f"{genai_url}/narrate/deviation",
                json={"order_id": order_id, "deviations": deviations},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("grounding_ok") and data.get("summary"):
                    return str(data["summary"])
    except Exception:
        _genai_offline_until = now_t + 30.0

    return deterministic_summary


@router.post("/custody/scan", response_model=Dict[str, Any])
async def record_custody_scan(payload: CustodyScanPayload) -> Dict[str, Any]:
    """Record physical custody barcode / QR scan event with HMAC verification and state machine enforcement."""
    current_time = sim_now()
    event_norm = payload.event.lower().strip()

    with session_scope() as session:
        # 1. Identify order
        order = None
        if payload.order_id:
            order = session.get(TransferOrderModel, payload.order_id)
            if not order:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Order '{payload.order_id}' not found",
                )
            expected_hmac = generate_qr_token(order.id)
            if not (hmac.compare_digest(payload.token, expected_hmac) or (order.qr_token and payload.token == order.qr_token)):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid HMAC custody token",
                )
        else:
            # Look up by stored qr_token
            order = session.execute(
                select(TransferOrderModel).where(TransferOrderModel.qr_token == payload.token)
            ).scalar_one_or_none()

            # Fallback: check HMAC across all orders
            if not order:
                all_orders = session.execute(select(TransferOrderModel)).scalars().all()
                for o in all_orders:
                    if hmac.compare_digest(payload.token, generate_qr_token(o.id)):
                        order = o
                        break

            if not order:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid HMAC custody token or order not found",
                )

        old_order_status = order.status

        # 2. Enforce strict state order: APPROVED -> IN_TRANSIT -> DELIVERED -> COMPLETED
        if event_norm == "dispatch":
            if old_order_status != "APPROVED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot dispatch order in state '{old_order_status}'. Order must be in APPROVED state.",
                )
            new_order_status = "IN_TRANSIT"

        elif event_norm == "receive":
            if old_order_status != "IN_TRANSIT":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot receive order in state '{old_order_status}'. Order must be in IN_TRANSIT state.",
                )
            new_order_status = "DELIVERED"

        elif event_norm == "consume":
            if old_order_status != "DELIVERED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot consume order in state '{old_order_status}'. Order must be in DELIVERED state.",
                )
            new_order_status = "COMPLETED"

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid custody event '{payload.event}'. Must be dispatch, receive, or consume.",
            )

        # 3. Process Domain Actions & Deviations
        deviations: Dict[str, Any] = {}
        is_quarantined = False

        if event_norm == "dispatch":
            # Deduct source lot in core-api
            src_lot = session.execute(
                select(LotModel).where(
                    LotModel.facility_id == order.source_facility_id,
                    LotModel.drug_code == order.drug_code,
                    LotModel.batch_no == order.batch_no,
                )
            ).scalar_one_or_none()

            if src_lot:
                src_lot.quantity = max(0, src_lot.quantity - payload.qty)
                if src_lot.quantity == 0:
                    src_lot.status = "in_transit"
                src_lot.updated_at = current_time

            # Asynchronous outbound notification to source hospital
            asyncio.create_task(
                _call_hospital_transfer(
                    order.source_facility_id,
                    "/transfers/outbound",
                    {
                        "order_id": order.id,
                        "drug_code": order.drug_code,
                        "batch_no": order.batch_no,
                        "quantity": payload.qty,
                    },
                )
            )

        elif event_norm == "receive":
            # 3a. Quantity mismatch deviation
            if payload.qty != order.quantity:
                deviations["qty_mismatch"] = {
                    "dispatched": order.quantity,
                    "received": payload.qty,
                    "diff": payload.qty - order.quantity,
                }

            # 3b. Late arrival deviation (arrival later than ETA + 1 day)
            route = session.execute(
                select(RouteModel).where(
                    RouteModel.source_id == order.source_facility_id,
                    RouteModel.destination_id == order.destination_facility_id,
                )
            ).scalar_one_or_none()
            transit_hours = float(route.transit_hours) if route and route.transit_hours else 2.0

            dispatch_evt = session.execute(
                select(CustodyEventModel)
                .where(
                    CustodyEventModel.order_id == order.id,
                    CustodyEventModel.event_type == "DISPATCH",
                )
                .order_by(CustodyEventModel.timestamp.desc())
            ).scalar_one_or_none()

            raw_dispatch_ts = dispatch_evt.timestamp if dispatch_evt else (order.updated_at or order.created_at or current_time)
            dispatch_ts = _ensure_aware(raw_dispatch_ts)
            eta = dispatch_ts + timedelta(hours=transit_hours)
            eta_deadline = eta + timedelta(days=1)

            scan_ts = _ensure_aware(current_time)
            if payload.timestamp:
                try:
                    parsed_ts = datetime.fromisoformat(payload.timestamp)
                    scan_ts = _ensure_aware(parsed_ts)
                except Exception:
                    pass

            if scan_ts > eta_deadline:
                delay_hrs = round((scan_ts - eta).total_seconds() / 3600.0, 1)
                deviations["late_arrival"] = {
                    "eta": eta.isoformat(),
                    "deadline": eta_deadline.isoformat(),
                    "arrival": scan_ts.isoformat(),
                    "delay_hours": delay_hrs,
                }

            # 3c. Cold-chain excursion in transit deviation
            is_cold = bool(order.temperature_controlled)
            if not is_cold:
                drug = session.get(DrugModel, order.drug_code)
                if drug and drug.cold_chain:
                    is_cold = True

            if is_cold and payload.temperature_c is not None:
                temp = float(payload.temperature_c)
                if temp < 2.0 or temp > 8.0:
                    is_quarantined = True
                    deviations["temperature_excursion"] = {
                        "temperature_c": temp,
                        "safe_min_c": 2.0,
                        "safe_max_c": 8.0,
                        "excursion_type": "OVERHEAT" if temp > 8.0 else "FREEZE",
                    }

            # Update or create destination lot in core-api
            dest_lot = session.execute(
                select(LotModel).where(
                    LotModel.facility_id == order.destination_facility_id,
                    LotModel.drug_code == order.drug_code,
                    LotModel.batch_no == order.batch_no,
                )
            ).scalar_one_or_none()

            src_lot = session.execute(
                select(LotModel).where(
                    LotModel.drug_code == order.drug_code,
                    LotModel.batch_no == order.batch_no,
                )
            ).scalar_one_or_none()

            expiry_date = src_lot.expiry if src_lot else (current_time.date() + timedelta(days=180))

            if dest_lot:
                dest_lot.quantity += payload.qty
                dest_lot.status = "quarantined" if is_quarantined else "active"
                dest_lot.updated_at = current_time
            else:
                new_lot = LotModel(
                    facility_id=order.destination_facility_id,
                    drug_code=order.drug_code,
                    batch_no=order.batch_no,
                    expiry=expiry_date,
                    quantity=payload.qty,
                    status="quarantined" if is_quarantined else "active",
                    created_at=current_time,
                    updated_at=current_time,
                )
                session.add(new_lot)

            # Asynchronous inbound notification to destination hospital
            asyncio.create_task(
                _call_hospital_transfer(
                    order.destination_facility_id,
                    "/transfers/inbound",
                    {
                        "order_id": order.id,
                        "drug_code": order.drug_code,
                        "batch_no": order.batch_no,
                        "expiry": str(expiry_date),
                        "quantity": payload.qty,
                    },
                )
            )

        # 4. Generate deviation notes summary
        final_notes = payload.notes
        if deviations:
            dev_summary = await _generate_deviation_summary(order.id, deviations)
            final_notes = f"{payload.notes} | {dev_summary}" if payload.notes else dev_summary

        # 5. Persist Custody Event
        custody_evt = CustodyEventModel(
            order_id=order.id,
            actor=payload.actor,
            event_type=event_norm.upper(),
            timestamp=current_time,
            location=payload.location or f"{order.source_facility_id if event_norm == 'dispatch' else order.destination_facility_id} bay",
            temperature_c=payload.temperature_c,
            signature_hash=payload.token,
            notes=final_notes,
            deviation=deviations if deviations else None,
        )
        session.add(custody_evt)
        session.flush()

        # Update order status
        order.status = new_order_status
        order.updated_at = current_time

        # 6. Audit ledger entry in same transaction
        audit_append(
            session=session,
            actor=payload.actor,
            action=f"custody_{event_norm}",
            entity="transfer_order",
            entity_id=order.id,
            payload={
                "event": event_norm.upper(),
                "qty": payload.qty,
                "old_status": old_order_status,
                "new_status": new_order_status,
                "location": custody_evt.location,
                "temperature_c": payload.temperature_c,
                "deviation": deviations if deviations else None,
            },
            timestamp=current_time,
        )

        event_id = custody_evt.id
        order_id = order.id
        recorded_status = order.status
        order_source = order.source_facility_id
        order_dest = order.destination_facility_id

    # 7. Publish Redis Streams events
    try:
        scan_event_payload = {
            "event_id": f"evt-scan-{uuid4().hex[:8]}",
            "event_type": "custody.scanned",
            "timestamp": current_time.isoformat(),
            "data": {
                "order_id": order_id,
                "event_type": event_norm.upper(),
                "actor": payload.actor,
                "location": payload.location,
                "temperature_c": payload.temperature_c,
                "signature_hash": payload.token,
                "deviation": deviations if deviations else None,
            },
        }
        await asyncio.wait_for(publish("custody.scanned", scan_event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish custody.scanned event: {exc}")

    try:
        status_event_payload = {
            "event_id": f"evt-ord-{uuid4().hex[:8]}",
            "event_type": "order.status",
            "timestamp": current_time.isoformat(),
            "data": {
                "order_id": order_id,
                "old_status": old_order_status,
                "new_status": recorded_status,
                "actor": payload.actor,
                "source_facility_id": order_source,
                "destination_facility_id": order_dest,
                "notes": final_notes,
            },
        }
        await asyncio.wait_for(publish("order.status", status_event_payload), timeout=0.5)
    except Exception as exc:
        logger.warning(f"Could not publish order.status event: {exc}")

    return {
        "status": "recorded",
        "event_id": event_id,
        "order_id": order_id,
        "order_status": recorded_status,
        "event_type": event_norm.upper(),
        "deviation": deviations if deviations else None,
        "notes": final_notes,
    }


async def execute_auto_scan(order_id: str, transit_delay_sec: float = 0.1) -> Dict[str, Any]:
    """Execute automated dispatch -> transit wait -> receive sequence for an approved order."""
    with session_scope() as session:
        order = session.get(TransferOrderModel, order_id)
        if not order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        if order.status != "APPROVED":
            raise HTTPException(status_code=400, detail=f"Order {order_id} in state '{order.status}', must be APPROVED")

        qr_tok = order.qr_token or generate_qr_token(order.id)
        qty = order.quantity
        src_fac = order.source_facility_id
        dst_fac = order.destination_facility_id
        temp_c = 4.5 if order.temperature_controlled else None

    # Step 1: Dispatch
    dispatch_res = await record_custody_scan(
        CustodyScanPayload(
            token=qr_tok,
            event="dispatch",
            qty=qty,
            actor="auto_scan_driver",
            location=f"{src_fac} Outbound Dock",
            temperature_c=temp_c,
            order_id=order_id,
        )
    )

    # Step 2: Transit wait
    if transit_delay_sec > 0:
        await asyncio.sleep(transit_delay_sec)

    # Step 3: Receive
    receive_res = await record_custody_scan(
        CustodyScanPayload(
            token=qr_tok,
            event="receive",
            qty=qty,
            actor="auto_scan_receiver",
            location=f"{dst_fac} Receiving Bay",
            temperature_c=temp_c,
            order_id=order_id,
        )
    )

    return {
        "status": "completed",
        "order_id": order_id,
        "dispatch_event_id": dispatch_res.get("event_id"),
        "receive_event_id": receive_res.get("event_id"),
    }


@router.post("/custody/auto-scan/{order_id:path}", response_model=Dict[str, Any])
async def auto_scan_order(
    order_id: str,
    transit_delay_sec: float = Query(0.1, description="Seconds to simulate transit delay between dispatch and receive"),
) -> Dict[str, Any]:
    """Admin/Simulation trigger to automatically flow an approved order through dispatch, transit, and receive."""
    return await execute_auto_scan(order_id=order_id, transit_delay_sec=transit_delay_sec)


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
                "deviation": c.deviation,
            }
            for c in events
        ]
