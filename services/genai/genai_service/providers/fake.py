"""Deterministic FakeProvider for testing GenAI gateway."""

import asyncio
import copy
import json
import time
from typing import Any, Dict, List, Optional, Union
from genai_service.providers.base import LLMProvider, LLMResult


class FakeProvider(LLMProvider):
    """Mock LLM provider for unit and integration testing."""

    def __init__(
        self,
        default_output: Optional[Dict[str, Any]] = None,
        responses: Optional[List[Union[Dict[str, Any], str, Exception]]] = None,
        simulated_latency: float = 0.01,
        fast_model: str = "mock-fast-model",
        smart_model: str = "mock-smart-model",
    ) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.default_output = default_output or {"echo": "test", "status": "ok"}
        self.responses: List[Union[Dict[str, Any], str, Exception]] = list(responses or [])
        self.simulated_latency = simulated_latency
        self.fast_model = fast_model
        self.smart_model = smart_model
        self.raise_error: Optional[Exception] = None

    def resolve_model(self, model_tier: str, model_name: Optional[str] = None) -> str:
        """Resolve model tier into concrete model identifier."""
        if model_name:
            return model_name
        if str(model_tier).lower() == "smart":
            return self.smart_model
        return self.fast_model

    def queue_response(self, resp: Union[Dict[str, Any], str, Exception]) -> None:
        """Add a response to the queue."""
        self.responses.append(resp)

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
        if self.simulated_latency > 0:
            await asyncio.sleep(min(self.simulated_latency, timeout_sec))

        call_record = {
            "messages": copy.deepcopy(messages),
            "system": system,
            "schema": copy.deepcopy(schema) if schema else None,
            "tools": copy.deepcopy(tools) if tools else None,
            "model_tier": model_tier,
            "model_name": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timestamp": time.time(),
        }
        self.calls.append(call_record)

        if self.raise_error:
            raise self.raise_error

        # Determine next response
        if self.responses:
            next_resp = self.responses.pop(0)
            if isinstance(next_resp, Exception):
                raise next_resp
            if isinstance(next_resp, LLMResult):
                return next_resp
            if isinstance(next_resp, dict):
                resolved_model = self.resolve_model(model_tier, model_name)
                tool_calls = next_resp.get("tool_calls")
                if tool_calls is not None:
                    raw_text = next_resp.get("content") or next_resp.get("raw_text")
                    return LLMResult(
                        model=resolved_model,
                        provider="fake",
                        raw_text=raw_text,
                        structured_output=next_resp.get("structured_output"),
                        tool_calls=tool_calls,
                        tokens=42,
                        latency_sec=self.simulated_latency,
                    )
                structured = next_resp
                raw = json.dumps(next_resp)
            else:
                raw = str(next_resp)
                try:
                    structured = json.loads(raw)
                except Exception:
                    structured = None
        else:
            structured = copy.deepcopy(self.default_output)
            raw = json.dumps(structured)

        resolved_model = self.resolve_model(model_tier, model_name)

        return LLMResult(
            model=resolved_model,
            provider="fake",
            raw_text=raw,
            structured_output=structured,
            tokens=42,
            latency_sec=self.simulated_latency,
        )
