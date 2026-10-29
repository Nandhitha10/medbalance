"""SQLAlchemy models for GenAI call logging."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, JSON
from medbal_common.db import Base


class LlmCallModel(Base):
    """Log record of every LLM completion request."""
    __tablename__ = "llm_call"
    __table_args__ = {"extend_existing": True}

    id = Column(String(64), primary_key=True)
    purpose = Column(String(64), nullable=False)
    prompt_id = Column(String(64), nullable=False)
    version = Column(String(16), nullable=False)
    model = Column(String(64), nullable=False)
    input_hash = Column(String(64), nullable=False)
    input = Column(JSON, nullable=False)
    output = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=True)
    execution_time_sec = Column(Float, nullable=True)
    cached = Column(Boolean, default=False)
    provider = Column(String(64), default="anthropic")
    tokens = Column(Integer, default=0)
    ok = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "prompt_id": self.prompt_id,
            "version": self.version,
            "model": self.model,
            "input_hash": self.input_hash,
            "input": self.input,
            "output": self.output,
            "confidence": self.confidence,
            "execution_time_sec": self.execution_time_sec,
            "cached": self.cached,
            "provider": self.provider,
            "tokens": self.tokens,
            "ok": self.ok,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
