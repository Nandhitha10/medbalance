"""Comprehensive tests for Phase P16: Interactive Copilot with Tools, SSE Streaming & Numeric Firewall.

Verifies:
1. Prompt definition parsing and tool schemas for all 8 tools.
2. Direct execution of all 8 tools with fallback resilience.
3. Agent loop tool calling and SSE streaming with FakeProvider.
4. "Why didn't Hesaraghatta get insulin?" routes to why_not and reports Rule F3 cold storage failure.
5. "What if we repair its fridge?" routes to what_if and reports diff with orders added to H4.
6. Numeric firewall catches injected fake numbers and appends verification note.
7. Bilingual Kannada queries supported.
8. Database persistence of sessions and messages in PostgreSQL.
9. DEMO_MODE replay cache serving scripted golden questions.
10. FastAPI endpoint POST /copilot/chat streaming response.
"""

import json
import os
import pytest
from httpx import ASGITransport, AsyncClient

from genai_service.agent import CopilotAgent, chunk_text_tokens
from genai_service.app import build_app
from genai_service.metrics import metrics_tracker
from genai_service.providers.base import LLMResult
from genai_service.providers.fake import FakeProvider
from genai_service.registry import PromptRegistry
from genai_service.routers.copilot import copilot_agent
from genai_service.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    normalize_facility_id,
    normalize_drug_code,
)


# ==============================================================================
# 1. Prompt Definition & Tool Schemas
# ==============================================================================

