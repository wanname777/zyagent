from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from zyagent.application.ports import ModelSettings
from zyagent.domain.context import Context
from zyagent.domain.messages import AssistantMessage, ConversationSummary, Decision
from zyagent.domain.session import Session


class QueueModelClient:
    def __init__(self, *responses: Any) -> None:
        self.responses: Deque[Any] = deque(responses)
        self.contexts: List[Context[Any]] = []
        self.settings: List[ModelSettings] = []

    def generate(self, context: Context[Any], settings: ModelSettings) -> Any:
        self.contexts.append(context)
        self.settings.append(settings)
        if not self.responses:
            raise AssertionError("No queued model response")
        response = self.responses.popleft()
        if not isinstance(response, context.output_type):
            raise AssertionError(
                f"Expected {context.output_type.__name__}, got {type(response).__name__}"
            )
        return response


class MemorySessionStore:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}

    def list(self) -> List[Session]:
        return sorted(self.sessions.values(), key=lambda session: session.created_at)

    def load(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def save(self, session: Session) -> None:
        self.sessions[session.id] = session


class EchoTool:
    name = "echo"
    description = "Echo a text value."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, arguments: Dict[str, Any]) -> str:
        return str(arguments["text"])


def assistant(text: str = "") -> AssistantMessage:
    return AssistantMessage.create(text=text)


def allow() -> Decision:
    return Decision(allowed=True, reason="")


def summary(text: str) -> ConversationSummary:
    return ConversationSummary(text=text)


def temporary_store_path(tmp_path: Path) -> Path:
    return tmp_path / "sessions.jsonl"
