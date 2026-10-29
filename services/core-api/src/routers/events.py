"""Server-Sent Events (SSE) streaming endpoint consuming all Redis event streams."""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from medbal_common.bus import get_redis_client, _decode_stream_entry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])

ALL_STREAMS = [
    "report.received",
    "inventory.updated",
    "anomaly.flagged",
    "forecast.updated",
    "coldchain.alert",
    "plan.progress",
    "plan.completed",
    "plan.revised",
    "order.status",
    "custody.scanned",
]


async def sse_event_stream(request: Request, limit: Optional[int] = None) -> AsyncGenerator[str, None]:
    """Consume from all Redis streams and stream to browser clients with 15s heartbeats."""
    sent = 0
    # Initial connection confirmation
    yield ": connected\n\n"
    sent += 1
    if limit is not None and sent >= limit:
        return

    last_heartbeat = time.time()
    redis_client = None
    consumer_name = f"sse-{uuid4().hex[:8]}"
    streams_dict: Dict[str, str] = {}

    try:
        redis_client = get_redis_client()
        await asyncio.wait_for(redis_client.ping(), timeout=0.2)

        for stream_name in ALL_STREAMS:
            try:
                await redis_client.xgroup_create(stream_name, "sse", id="$", mkstream=True)
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    logger.debug(f"Consumer group notice on {stream_name}: {e}")
            streams_dict[stream_name] = ">"
    except Exception as exc:
        logger.warning(f"SSE Redis client not available, running in fallback mode: {exc}")
        redis_client = None

    while True:
        if await request.is_disconnected():
            break

        now = time.time()
        if now - last_heartbeat >= 15.0:
            yield ": heartbeat\n\n"
            last_heartbeat = now
            sent += 1
            if limit is not None and sent >= limit:
                break

        if redis_client is not None:
            try:
                entries = await redis_client.xreadgroup(
                    groupname="sse",
                    consumername=consumer_name,
                    streams=streams_dict,
                    count=10,
                    block=1000,
                )

                if entries:
                    for stream_name, messages in entries:
                        for msg_id, fields in messages:
                            data = _decode_stream_entry(fields)
                            event_payload = json.dumps({"stream": stream_name, "data": data})
                            yield f"event: {stream_name}\ndata: {event_payload}\n\n"
                            last_heartbeat = time.time()
                            sent += 1
                            try:
                                await redis_client.xack(stream_name, "sse", msg_id)
                            except Exception:
                                pass
                            if limit is not None and sent >= limit:
                                return
                else:
                    await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.debug(f"SSE Redis read exception: {err}")
                await asyncio.sleep(1.0)
        else:
            # Redis not connected: maintain heartbeat
            await asyncio.sleep(1.0)


@router.get("/events")
async def get_events(
    request: Request,
    limit: Optional[int] = Query(None, description="Max events to yield before closing"),
) -> StreamingResponse:
    """Stream real-time Redis Streams events to connected browsers with 15-second heartbeats."""
    return StreamingResponse(
        sse_event_stream(request, limit=limit),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
