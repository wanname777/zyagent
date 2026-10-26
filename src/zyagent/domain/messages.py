from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Tuple, Union
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

    @classmethod
    def create(cls, name: str, arguments: Dict[str, Any]) -> "ToolCall":
        return cls(id=new_id(), name=name, arguments=dict(arguments))


@dataclass(frozen=True)
class UserMessage:
    id: str
    text: str
    created_at: str = field(default_factory=now)

    @classmethod
    def create(cls, text: str) -> "UserMessage":
        return cls(id=new_id(), text=text)


@dataclass(frozen=True)
class AssistantMessage:
    id: str
    text: str = ""
    tool_calls: Tuple[ToolCall, ...] = ()
    created_at: str = field(default_factory=now)

    @classmethod
    def create(
        cls, text: str = "", tool_calls: Tuple[ToolCall, ...] = ()
    ) -> "AssistantMessage":
        return cls(id=new_id(), text=text, tool_calls=tuple(tool_calls))


@dataclass(frozen=True)
class ToolResult:
    id: str
    tool_call_id: str
    content: str
    is_error: bool = False
    created_at: str = field(default_factory=now)

    @classmethod
    def create(
        cls, tool_call_id: str, content: str, is_error: bool = False
    ) -> "ToolResult":
        return cls(
            id=new_id(),
            tool_call_id=tool_call_id,
            content=content,
            is_error=is_error,
        )


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class ConversationSummary:
    text: str


Message = Union[UserMessage, AssistantMessage, ToolResult]
