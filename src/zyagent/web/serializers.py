from __future__ import annotations

from typing import Any, Dict

from zyagent.domain.messages import AssistantMessage, ToolResult, UserMessage
from zyagent.domain.session import Session


def message_payload(message: object) -> Dict[str, Any]:
    base = {
        "id": message.id,
        "created_at": message.created_at,
    }
    if isinstance(message, UserMessage):
        return {
            **base,
            "type": "user",
            "text": message.text,
        }
    if isinstance(message, AssistantMessage):
        return {
            **base,
            "type": "assistant",
            "text": message.text,
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in message.tool_calls
            ],
        }
    if isinstance(message, ToolResult):
        return {
            **base,
            "type": "tool_result",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
            "is_error": message.is_error,
        }
    raise TypeError(f"Unsupported message type: {type(message).__name__}")


def session_payload(session: Session, include_messages: bool = True) -> Dict[str, Any]:
    payload = {
        "id": session.id,
        "title": _session_title(session),
        "preview": _session_preview(session),
        "message_count": len(session.messages),
        "active_message_count": len(session.context_messages()),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "parent_session_id": session.parent_session_id,
        "branch_message_id": session.branch_message_id,
        "summary": session.summary,
        "summary_through_message_id": session.summary_through_message_id,
    }
    if include_messages:
        payload["messages"] = [message_payload(message) for message in session.messages]
    return payload


def _session_title(session: Session) -> str:
    for message in session.messages:
        if isinstance(message, UserMessage) and message.text.strip():
            return _truncate(message.text.strip(), 24)
    return "新会话"


def _session_preview(session: Session) -> str:
    for message in reversed(session.messages):
        if (
            isinstance(message, (UserMessage, AssistantMessage))
            and message.text.strip()
        ):
            return _truncate(message.text.strip(), 44)
        if isinstance(message, ToolResult) and message.content.strip():
            return _truncate(message.content.strip(), 44)
    return "等待第一条消息"


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"
