"""GenAI LLM Gateway orchestrating registry, cache, providers, validation, and logging."""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from medbal_common.db import session_scope
from medbal_common.settings import get_settings
from genai_service.cache import ReplayCache, canonical_json, compute_cache_key
from genai_service.db_models import LlmCallModel
from genai_service.metrics import metrics_tracker
from genai_service.providers.base import LLMProvider, LLMResult
from genai_service.providers.claude import ClaudeProvider
from genai_service.providers.fake import FakeProvider
from genai_service.providers.gemini import GeminiProvider
from genai_service.providers.ollama import OllamaProvider
from genai_service.registry import PromptDefinition, PromptRegistry, normalize_version

logger = logging.getLogger(__name__)


class LLMGateway:
    """Central gateway for all LLM completions in MedBalance."""

    def __init__(
        self,
        registry: Optional[PromptRegistry] = None,
        cache: Optional[ReplayCache] = None,
        provider: Optional[LLMProvider] = None,
        concurrency_limit: int = 4,
    ) -> None:
        self.settings = get_settings()
        self.registry = registry or PromptRegistry()
        self.cache = cache or ReplayCache()
        self.provider = provider or self._init_default_provider()
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self.firewall_active: bool = True

    def _init_default_provider(self) -> LLMProvider:
        """Initialize provider based on environment keys, defaulting to Claude."""
        if self.settings.ANTHROPIC_API_KEY:
            return ClaudeProvider(api_key=self.settings.ANTHROPIC_API_KEY)
        if self.settings.GEMINI_API_KEY:
            return GeminiProvider(api_key=self.settings.GEMINI_API_KEY)
        if os.getenv("OLLAMA_HOST"):
            return OllamaProvider()
        # Fallback to ClaudeProvider (will check key on invocation) or FakeProvider
        return ClaudeProvider()

    def get_provider_name(self) -> str:
        if isinstance(self.provider, ClaudeProvider):
            return "anthropic"
        if isinstance(self.provider, GeminiProvider):
            return "gemini"
        if isinstance(self.provider, OllamaProvider):
            return "ollama"
        if isinstance(self.provider, FakeProvider):
            return "fake"
        return "custom"

    async def complete(
        self,
        purpose: str,
        prompt_id: str,
        version: Union[str, int],
        input_data: Dict[str, Any],
        model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute structured LLM completion with prompt registry, caching, retries, and logging."""
        request_id = f"llm-{uuid.uuid4().hex[:12]}"
        norm_version = normalize_version(version)
        start_time = time.perf_counter()

        # 1. Lookup prompt definition
        prompt_def = self.registry.get(prompt_id, norm_version)
        if not prompt_def:
            error_msg = f"Prompt '{prompt_id}' version '{version}' not found in registry"
            logger.error(error_msg)
            metrics_tracker.record(
                purpose=purpose,
                cached=False,
                latency_sec=0.001,
                ok=False,
                fallback=True,
                schema_failure=False,
            )
            return {
                "request_id": request_id,
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": str(version),
                "model": "unknown",
                "confidence": 0.0,
                "output": {},
                "cached": False,
                "execution_time_sec": 0.001,
                "ok": False,
                "fallback": True,
                "error": error_msg,
            }

        # Determine model tier and model name
        model_tier = model_override or prompt_def.model or "fast"
        timeout_sec = 45.0 if model_tier.lower() == "smart" else 20.0

        resolved_model = model_tier
        if hasattr(self.provider, "resolve_model"):
            resolved_model = self.provider.resolve_model(model_tier)
        elif hasattr(self.provider, "fast_model"):
            resolved_model = getattr(self.provider, f"{model_tier}_model", model_tier)

        # 2. Check Replay Cache
        cached_result, is_hit = self.cache.get(prompt_id, norm_version, resolved_model, input_data)
        if is_hit and cached_result:
            exec_time = round(time.perf_counter() - start_time, 4)
            metrics_tracker.record(
                purpose=purpose,
                cached=True,
                latency_sec=exec_time,
                ok=True,
                fallback=False,
            )
            resp = {
                "request_id": request_id,
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": str(version),
                "model": resolved_model,
                "confidence": float(cached_result.get("confidence", 0.98)),
                "output": cached_result.get("output", {}),
                "cached": True,
                "execution_time_sec": exec_time,
                "ok": True,
                "fallback": False,
            }
            self._log_call(
                call_id=request_id,
                purpose=purpose,
                prompt_id=prompt_id,
                version=str(version),
                model=resolved_model,
                input_data=input_data,
                output_data=resp["output"],
                confidence=resp["confidence"],
                exec_time=exec_time,
                cached=True,
                tokens=cached_result.get("tokens", 0),
                ok=True,
                error=None,
            )
            return resp

        # Replay mode miss -> MUST NOT make network calls
        if self.cache.demo_mode == "replay":
            exec_time = round(time.perf_counter() - start_time, 4)
            error_msg = f"Replay cache miss for {prompt_id}@{version} ({resolved_model})"
            logger.warning(error_msg)
            metrics_tracker.record(
                purpose=purpose,
                cached=False,
                latency_sec=exec_time,
                ok=False,
                fallback=True,
                schema_failure=False,
            )
            resp = {
                "request_id": request_id,
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": str(version),
                "model": resolved_model,
                "confidence": 0.0,
                "output": {},
                "cached": False,
                "execution_time_sec": exec_time,
                "ok": False,
                "fallback": True,
                "error": error_msg,
            }
            self._log_call(
                call_id=request_id,
                purpose=purpose,
                prompt_id=prompt_id,
                version=str(version),
                model=resolved_model,
                input_data=input_data,
                output_data={},
                confidence=0.0,
                exec_time=exec_time,
                cached=False,
                tokens=0,
                ok=False,
                error=error_msg,
            )
            return resp

        # 3. Render prompt template
        user_prompt_text = prompt_def.render(input_data)
        messages = [{"role": "user", "content": user_prompt_text}]

        # 4. Invoke Provider with Concurrency Limit & Retries (up to 2 retries on schema failure)
        max_retries = 2
        total_tokens = 0
        last_error = None
        schema_failed = False
        final_output = None
        confidence = 0.95

        async with self._semaphore:
            for attempt in range(max_retries + 1):
                try:
                    result: LLMResult = await asyncio.wait_for(
                        self.provider.complete(
                            messages=messages,
                            system=prompt_def.system,
                            schema=prompt_def.json_schema,
                            tools=prompt_def.tools,
                            model_tier=model_tier,
                            temperature=prompt_def.temperature,
                            max_tokens=prompt_def.max_tokens,
                            timeout_sec=timeout_sec,
                        ),
                        timeout=timeout_sec + 2.0,
                    )
                    total_tokens += result.tokens
                    resolved_model = result.model

                    output_candidate = result.structured_output
                    if output_candidate is None and result.raw_text:
                        try:
                            output_candidate = json.loads(result.raw_text)
                        except Exception:
                            output_candidate = None

                    if output_candidate is None:
                        is_valid, val_err = False, "Provider returned non-JSON / empty structured output"
                    else:
                        is_valid, val_err = prompt_def.validate_schema(output_candidate)

                    if is_valid:
                        final_output = output_candidate
                        # Adjust confidence based on attempts
                        if attempt == 1:
                            confidence = 0.85
                        elif attempt == 2:
                            confidence = 0.70
                        break
                    else:
                        schema_failed = True
                        last_error = val_err
                        logger.warning(f"Schema validation attempt {attempt + 1} failed: {val_err}")

                        if attempt < max_retries:
                            # Append error and retry
                            messages.append({
                                "role": "assistant",
                                "content": json.dumps(output_candidate) if output_candidate else (result.raw_text or ""),
                            })
                            messages.append({
                                "role": "user",
                                "content": f"Schema validation error: {val_err}. Please output valid JSON matching the schema strictly.",
                            })
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(f"Provider invocation failed on attempt {attempt + 1}: {exc}")
                    if attempt < max_retries:
                        await asyncio.sleep(0.5 * (attempt + 1))

        exec_time = round(time.perf_counter() - start_time, 4)

        # 5. Handle Final Outcome
        if final_output is not None:
            # Store in cache
            cache_payload = {
                "output": final_output,
                "confidence": confidence,
                "tokens": total_tokens,
            }
            self.cache.set(prompt_id, norm_version, resolved_model, input_data, cache_payload)

            metrics_tracker.record(
                purpose=purpose,
                cached=False,
                latency_sec=exec_time,
                ok=True,
                fallback=False,
                schema_failure=schema_failed,
            )

            resp = {
                "request_id": request_id,
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": str(version),
                "model": resolved_model,
                "confidence": confidence,
                "output": final_output,
                "cached": False,
                "execution_time_sec": exec_time,
                "ok": True,
                "fallback": False,
            }
            self._log_call(
                call_id=request_id,
                purpose=purpose,
                prompt_id=prompt_id,
                version=str(version),
                model=resolved_model,
                input_data=input_data,
                output_data=final_output,
                confidence=confidence,
                exec_time=exec_time,
                cached=False,
                tokens=total_tokens,
                ok=True,
                error=None,
            )
            return resp
        else:
            # Fallback outcome
            metrics_tracker.record(
                purpose=purpose,
                cached=False,
                latency_sec=exec_time,
                ok=False,
                fallback=True,
                schema_failure=schema_failed,
            )
            resp = {
                "request_id": request_id,
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": str(version),
                "model": resolved_model,
                "confidence": 0.0,
                "output": {},
                "cached": False,
                "execution_time_sec": exec_time,
                "ok": False,
                "fallback": True,
                "error": last_error or "LLM generation failed after retries",
            }
            self._log_call(
                call_id=request_id,
                purpose=purpose,
                prompt_id=prompt_id,
                version=str(version),
                model=resolved_model,
                input_data=input_data,
                output_data={},
                confidence=0.0,
                exec_time=exec_time,
                cached=False,
                tokens=total_tokens,
                ok=False,
                error=resp["error"],
            )
            return resp

    def _log_call(
        self,
        call_id: str,
        purpose: str,
        prompt_id: str,
        version: str,
        model: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        confidence: float,
        exec_time: float,
        cached: bool,
        tokens: int,
        ok: bool,
        error: Optional[str],
    ) -> None:
        """Write call record to Postgres llm_call table."""
        input_hash = compute_cache_key(prompt_id, version, model, input_data)
        try:
            with session_scope() as session:
                entry = LlmCallModel(
                    id=call_id,
                    purpose=purpose,
                    prompt_id=prompt_id,
                    version=version,
                    model=model,
                    input_hash=input_hash,
                    input=input_data,
                    output=output_data,
                    confidence=confidence,
                    execution_time_sec=exec_time,
                    cached=cached,
                    provider=self.get_provider_name(),
                    tokens=tokens,
                    ok=ok,
                    error=error,
                )
                session.add(entry)
        except Exception as e:
            logger.debug(f"Database logging skipped or failed: {e}")
