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
