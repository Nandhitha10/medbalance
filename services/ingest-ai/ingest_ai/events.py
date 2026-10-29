"""Redis Streams event publishing for ingest-ai."""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional
import uuid

import redis.asyncio as aioredis
from medbal_common.clock import now
from medbal_common.settings import get_settings

logger = logging.getLogger("ingest-ai.events")


class EventPublisher:
    def __init__(self, redis_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL

    async def publish_report_received(
        self,
        report_id: str,
        facility_code: str,
        source_type: str,
        file_name: str = "",
        file_size_bytes: int = 0,
    ) -> None:
        """Publish report.received event to Redis Streams."""
        event = {
            "event_id": f"evt-rep-{uuid.uuid4().hex[:8]}",
            "event_type": "report.received",
            "timestamp": now().isoformat(),
            "data": {
                "report_id": report_id,
                "facility_code": facility_code,
                "source_type": source_type,
                "file_name": file_name or f"{facility_code}_{source_type}.dat",
                "file_size_bytes": file_size_bytes,
            },
        }
        await self._safe_publish("report.received", event)

    async def publish_anomaly_flagged(
        self,
        review_id: str,
        facility_code: str,
        anomaly_type: str,
        confidence: float,
        details: str,
    ) -> None:
        """Publish anomaly.flagged event to Redis Streams."""
        event = {
            "event_id": f"evt-anom-{uuid.uuid4().hex[:8]}",
            "event_type": "anomaly.flagged",
            "timestamp": now().isoformat(),
            "data": {
                "review_id": review_id,
                "facility_code": facility_code,
                "anomaly_type": anomaly_type,
                "confidence": max(0.0, min(1.0, float(confidence))),
                "details": details,
            },
        }
        await self._safe_publish("anomaly.flagged", event)

    async def _safe_publish(self, stream_name: str, event_payload: Dict[str, Any]) -> None:
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            async with r:
                await asyncio.wait_for(
                    r.xadd(stream_name, {"payload": json.dumps(event_payload)}),
                    timeout=0.2,
                )
        except Exception as e:
            logger.debug("Redis publish to '%s' skipped or timed out: %s", stream_name, e)
