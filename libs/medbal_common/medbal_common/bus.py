"""Redis Streams messaging helpers for event publishing and consumption."""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable
import redis.asyncio as aioredis
from redis.asyncio import Redis

from medbal_common.settings import get_settings

logger = logging.getLogger(__name__)

_default_redis: Redis | None = None


def get_redis_client(url: str | None = None) -> Redis:
    """Return an asynchronous Redis client instance."""
    global _default_redis
    if url is not None:
        return aioredis.from_url(url, decode_responses=True)
    if _default_redis is None:
        settings = get_settings()
        _default_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _default_redis


async def publish(
    stream: str,
    payload: dict[str, Any],
    redis_client: Redis | None = None,
) -> str:
    """Publish a dictionary payload to a Redis Stream."""
    client = redis_client or get_redis_client()
    serialized = {"payload": json.dumps(payload, default=str)}
    msg_id = await client.xadd(stream, serialized)
    return str(msg_id)


def _decode_stream_entry(fields: dict[str, Any]) -> dict[str, Any]:
    """Decode fields from a Redis Stream entry back into a Python dict."""
    if "payload" in fields:
        try:
            return json.loads(fields["payload"])
        except Exception:
            return fields
    return fields


async def consume(
    stream: str,
    group: str,
    consumer: str,
    handler: Callable[[str, dict[str, Any]], Awaitable[None]],
    redis_client: Redis | None = None,
    batch_size: int = 10,
    block_ms: int = 2000,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Consume messages from a Redis stream using consumer groups."""
    client = redis_client or get_redis_client()

    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            logger.warning(f"Consumer group '{group}' on stream '{stream}' warning: {exc}")

    while stop_event is None or not stop_event.is_set():
        try:
            # Read new messages for this group
            entries = await client.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=batch_size,
                block=block_ms,
            )

            if not entries:
                continue

            for stream_name, messages in entries:
                for msg_id, fields in messages:
                    data = _decode_stream_entry(fields)
                    try:
                        await handler(msg_id, data)
                        await client.xack(stream_name, group, msg_id)
                    except Exception as err:
                        logger.error(
                            f"Error processing message {msg_id} from {stream_name}: {err}",
                            exc_info=True,
                        )
        except asyncio.CancelledError:
            break
        except Exception as e:
            if stop_event and stop_event.is_set():
                break
            logger.error(f"Error in stream consumer loop for {stream}: {e}")
            await asyncio.sleep(1.0)


def start_stream_consumer_task(
    stream: str,
    group: str,
    consumer: str,
    handler: Callable[[str, dict[str, Any]], Awaitable[None]],
    redis_client: Redis | None = None,
    batch_size: int = 10,
    block_ms: int = 2000,
) -> tuple[asyncio.Task, asyncio.Event]:
    """Start consume() as a background asyncio task for FastAPI lifespan."""
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        consume(
            stream=stream,
            group=group,
            consumer=consumer,
            handler=handler,
            redis_client=redis_client,
            batch_size=batch_size,
            block_ms=block_ms,
            stop_event=stop_event,
        )
    )
    return task, stop_event


async def stop_stream_consumer_task(
    task: asyncio.Task,
    stop_event: asyncio.Event,
    timeout: float = 5.0,
) -> None:
    """Gracefully signal and await the consumer task."""
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        task.cancel()
