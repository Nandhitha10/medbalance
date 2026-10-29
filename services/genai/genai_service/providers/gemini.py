"""Google Gemini provider adapter (optional, env-guarded)."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from medbal_common.settings import get_settings
from genai_service.providers.base import LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini provider using direct REST API."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.fast_model = "gemini-1.5-flash"
        self.smart_model = "gemini-1.5-pro"

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
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        target_model = self.resolve_model(model_tier, model_name)
        start_t = time.perf_counter()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={self.api_key}"

        contents = []
        for msg in messages:
            role = "user" if msg.get("role") in ("user", "system") else "model"
            contents.append({
                "role": role,
                "parts": [{"text": str(msg.get("content", ""))}]
            })

        gen_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if schema:
            gen_config["responseMimeType"] = "application/json"
            gen_config["responseSchema"] = schema

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        elapsed = time.perf_counter() - start_t

        text_content = ""
        structured = None
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    text_content += p["text"]

        if text_content:
            try:
                structured = json.loads(text_content)
            except Exception:
                pass

        usage = data.get("usageMetadata", {})
        tokens = usage.get("totalTokenCount", 0)

        return LLMResult(
            model=target_model,
            provider="gemini",
            raw_text=text_content,
            structured_output=structured,
            tokens=tokens,
            latency_sec=elapsed,
        )
