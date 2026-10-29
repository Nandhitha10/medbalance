"""Redis replay cache for LLM gateway."""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple, Union
import redis
from medbal_common.settings import get_settings

logger = logging.getLogger(__name__)


def canonical_json(data: Any) -> str:
    """Produce deterministic, whitespace-normalized JSON string with sorted keys."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_cache_key(prompt_id: str, version: Union[str, int], model: str, input_dict: Dict[str, Any]) -> str:
    """Compute sha256(prompt_id@version + model + canonical_json(input))."""
    norm_version = str(version).strip().lower()
    if norm_version.startswith("v") and len(norm_version) > 1 and norm_version[1:].isdigit():
        norm_version = norm_version[1:]

    canon_input = canonical_json(input_dict)
    raw = f"{prompt_id}@{norm_version}:{model}:{canon_input}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ReplayCache:
    """Cache managing live, record, and replay modes backed by Redis with in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None, demo_mode: Optional[str] = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL
        self.demo_mode = (demo_mode or settings.DEMO_MODE or "live").lower()
        self._redis_client: Optional[redis.Redis] = None
        self._memory_cache: Dict[str, str] = {}
        self._init_redis()

    def _init_redis(self) -> None:
        if not self.redis_url:
            return
        try:
            client = redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.0)
            client.ping()
            self._redis_client = client
            logger.info("Connected to Redis for LLM cache")
        except Exception as e:
            logger.debug(f"Redis not accessible for LLM cache, using memory fallback: {e}")
            self._redis_client = None

    def get(
        self,
        prompt_id: str,
        version: Union[str, int],
        model: str,
        input_dict: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Look up response from cache according to DEMO_MODE.

        Returns (cached_data, is_hit).
        In 'record' mode: always returns (None, False).
        In 'live' mode: checks cache, returns data on hit, (None, False) on miss.
        In 'replay' mode: checks cache, returns data on hit, (None, False) on miss.
        """
        if self.demo_mode == "record":
            return None, False

        key = compute_cache_key(prompt_id, version, model, input_dict)
        redis_key = f"llm:cache:{key}"

        cached_str = None
        if self._redis_client:
            try:
                cached_str = self._redis_client.get(redis_key)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
                self._redis_client = None

        if cached_str is None:
            cached_str = self._memory_cache.get(key)

        if cached_str:
            try:
                data = json.loads(cached_str)
                return data, True
            except Exception as e:
                logger.error(f"Failed to decode cached entry: {e}")

        return None, False

    def set(
        self,
        prompt_id: str,
        version: Union[str, int],
        model: str,
        input_dict: Dict[str, Any],
        data: Dict[str, Any],
        ttl_seconds: int = 86400 * 7,
        force: bool = False,
    ) -> None:
        """Store response in cache according to DEMO_MODE.

        If force=True, stores regardless of demo_mode (useful for cache pre-warming).
        """
        if self.demo_mode == "replay" and not force:
            # Replay mode is read-only unless forced
            return

        key = compute_cache_key(prompt_id, version, model, input_dict)
        redis_key = f"llm:cache:{key}"
        val_str = json.dumps(data)

        # Store in memory
        self._memory_cache[key] = val_str

        # Store in Redis
        if self._redis_client:
            try:
                self._redis_client.set(redis_key, val_str, ex=ttl_seconds)
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")
                self._redis_client = None

    def clear(self) -> None:
        """Clear memory cache."""
        self._memory_cache.clear()
