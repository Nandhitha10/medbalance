"""FastAPI router for interactive Copilot chat SSE stream."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from genai_service.agent import CopilotAgent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Copilot"])

# Global agent instance (overridable in tests)
copilot_agent = CopilotAgent()


class ChatMessage(BaseModel):
    role: str = Field(description="Role of message author (user, assistant, system, tool)")
    content: str = Field(description="Textual content of the message")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional tool invocations")


class CopilotChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(description="Sequential conversation messages")
    session_id: Optional[str] = Field(default=None, description="Optional persistent chat session identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier (defaults to district_drug_officer)")
    facility_id: Optional[str] = Field(default=None, description="Facility context identifier (e.g. H1, H4, W0)")


@router.post("/copilot/chat")
async def copilot_chat(req: CopilotChatRequest) -> StreamingResponse:
    """Stream interactive district copilot response via Server-Sent Events (SSE).

    Emits SSE events:
    - tool_call: {type: "tool_call", name: str, args: dict, id: str}
    - tool_result: {type: "tool_result", name: str, summary: str, result: dict, id: str}
    - token: {type: "token", token: str}
    - done: {type: "done", session_id: str, verified: bool}
    """
    if not req.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages list must not be empty",
        )

    # Convert Pydantic models to dicts
    dict_messages = [
        {"role": m.role, "content": m.content, "tool_calls": m.tool_calls}
        for m in req.messages
    ]

    event_generator = copilot_agent.run_copilot_stream(
        messages=dict_messages,
        session_id=req.session_id,
        user_id=req.user_id,
        facility_id=req.facility_id,
    )

    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/copilot/history/{session_id}")
async def get_session_history(session_id: str) -> Dict[str, Any]:
    """Retrieve persisted message history for a given session."""
    history = copilot_agent._get_history(session_id)
    return {
        "session_id": session_id,
        "message_count": len(history),
        "messages": history,
    }

