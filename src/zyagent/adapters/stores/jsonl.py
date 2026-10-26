from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from zyagent.domain.messages import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolResult,
    UserMessage,
)
from zyagent.domain.session import Session


class JsonlSessionStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def list(self) -> List[Session]:
        with self._lock:
            sessions = list(self._read_all().values())
        return sorted(sessions, key=lambda session: session.created_at)

    def load(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._read_all().get(session_id)

    def save(self, session: Session) -> None:
        with self._lock:
            sessions = self._read_all()
            sessions[session.id] = session
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                for item in sorted(
                    sessions.values(), key=lambda value: value.created_at
                ):
                    handle.write(
                        json.dumps(
                            _session_to_dict(item),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)

    def _read_all(self) -> Dict[str, Session]:
        if not self.path.exists():
            return {}
        sessions: Dict[str, Session] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    session = _session_from_dict(json.loads(line))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise ValueError(
                        f"Invalid session record at line {line_number}: {error}"
                    ) from error
                sessions[session.id] = session
        return sessions


def _tool_call_to_dict(call: ToolCall) -> Dict[str, Any]:
    return {"id": call.id, "name": call.name, "arguments": call.arguments}


def _tool_call_from_dict(data: Dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=data["id"],
        name=data["name"],
        arguments=dict(data["arguments"]),
    )


def _message_to_dict(message: Message) -> Dict[str, Any]:
    if isinstance(message, UserMessage):
        return {
            "type": "user",
            "id": message.id,
            "text": message.text,
            "created_at": message.created_at,
        }
    if isinstance(message, AssistantMessage):
        return {
            "type": "assistant",
            "id": message.id,
            "text": message.text,
            "tool_calls": [_tool_call_to_dict(call) for call in message.tool_calls],
            "created_at": message.created_at,
        }
    if isinstance(message, ToolResult):
        return {
            "type": "tool_result",
            "id": message.id,
            "tool_call_id": message.tool_call_id,
            "content": message.content,
            "is_error": message.is_error,
            "created_at": message.created_at,
        }
    raise TypeError(f"Unsupported message type: {type(message).__name__}")


def _message_from_dict(data: Dict[str, Any]) -> Message:
    message_type = data["type"]
    if message_type == "user":
        return UserMessage(
            id=data["id"],
            text=data["text"],
            created_at=data["created_at"],
        )
    if message_type == "assistant":
        return AssistantMessage(
            id=data["id"],
            text=data.get("text", ""),
            tool_calls=tuple(
                _tool_call_from_dict(call) for call in data.get("tool_calls", [])
            ),
            created_at=data["created_at"],
        )
    if message_type == "tool_result":
        return ToolResult(
            id=data["id"],
            tool_call_id=data["tool_call_id"],
            content=data["content"],
            is_error=bool(data.get("is_error", False)),
            created_at=data["created_at"],
        )
    raise ValueError(f"Unknown message type: {message_type}")


def _session_to_dict(session: Session) -> Dict[str, Any]:
    return {
        "id": session.id,
        "messages": [_message_to_dict(message) for message in session.messages],
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "parent_session_id": session.parent_session_id,
        "branch_message_id": session.branch_message_id,
        "summary": session.summary,
        "summary_through_message_id": session.summary_through_message_id,
    }


def _session_from_dict(data: Dict[str, Any]) -> Session:
    return Session(
        id=data["id"],
        messages=tuple(_message_from_dict(item) for item in data["messages"]),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        parent_session_id=data.get("parent_session_id"),
        branch_message_id=data.get("branch_message_id"),
        summary=data.get("summary"),
        summary_through_message_id=data.get("summary_through_message_id"),
    )
