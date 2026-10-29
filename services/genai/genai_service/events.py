"""Event bus consumer for automatic batch narration on plan completion/revision."""

import asyncio
import logging
from typing import Any, Dict
from uuid import uuid4

from genai_service.routers.narrate import batch_narrate_plan_orders

logger = logging.getLogger(__name__)


async def handle_plan_event(msg_id: str, payload: Dict[str, Any]) -> None:
    """Handle plan.completed and plan.revised events by triggering batch narration."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    plan_id = data.get("plan_id") or payload.get("plan_id")
    event_type = payload.get("event_type", "plan.completed")

    if not plan_id:
        logger.debug(f"Plan event {msg_id} has no plan_id, skipping narration: {payload}")
        return

    logger.info(f"Triggering batch narration for plan {plan_id} on {event_type} (msg_id={msg_id})")
    try:
        results = await batch_narrate_plan_orders(plan_id)
        logger.info(f"Batch narration completed for plan {plan_id}: {len(results)} orders narrated")
    except Exception as exc:
        logger.error(f"Error during batch narration for plan {plan_id}: {exc}")


async def handle_order_status_event(msg_id: str, payload: Dict[str, Any]) -> None:
    """Handle order.status events: on APPROVED status, trigger DTA voucher and credit memo generation."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    order_id = data.get("order_id")
    new_status = data.get("new_status")

    if not order_id or new_status != "APPROVED":
        return

    logger.info(f"Triggering DTA and credit memo generation for approved order {order_id}")
    try:
        from genai_service.routers.documents import generate_dta_voucher, generate_credit_memo
        await generate_dta_voucher(order_id)
        await generate_credit_memo(order_id)
    except Exception as exc:
        logger.debug(f"Error triggering docs on order.status for {order_id}: {exc}")


