"""Comprehensive tests for GenAI service and LLM gateway."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from medbal_common.db import Base
from genai_service.app import build_app
from genai_service.cache import ReplayCache, canonical_json, compute_cache_key
from genai_service.db_models import LlmCallModel
from genai_service.gateway import LLMGateway
from genai_service.metrics import MetricsTracker
from genai_service.providers.fake import FakeProvider
from genai_service.registry import PromptDefinition, PromptRegistry, normalize_version
from genai_service.routers.llm import router as llm_router


@pytest.fixture
def fake_provider():
    return FakeProvider(default_output={"echo": "hi", "status": "ok"})


@pytest.fixture
def memory_cache():
    cache = ReplayCache(redis_url=None, demo_mode="live")
    cache.clear()
    return cache


@pytest.fixture
def registry():
    return PromptRegistry()


@pytest.fixture
def gateway(registry, memory_cache, fake_provider):
    gw = LLMGateway(
        registry=registry,
        cache=memory_cache,
        provider=fake_provider,
        concurrency_limit=4,
    )
    return gw


def test_prompt_registry_loading(registry):
    """Test loading and rendering prompts from prompts/ directory."""
    smoke = registry.get("smoke", 1)
    assert smoke is not None
    assert smoke.id == "smoke"
    assert smoke.version == "1"

    # Also check string version
    smoke_v = registry.get("smoke", "v1")
    assert smoke_v is not None

    rendered = smoke.render({"text": "hello test"})
    assert "hello test" in rendered

    # Schema validation
    ok, err = smoke.validate_schema({"echo": "hi", "status": "ok"})
    assert ok is True
    assert err is None

    # Invalid schema (missing status)
    bad_ok, bad_err = smoke.validate_schema({"echo": "hi"})
    assert bad_ok is False
    assert bad_err is not None


def test_canonical_json_and_cache_key():
    """Verify deterministic canonical json serialization and hash stability."""
    obj1 = {"b": 2, "a": 1, "nested": {"y": "2", "x": "1"}}
    obj2 = {"a": 1, "b": 2, "nested": {"x": "1", "y": "2"}}
    assert canonical_json(obj1) == canonical_json(obj2)

    k1 = compute_cache_key("smoke", 1, "test-model", obj1)
    k2 = compute_cache_key("smoke", "v1", "test-model", obj2)
    assert k1 == k2


@pytest.mark.asyncio
async def test_cache_live_mode(gateway, fake_provider):
    """DEMO_MODE=live: first call misses and caches; second call hits cache without calling provider."""
    gateway.cache.demo_mode = "live"
    input_data = {"text": "hello live"}

    # Call 1: Cache miss
    res1 = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=input_data,
    )
    assert res1["ok"] is True
    assert res1["cached"] is False
    assert res1["output"] == {"echo": "hi", "status": "ok"}
    assert len(fake_provider.calls) == 1

    # Call 2: Cache hit
    res2 = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=input_data,
    )
    assert res2["ok"] is True
    assert res2["cached"] is True
    assert res2["output"] == {"echo": "hi", "status": "ok"}
    # Provider was NOT called a second time
    assert len(fake_provider.calls) == 1


@pytest.mark.asyncio
async def test_cache_record_mode(gateway, fake_provider):
    """DEMO_MODE=record: always calls provider and stores."""
    gateway.cache.demo_mode = "record"
    input_data = {"text": "hello record"}

    # Call 1
    res1 = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=input_data,
    )
    assert res1["cached"] is False
    assert len(fake_provider.calls) == 1

    # Call 2
    res2 = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=input_data,
    )
    assert res2["cached"] is False
    # Provider called again in record mode
    assert len(fake_provider.calls) == 2


@pytest.mark.asyncio
async def test_cache_replay_mode(gateway, fake_provider):
    """DEMO_MODE=replay: miss triggers fallback without calling provider; hit returns cached output."""
    gateway.cache.demo_mode = "replay"
    input_data = {"text": "hello replay miss"}

    # Replay miss -> fallback=True, NO network call
    res_miss = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=input_data,
    )
    assert res_miss["ok"] is False
    assert res_miss["fallback"] is True
    assert "Replay cache miss" in res_miss["error"]
    assert len(fake_provider.calls) == 0

    # Populate cache artificially with force=True
    hit_input = {"text": "hello replay hit"}
    gateway.cache.set(
        prompt_id="smoke",
        version="1",
        model=fake_provider.resolve_model("fast"),
        input_dict=hit_input,
        data={"output": {"echo": "cached-replay", "status": "ok"}, "confidence": 0.99, "tokens": 10},
        force=True,
    )

    res_hit = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data=hit_input,
    )
    assert res_hit["ok"] is True
    assert res_hit["cached"] is True
    assert res_hit["output"]["echo"] == "cached-replay"
    assert len(fake_provider.calls) == 0


@pytest.mark.asyncio
async def test_validation_retry_success(gateway, fake_provider):
    """Gateway retries on invalid schema and recovers when subsequent attempt returns valid output."""
    gateway.cache.demo_mode = "record"  # avoid cache interference

    # 1st attempt: invalid (missing status)
    # 2nd attempt: valid
    fake_provider.queue_response({"echo": "attempt 1 missing status"})
    fake_provider.queue_response({"echo": "attempt 2 fixed", "status": "ok"})

    res = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data={"text": "retry test"},
    )

    assert res["ok"] is True
    assert res["fallback"] is False
    assert res["output"] == {"echo": "attempt 2 fixed", "status": "ok"}
    # Provider called twice (initial + 1 retry)
    assert len(fake_provider.calls) == 2
    # Verify corrective user prompt was sent on retry
    second_call_messages = fake_provider.calls[1]["messages"]
    assert len(second_call_messages) >= 3
    assert "Schema validation error" in second_call_messages[-1]["content"]


@pytest.mark.asyncio
async def test_validation_retry_exhaustion(gateway, fake_provider):
    """Gateway exhausts retries on invalid output and returns fallback."""
    gateway.cache.demo_mode = "record"

    # Queue 3 invalid responses (attempt 0, 1, 2)
    fake_provider.queue_response({"invalid": "attempt 1"})
    fake_provider.queue_response({"invalid": "attempt 2"})
    fake_provider.queue_response({"invalid": "attempt 3"})

    res = await gateway.complete(
        purpose="testing",
        prompt_id="smoke",
        version=1,
        input_data={"text": "exhaustion test"},
    )

    assert res["ok"] is False
    assert res["fallback"] is True
    assert len(fake_provider.calls) == 3


def test_metrics_tracker():
    """Verify rolling metrics calculations."""
    tracker = MetricsTracker(window_seconds=3600)
    tracker.clear()

    tracker.record(purpose="extraction", cached=False, latency_sec=1.0, ok=True)
    tracker.record(purpose="extraction", cached=True, latency_sec=0.01, ok=True)
    tracker.record(purpose="narration", cached=False, latency_sec=2.0, ok=False, fallback=True, schema_failure=True)

    summary = tracker.get_summary()
    assert summary["total_calls"] == 3
    assert summary["cache_hits"] == 1
    assert summary["cache_hit_rate"] == round(1 / 3, 4)
    assert summary["schema_failures"] == 1
    assert summary["fallbacks"] == 1
    assert "extraction" in summary["by_purpose"]
    assert "narration" in summary["by_purpose"]


def test_db_logging_with_sqlite(tmp_path, fake_provider, registry, memory_cache):
    """Verify call logging to llm_call table in database."""
    from unittest.mock import patch

    db_path = tmp_path / "test_llm.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine, tables=[LlmCallModel.__table__])
    Session = sessionmaker(bind=engine)

    from contextlib import contextmanager
    @contextmanager
    def mock_session_scope():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with patch("genai_service.gateway.session_scope", mock_session_scope):
        gw = LLMGateway(registry=registry, cache=memory_cache, provider=fake_provider)

        import asyncio
        res = asyncio.run(gw.complete(
            purpose="test_logging",
            prompt_id="smoke",
            version=1,
            input_data={"text": "logging test"},
        ))
        assert res["ok"] is True

        # Check row in DB
        with Session() as s:
            rows = s.query(LlmCallModel).all()
            assert len(rows) == 1
            call = rows[0]
            assert call.purpose == "test_logging"
            assert call.prompt_id == "smoke"
            assert call.version == "1"
            assert call.ok is True
            assert call.output == {"echo": "hi", "status": "ok"}


def test_fastapi_endpoints(fake_provider):
    """Test POST /llm/complete and GET /ai/health endpoints on FastAPI app."""
    from genai_service.routers import llm as llm_router_mod
    llm_router_mod.gateway = LLMGateway(provider=fake_provider)

    app = build_app(use_fixtures=False)
    client = TestClient(app)

    # 1. Health check
    resp_health = client.get("/ai/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert health_data["status"] == "healthy"
    assert health_data["gateway"] == "genai-gateway"
    assert "cache_hit_rate" in health_data

    # Also check /api/genai/ai/health
    resp_pre_health = client.get("/api/genai/ai/health")
    assert resp_pre_health.status_code == 200

    # 2. Complete endpoint
    req_body = {
        "purpose": "smoke",
        "prompt_id": "smoke",
        "version": 1,
        "input": {"text": "fastapi test"},
    }
    resp_complete = client.post("/llm/complete", json=req_body)
    assert resp_complete.status_code == 200
    comp_data = resp_complete.json()
    assert comp_data["purpose"] == "smoke"
    assert comp_data["prompt_id"] == "smoke"
    assert comp_data["output"] == {"echo": "hi", "status": "ok"}
    assert comp_data["cached"] is False

    # Second call -> cached=True
    resp_cached = client.post("/llm/complete", json=req_body)
    assert resp_cached.status_code == 200
    assert resp_cached.json()["cached"] is True

    # Also test via /api/genai prefix
    resp_prefix = client.post("/api/genai/llm/complete", json=req_body)
    assert resp_prefix.status_code == 200
    assert resp_prefix.json()["cached"] is True
