"""Base interface for GenAI LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMResult:
    """Unified result returned by an LLM provider."""
    model: str
    provider: str
    raw_text: Optional[str] = None
    structured_output: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tokens: int = 0
    latency_sec: float = 0.0


class LLMProvider(ABC):
    """Abstract interface for LLM provider adapters."""

    @abstractmethod
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
        """Execute completion request and return unified LLMResult."""
        pass
