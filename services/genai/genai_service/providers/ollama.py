"""Ollama provider adapter for offline execution stretch."""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import httpx
from genai_service.providers.base import LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama local model adapter."""

    def __init__(self, host: Optional[str] = None) -> None:
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.fast_model = os.getenv("OLLAMA_MODEL_FAST", "qwen2.5:3b")
        self.smart_model = os.getenv("OLLAMA_MODEL_SMART", "qwen2.5:7b")

    def resolve_model(self, model_tier: str, model_name: Optional[str] = None) -> str:
        if model_name:
            return model_name
        if model_tier.lower() == "smart":
            return self.smart_model
        return self.fast_model

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model_tier: str = "fast",
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout_sec: float = 20.0,
    ) -> LLMResult:
        target_model = self.resolve_model(model_tier, model_name)
        start_t = time.perf_counter()

        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": str(msg.get("content", "")),
            })

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if schema:
            payload["format"] = schema

        url = f"{self.host}/api/chat"
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        elapsed = time.perf_counter() - start_t
        content = data.get("message", {}).get("content", "")

        structured = None
        if content:
            try:
                structured = json.loads(content)
            except Exception:
                pass

        eval_count = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return LLMResult(
            model=target_model,
            provider="ollama",
            raw_text=content,
            structured_output=structured,
            tokens=eval_count,
            latency_sec=elapsed,
        )