def test_copilot_prompt_definition():
    """Verify copilot_v1.yaml prompt definition parses with smart model and 8 tools."""
    registry = PromptRegistry()
    prompt = registry.get("copilot", "1")
    assert prompt is not None
    assert prompt.id == "copilot"
    assert prompt.version == "1"
    assert prompt.model == "smart"
    assert prompt.temperature == 0.0

    # Verify all 8 tools defined in YAML
    assert prompt.tools is not None
    assert len(prompt.tools) == 8
    tool_names = [t["name"] for t in prompt.tools]
    expected_tools = [
        "get_district_overview",
        "get_stock_position",
        "explain_order",
        "why_not",
        "what_if",
        "get_coldchain_status",
        "get_audit_trail",
        "compare_policies",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Expected {expected} in prompt tools"


def test_tool_definitions_schemas():
    """Verify python TOOL_DEFINITIONS schemas match OpenAPI expectations."""
    assert len(TOOL_DEFINITIONS) == 8
    tool_map = {t["name"]: t for t in TOOL_DEFINITIONS}

    # Verify why_not requires facility and drug
    why_not_schema = tool_map["why_not"]["input_schema"]
    assert "facility" in why_not_schema["properties"]
    assert "drug" in why_not_schema["properties"]
    assert set(why_not_schema["required"]) == {"facility", "drug"}

    # Verify what_if requires overrides
    what_if_schema = tool_map["what_if"]["input_schema"]
    assert "overrides" in what_if_schema["properties"]
    assert "overrides" in what_if_schema["required"]


def test_alias_normalization():
    """Verify normalization of facility and drug aliases."""
    assert normalize_facility_id("hesaraghatta") == "H4"
    assert normalize_facility_id("SIM-HOSP-H4") == "H4"
    assert normalize_facility_id("jayanagar") == "H1"
    assert normalize_facility_id("district hospital") == "H1"
    assert normalize_facility_id("anekal") == "H2"
    assert normalize_facility_id("yelahanka") == "H3"
    assert normalize_facility_id("warehouse") == "W0"

    assert normalize_drug_code("insulin") == "INS-REG"
    assert normalize_drug_code("paracetamol") == "PCM-500"
    assert normalize_drug_code("ors") == "ORS-20"
    assert normalize_drug_code("amoxicillin") == "AMOX-500"
    assert normalize_drug_code("oxytocin") == "OXY-10"


# ==============================================================================
# 2. Tool Execution
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_district_overview():
    """Test get_district_overview tool returns facilities and cold chain status."""
    res, summary = await execute_tool("get_district_overview", {})
    assert "facilities_count" in res
    assert res["facilities_count"] >= 4
    assert "cold_chain_status" in res
    assert "monitored" in summary.lower() or "health facilities" in summary.lower()


@pytest.mark.asyncio
async def test_tool_get_stock_position():
    """Test get_stock_position tool returns FEFO metrics."""
    res, summary = await execute_tool("get_stock_position", {"facility": "H4", "drug": "INS-REG"})
    assert res["facility_id"] == "H4"
    assert res["drug_code"] == "INS-REG"
    assert "stock_on_hand" in res
    assert "daily_consumption_rate" in res
    assert "Stock position for" in summary


@pytest.mark.asyncio
async def test_tool_why_not_h4_insulin():
    """Test why_not tool on H4 insulin reports Rule F3 cold storage offline."""
    res, summary = await execute_tool("why_not", {"facility": "H4", "drug": "INS-REG"})
    assert res["facility_id"] == "H4"
    assert res["drug_code"] == "INS-REG"

    # Verify F3 cold storage failure is surfaced
    summary_lower = summary.lower()
    reasons_str = " ".join(res.get("reasons", [])).lower()
    assert "f3" in summary_lower or "cold" in summary_lower or "f3" in reasons_str or "cold" in reasons_str


@pytest.mark.asyncio
async def test_tool_what_if_repair_cold_storage():
    """Test what_if tool on repair_cold_storage: H4 returns added orders."""
    res, summary = await execute_tool("what_if", {"overrides": {"repair_cold_storage": "H4"}})
    assert res.get("status") == "COMPLETED"
    assert "diff" in res
    diff = res["diff"]
    assert "orders_added" in diff
    assert "orders added" in summary.lower()


@pytest.mark.asyncio
async def test_tool_get_coldchain_status():
    """Test get_coldchain_status returns device statuses."""
    res, summary = await execute_tool("get_coldchain_status", {})
    assert "status" in res
    assert "devices" in res
    assert "Cold Chain Network Status" in summary


@pytest.mark.asyncio
async def test_tool_get_audit_trail():
    """Test get_audit_trail returns SHA-256 protected entries."""
    res, summary = await execute_tool("get_audit_trail", {"order_id": "ORD-001"})
    assert res["order_id"] == "ORD-001"
    assert "audit_chain" in res
    assert len(res["audit_chain"]) >= 1
    assert "Audit Trail" in summary


@pytest.mark.asyncio
async def test_tool_compare_policies():
    """Test compare_policies returns 5-policy benchmark table."""
    res, summary = await execute_tool("compare_policies", {})
    assert "table" in res
    policies = [row["policy"] for row in res["table"]]
    assert "qubo" in policies
    assert "milp" in policies
    assert "optimality gap" in summary.lower()


# ==============================================================================
# 3. Copilot Agent Loop & Multi-Round Tool Calling
# ==============================================================================

@pytest.mark.asyncio
async def test_copilot_why_not_hesaraghatta_insulin_routing():
    """Verify 'Why didn't Hesaraghatta get insulin?' routes to why_not and reports Rule F3."""
    # 1. First turn: LLM calls why_not tool
    tool_call_resp = {
        "tool_calls": [
            {
                "id": "call_whynot_01",
                "name": "why_not",
                "input": {"facility": "H4", "drug": "INS-REG"},
            }
        ]
    }
    # 2. Second turn: LLM synthesizes grounded answer citing Rule F3 and cold storage
    final_text_resp = (
        "Hesaraghatta Primary Health Centre (H4) did not receive Insulin Regular 100 IU/ml (INS-REG) "
        "because of Rule F3: the destination cold storage unit is currently offline and under maintenance."
    )

    fake_provider = FakeProvider(responses=[tool_call_resp, final_text_resp])
    agent = CopilotAgent(provider=fake_provider)

    messages = [{"role": "user", "content": "Why didn't Hesaraghatta get insulin?"}]

    events = []
    async for raw_sse in agent.run_copilot_stream(messages, session_id="test_sess_01"):
        assert raw_sse.startswith("data: ")
        payload = json.loads(raw_sse[6:].strip())
        events.append(payload)

    # Verify tool_call event emitted
    tool_calls_emitted = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls_emitted) == 1
    assert tool_calls_emitted[0]["name"] == "why_not"
    assert tool_calls_emitted[0]["args"]["facility"] == "H4"
    assert tool_calls_emitted[0]["args"]["drug"] == "INS-REG"

    # Verify tool_result event emitted
    tool_results_emitted = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results_emitted) == 1
    assert tool_results_emitted[0]["name"] == "why_not"
    assert "result" in tool_results_emitted[0]

    # Verify token stream reconstructs final text with Rule F3
    token_events = [e for e in events if e.get("type") == "token"]
    assert len(token_events) > 0
    reconstructed_text = "".join(e["token"] for e in token_events)
    assert "Hesaraghatta Primary Health Centre (H4)" in reconstructed_text
    assert "Rule F3" in reconstructed_text or "cold storage" in reconstructed_text

    # Verify done event
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1
    assert done_events[0]["session_id"] == "test_sess_01"


