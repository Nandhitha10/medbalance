"""Anthropic Claude provider adapter."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from anthropic import AsyncAnthropic
from medbal_common.settings import get_settings
from genai_service.providers.base import LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """Anthropic Claude adapter using AsyncAnthropic SDK."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.fast_model = settings.LLM_MODEL_FAST or "claude-3-5-haiku-20241022"
        self.smart_model = settings.LLM_MODEL_SMART or "claude-3-5-sonnet-20241022"
        self._client: Optional[AsyncAnthropic] = None

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY is not configured")
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

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
        client = self._get_client()
        target_model = self.resolve_model(model_tier, model_name)

        start_t = time.perf_counter()

        api_kwargs: Dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "timeout": timeout_sec,
        }
        if system:
            api_kwargs["system"] = system

        tool_name = "record_output"
        if schema:
            api_kwargs["tools"] = [{
                "name": tool_name,
                "description": "Output structured data according to the required JSON schema.",
                "input_schema": schema,
            }]
            api_kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
        elif tools:
            api_kwargs["tools"] = tools

        response = await client.messages.create(**api_kwargs)
        elapsed = time.perf_counter() - start_t

        structured_output = None
        tool_calls: List[Dict[str, Any]] = []
        text_parts: List[str] = []

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                if block.name == tool_name:
                    if isinstance(block.input, dict):
                        structured_output = block.input
                    elif isinstance(block.input, str):
                        try:
                            structured_output = json.loads(block.input)
                        except Exception:
                            structured_output = {"raw": block.input}
                else:
                    tool_calls.append({
                        "id": getattr(block, "id", ""),
                        "name": block.name,
                        "input": block.input,
                    })
            elif getattr(block, "type", None) == "text":
                text_parts.append(block.text)

        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = (getattr(response.usage, "input_tokens", 0) or 0) + (getattr(response.usage, "output_tokens", 0) or 0)

        raw_text = "\n".join(text_parts).strip() if text_parts else None

        return LLMResult(
            model=target_model,
            provider="anthropic",
            raw_text=raw_text,
            structured_output=structured_output,
            tool_calls=tool_calls if tool_calls else None,
            tokens=tokens,
            latency_sec=elapsed,
        )

