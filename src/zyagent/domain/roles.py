from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

from .context import Context
from .messages import AssistantMessage, Decision, ToolCall
from .session import Session
from .tool import Tool


@dataclass(frozen=True)
class Assistant:
    instruction: str
    tools: Tuple[Tool, ...]

    def context(self, session: Session) -> Context[AssistantMessage]:
        return Context(
            instruction=self.instruction,
            tools=self.tools,
            messages=session.context_messages(),
            output_type=AssistantMessage,
            summary=session.summary,
        )


@dataclass(frozen=True)
class ToolCallReviewer:
    instruction: str

    def context(self, session: Session, call: ToolCall) -> Context[Decision]:
        subject = json.dumps(
            {"id": call.id, "name": call.name, "arguments": call.arguments},
            ensure_ascii=False,
            sort_keys=True,
        )
        return Context(
            instruction=(
                f"{self.instruction}\n\n"
                "Return whether this tool call is allowed and a concise reason.\n"
                f"Tool call under review: {subject}"
            ),
            tools=(),
            messages=session.context_messages(),
            output_type=Decision,
            summary=session.summary,
        )