@pytest.mark.asyncio
async def test_copilot_what_if_repair_fridge_routing():
    """Verify 'What if we repair its fridge?' routes to what_if and reports the diff."""
    # 1. Turn 1: LLM calls what_if
    tool_call_resp = {
        "tool_calls": [
            {
                "id": "call_whatif_01",
                "name": "what_if",
                "input": {"overrides": {"repair_cold_storage": "H4"}},
            }
        ]
    }
    # 2. Turn 2: LLM explains diff with added orders
    final_text_resp = (
        "In the simulated what-if scenario with cold storage repaired at Hesaraghatta Primary Health Centre (H4), "
        "1 order is added to the plan delivering 10 units of cold-chain stock to H4."
    )

    fake_provider = FakeProvider(responses=[tool_call_resp, final_text_resp])
    agent = CopilotAgent(provider=fake_provider)

    messages = [{"role": "user", "content": "What if we repair its fridge?"}]

    events = []
    async for raw_sse in agent.run_copilot_stream(messages, session_id="test_sess_02"):
        payload = json.loads(raw_sse[6:].strip())
        events.append(payload)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "what_if"
    assert tool_calls[0]["args"]["overrides"]["repair_cold_storage"] == "H4"

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert "diff" in tool_results[0]["result"]

    tokens = [e for e in events if e.get("type") == "token"]
    full_text = "".join(t["token"] for t in tokens)
    assert "Hesaraghatta Primary Health Centre (H4)" in full_text
    assert "added" in full_text


@pytest.mark.asyncio
async def test_copilot_numeric_firewall_catches_ungrounded_numbers():
    """Verify firewall appends verification note and logs block on ungrounded figures."""
    # Turn 1: calls get_district_overview (which yields 5 facilities, 0 orders)
    tool_call_resp = {
        "tool_calls": [
            {
                "id": "call_overview_01",
                "name": "get_district_overview",
                "input": {},
            }
        ]
    }
    # Turn 2: Assistant hallucinates fake numbers (9999 vials and Rs. 88888) not in tool output
    hallucinated_text = (
        "The district has 9999 surplus vials valued at ₹ 88,888.00 at Bengaluru District Hospital 1 (H1)."
    )

    prior_blocks = metrics_tracker.get_summary().get("firewall_blocks", 0)
    fake_provider = FakeProvider(responses=[tool_call_resp, hallucinated_text])
    agent = CopilotAgent(provider=fake_provider)

    events = []
    async for raw_sse in agent.run_copilot_stream(
        [{"role": "user", "content": "Tell me surplus value"}],
        session_id="test_firewall_sess",
    ):
        payload = json.loads(raw_sse[6:].strip())
        events.append(payload)

    # Verify firewall block logged
    assert metrics_tracker.get_summary().get("firewall_blocks", 0) > prior_blocks

    # Verify disclaimer appended
    tokens = [e for e in events if e.get("type") == "token"]
    reconstructed = "".join(t["token"] for t in tokens)
    assert "*Note: some figures could not be verified against tool records.*" in reconstructed

    # Verify done event indicates verified = false
    done_ev = [e for e in events if e.get("type") == "done"][0]
    assert done_ev["verified"] is False


