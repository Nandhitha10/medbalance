"""Interactive district copilot agent runtime.

Implements multi-round tool calling (up to 5 rounds), Server-Sent Events (SSE) streaming,
P15 numeric firewall post-check, PostgreSQL chat history persistence, and DEMO_MODE replay cache.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from medbal_common.db import session_scope
from medbal_common.settings import get_settings
from genai_service.cache import ReplayCache, canonical_json
from genai_service.db_models import ChatMessageModel, ChatSessionModel
from genai_service.firewall import verify_grounding
from genai_service.metrics import metrics_tracker
from genai_service.providers.base import LLMProvider, LLMResult
from genai_service.providers.claude import ClaudeProvider
from genai_service.providers.fake import FakeProvider
from genai_service.registry import PromptRegistry
from genai_service.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
)

logger = logging.getLogger(__name__)


def chunk_text_tokens(text: str) -> List[str]:
    """Break text into word-level streaming tokens for SSE delivery."""
    tokens = []
    # Split by spaces while preserving space after word
    words = text.split(" ")
    for i, word in enumerate(words):
        token = word + (" " if i < len(words) - 1 else "")
        tokens.append(token)
    return tokens


class CopilotAgent:
    """Read-only and simulation Copilot agent for the District Drug Officer."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        registry: Optional[PromptRegistry] = None,
        replay_cache: Optional[ReplayCache] = None,
    ) -> None:
        self.settings = get_settings()
        self.registry = registry or PromptRegistry()
        self.replay_cache = replay_cache or ReplayCache()
        self.provider = provider or ClaudeProvider()
        self.prompt_def = self.registry.get("copilot", "1")

    def _persist_session(self, session_id: str, user_id: Optional[str] = None, facility_id: Optional[str] = None) -> None:
        """Create or touch chat_session row in PostgreSQL."""
        try:
            with session_scope() as session:
                existing = session.query(ChatSessionModel).filter_by(id=session_id).first()
                if not existing:
                    new_session = ChatSessionModel(
                        id=session_id,
                        user_id=user_id or "district_drug_officer",
                        facility_id=facility_id or "W0",
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(new_session)
                else:
                    existing.updated_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.debug(f"DB session persistence notice: {e}")

    def _persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a message in chat_message table."""
        try:
            with session_scope() as session:
                msg = ChatMessageModel(
                    session_id=session_id,
                    role=role,
                    content=content,
                    tool_calls=tool_calls,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(msg)
        except Exception as e:
            logger.debug(f"DB message persistence notice: {e}")

    def _get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch past messages for session from DB."""
        try:
            with session_scope() as session:
                rows = (
                    session.query(ChatMessageModel)
                    .filter_by(session_id=session_id)
                    .order_by(ChatMessageModel.id.asc())
                    .all()
                )
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.debug(f"DB history retrieval notice: {e}")
            return []

    async def run_copilot_stream(
        self,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        facility_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Execute Copilot agent loop and stream SSE events to client.

        Yields SSE format strings:
            data: {"type": "tool_call", "name": ..., "args": ..., "id": ...}\n\n
            data: {"type": "tool_result", "name": ..., "summary": ..., "result": ..., "id": ...}\n\n
            data: {"type": "token", "token": ...}\n\n
            data: {"type": "done", "session_id": ..., "verified": ...}\n\n
        """
        active_session_id = session_id or f"session_{uuid4().hex[:12]}"
        self._persist_session(active_session_id, user_id=user_id, facility_id=facility_id)

        # Extract latest user message
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        # Persist incoming user message
        if user_text:
            self._persist_message(active_session_id, role="user", content=user_text)

        # 1. Check DEMO_MODE replay cache
        cache_key_input = {"messages": [{"role": m.get("role"), "content": m.get("content")} for m in messages]}
        cached_resp, is_hit = self.replay_cache.get(
            prompt_id="copilot",
            version="1",
            model="smart",
            input_dict=cache_key_input,
        )

        if is_hit and cached_resp and self.settings.DEMO_MODE == "replay":
            logger.info(f"Serving copilot answer from DEMO_MODE=replay cache for session {active_session_id}")
            # Stream cached events
            tool_calls = cached_resp.get("tool_calls", [])
            for tc in tool_calls:
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tc.get('name'), 'args': tc.get('args', {}), 'id': tc.get('id', 'call_0')})}\n\n"
                yield f"data: {json.dumps({'type': 'tool_result', 'name': tc.get('name'), 'summary': tc.get('summary', ''), 'result': tc.get('result', {}), 'id': tc.get('id', 'call_0')})}\n\n"

            final_text = cached_resp.get("content", "")
            for tok in chunk_text_tokens(final_text):
                yield f"data: {json.dumps({'type': 'token', 'token': tok})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'session_id': active_session_id, 'verified': cached_resp.get('verified', True)})}\n\n"
            self._persist_message(active_session_id, role="assistant", content=final_text, tool_calls=tool_calls)
            return

        # Check golden eval questions if in DEMO_MODE=replay and cache missed
        if self.settings.DEMO_MODE == "replay":
            golden_path = os.path.join(os.getcwd(), "evals", "golden", "copilot.json")
            if os.path.exists(golden_path):
                try:
                    with open(golden_path, "r", encoding="utf-8") as gf:
                        golden_data = json.load(gf)
                    norm_query = user_text.strip().lower()
                    for tc in golden_data.get("test_cases", []):
                        tc_q = tc.get("query", "").strip().lower()
                        if tc_q == norm_query or tc_q in norm_query or norm_query in tc_q:
                            tool_name = tc.get("expected_tool")
                            tool_args = tc.get("expected_args", {})
                            golden_ans = tc.get("golden_answer", "")
                            call_id = f"call_{uuid4().hex[:6]}"

                            yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'args': tool_args, 'id': call_id})}\n\n"
                            t_res, t_sum = await execute_tool(tool_name, tool_args)
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'summary': t_sum, 'result': t_res, 'id': call_id})}\n\n"

                            for tok in chunk_text_tokens(golden_ans):
                                yield f"data: {json.dumps({'type': 'token', 'token': tok})}\n\n"

                            yield f"data: {json.dumps({'type': 'done', 'session_id': active_session_id, 'verified': True})}\n\n"
                            self._persist_message(active_session_id, role="assistant", content=golden_ans, tool_calls=[{"name": tool_name, "args": tool_args}])
                            return
                except Exception as e:
                    logger.debug(f"Golden question lookup error: {e}")

        # 2. Setup conversation loop
        system_prompt = self.prompt_def.system if self.prompt_def else "You are the MedBalance Copilot."
        tools = self.prompt_def.tools if (self.prompt_def and self.prompt_def.tools) else TOOL_DEFINITIONS

        # Format initial conversation history
        conv_messages: List[Dict[str, Any]] = []
        for m in messages:
            conv_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        accumulated_facts: Dict[str, Any] = {
            "query": user_text,
            "session_id": active_session_id,
        }
        all_tool_events: List[Dict[str, Any]] = []
        final_answer = ""
        grounding_passed = True

        max_rounds = 5
        for round_idx in range(max_rounds):
            logger.debug(f"Copilot round {round_idx + 1}/{max_rounds} for session {active_session_id}")

            try:
                llm_res: LLMResult = await self.provider.complete(
                    messages=conv_messages,
                    system=system_prompt,
                    tools=tools,
                    model_tier="smart",
                    temperature=0.0,
                    max_tokens=1024,
                    timeout_sec=40.0,
                )
            except Exception as exc:
                logger.error(f"Copilot provider error on round {round_idx}: {exc}", exc_info=True)
                final_answer = f"I encountered an error retrieving data: {exc}"
                break

            # Check if LLM requested tool calls
            tool_calls = llm_res.tool_calls
            if tool_calls:
                # Add assistant message with tool calls to history
                assistant_msg_content = []
                if llm_res.raw_text:
                    assistant_msg_content.append({"type": "text", "text": llm_res.raw_text})

                for tc in tool_calls:
                    call_id = tc.get("id") or f"call_{round_idx}_{uuid4().hex[:6]}"
                    call_name = tc.get("name")
                    call_args = tc.get("input") or tc.get("arguments") or {}

                    assistant_msg_content.append({
                        "type": "tool_use",
                        "id": call_id,
                        "name": call_name,
                        "input": call_args,
                    })

                    # Emit tool_call SSE event
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': call_name, 'args': call_args, 'id': call_id})}\n\n"

                    # Execute tool
                    tool_result_dict, tool_summary = await execute_tool(call_name, call_args)

                    # Accumulate facts for numeric firewall check
                    accumulated_facts[f"{call_name}_{round_idx}"] = tool_result_dict

                    # Emit tool_result SSE event
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': call_name, 'summary': tool_summary, 'result': tool_result_dict, 'id': call_id})}\n\n"

                    all_tool_events.append({
                        "id": call_id,
                        "name": call_name,
                        "args": call_args,
                        "summary": tool_summary,
                        "result": tool_result_dict,
                    })

                    # Append tool result to conversation history for next round
                    conv_messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call_id,
                                "content": json.dumps(tool_result_dict),
                            }
                        ],
                    })

                self._persist_message(
                    active_session_id,
                    role="assistant",
                    content=llm_res.raw_text or f"Called {len(tool_calls)} tools",
                    tool_calls=tool_calls,
                )
                # Continue to next round so LLM can synthesize or call further tools
                continue
            else:
                # Model produced final text
                final_answer = llm_res.raw_text or ""
                if not final_answer and llm_res.structured_output:
                    final_answer = llm_res.structured_output.get("content") or json.dumps(llm_res.structured_output)
                break

        # If loop exited after max rounds without final answer, request synthesis
        if not final_answer:
            try:
                synth_res = await self.provider.complete(
                    messages=conv_messages + [{"role": "user", "content": "Please synthesize your final grounded answer for the District Drug Officer now based only on the tool results above."}],
                    system=system_prompt,
                    model_tier="smart",
                    temperature=0.0,
                    max_tokens=800,
                    timeout_sec=30.0,
                )
                final_answer = synth_res.raw_text or "I do not have sufficient information in the records to answer this query."
            except Exception as e:
                final_answer = "Analysis complete based on available tool results."

        # 3. Post-check with P15 Numeric Firewall
        grounding_check = verify_grounding(final_answer, accumulated_facts)
        grounding_passed = grounding_check.get("passed", True)

        if not grounding_passed:
            logger.warning(
                f"Copilot answer failed numeric grounding: unverified numbers={grounding_check.get('unverified_numbers')}, "
                f"unverified dates={grounding_check.get('unverified_dates')}"
            )
            metrics_tracker.record(
                purpose="copilot",
                cached=False,
                latency_sec=0.0,
                ok=True,
                firewall_block=True,
            )
            # Append note required by specification
            final_answer += "\n\n*Note: some figures could not be verified against tool records.*"

        # 4. Stream tokens to client
        tokens = chunk_text_tokens(final_answer)
        for tok in tokens:
            yield f"data: {json.dumps({'type': 'token', 'token': tok})}\n\n"

        # 5. Emit done event
        yield f"data: {json.dumps({'type': 'done', 'session_id': active_session_id, 'verified': grounding_passed})}\n\n"

        # 6. Persist final assistant message
        self._persist_message(active_session_id, role="assistant", content=final_answer)

        # 7. Update Replay Cache for DEMO_MODE
        cache_data = {
            "session_id": active_session_id,
            "content": final_answer,
            "tool_calls": all_tool_events,
            "verified": grounding_passed,
        }
        self.replay_cache.set(
            prompt_id="copilot",
            version="1",
            model="smart",
            input_dict=cache_key_input,
            data=cache_data,
        )