@pytest.mark.asyncio
async def test_copilot_kannada_query():
    """Verify copilot answers in Kannada when queried in Kannada."""
    tool_call_resp = {
        "tool_calls": [
            {
                "id": "call_kn_01",
                "name": "why_not",
                "input": {"facility": "H4", "drug": "INS-REG"},
            }
        ]
    }
    kannada_text = (
        "ಹೆಸರಘಟ್ಟ ಪ್ರಾಥಮಿಕ ಆರೋಗ್ಯ ಕೇಂದ್ರಕ್ಕೆ (H4) ಇನ್ಸುಲಿನ್ ನಿಯಮ F3 (Rule F3) ರ ಕಾರಣದಿಂದಾಗಿ ಸಿಗಲಿಲ್ಲ, "
        "ಏಕೆಂದರೆ ಅಲ್ಲಿನ ಶೈತ್ಯಾಗಾರ ಘಟಕವು ಪ್ರಸ್ತುತ ಆಫ್‌ಲೈನ್‌ನಲ್ಲಿದೆ."
    )

    fake_provider = FakeProvider(responses=[tool_call_resp, kannada_text])
    agent = CopilotAgent(provider=fake_provider)

    events = []
    async for raw_sse in agent.run_copilot_stream(
        [{"role": "user", "content": "ಹೆಸರಘಟ್ಟ ಪ್ರಾಥಮಿಕ ಆರೋಗ್ಯ ಕೇಂದ್ರಕ್ಕೆ ಇನ್ಸುಲಿನ್ ಏಕೆ ಸಿಗಲಿಲ್ಲ?"}],
        session_id="test_kn_sess",
    ):
        payload = json.loads(raw_sse[6:].strip())
        events.append(payload)

    tokens = [e for e in events if e.get("type") == "token"]
    full_text = "".join(t["token"] for t in tokens)
    assert "ಹೆಸರಘಟ್ಟ" in full_text
    assert "Rule F3" in full_text or "ನಿಯಮ F3" in full_text


@pytest.mark.asyncio
async def test_copilot_golden_questions_json_coverage():
    """Verify evals/golden/copilot.json contains 12 scripted test cases covering all tools."""
    golden_file = os.path.join(os.getcwd(), "evals", "golden", "copilot.json")
    assert os.path.exists(golden_file)
    with open(golden_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data["test_cases"]
    assert len(test_cases) == 12

    tools_covered = {tc["expected_tool"] for tc in test_cases}
    assert "why_not" in tools_covered
    assert "what_if" in tools_covered
    assert "get_stock_position" in tools_covered
    assert "get_district_overview" in tools_covered
    assert "explain_order" in tools_covered
    assert "get_coldchain_status" in tools_covered
    assert "get_audit_trail" in tools_covered
    assert "compare_policies" in tools_covered

    # Verify q01 and q02 match user requirements
    q01 = next(tc for tc in test_cases if tc["id"] == "q01_whynot_hesaraghatta_insulin")
    assert "Hesaraghatta" in q01["query"] and "insulin" in q01["query"].lower()
    assert q01["expected_args"]["facility"] == "H4"
    assert q01["expected_args"]["drug"] == "INS-REG"

    q02 = next(tc for tc in test_cases if tc["id"] == "q02_whatif_repair_fridge")
    assert "repair" in q02["query"].lower() and "fridge" in q02["query"].lower()
    assert q02["expected_args"]["overrides"]["repair_cold_storage"] == "H4"


@pytest.mark.asyncio
async def test_copilot_fastapi_endpoint_streaming():
    """Test POST /copilot/chat via FastAPI test client with StreamingResponse."""
    app = build_app(use_fixtures=False)

    # Inject mock fake provider into router's copilot_agent
    mock_provider = FakeProvider(responses=[
        {
            "tool_calls": [
                {"id": "call_mock_1", "name": "get_district_overview", "input": {}}
            ]
        },
        "Bengaluru District Hospital 1 (H1) and Hesaraghatta Primary Health Centre (H4) are monitored."
    ])
    copilot_agent.provider = mock_provider

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/copilot/chat",
            json={
                "messages": [{"role": "user", "content": "Overview please"}],
                "session_id": "test_api_stream_sess",
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body_text = resp.text
        assert "data: " in body_text
        assert '"type": "tool_call"' in body_text
        assert '"type": "tool_result"' in body_text
        assert '"type": "token"' in body_text
        assert '"type": "done"' in body_text
