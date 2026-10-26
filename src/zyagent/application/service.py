from __future__ import annotations

from typing import Dict, List, Optional

from zyagent.domain.context import Context
from zyagent.domain.messages import (
    AssistantMessage,
    ConversationSummary,
    ToolResult,
    UserMessage,
)
from zyagent.domain.roles import Assistant, ToolCallReviewer
from zyagent.domain.session import Session
from zyagent.domain.tool import Tool

from .ports import ModelClient, ModelSettings, SessionStore


class SessionNotFoundError(LookupError):
    pass


class AgentService:
    def __init__(
        self,
        model_client: ModelClient,
        session_store: SessionStore,
        assistant: Assistant,
        reviewer: ToolCallReviewer,
        assistant_settings: ModelSettings,
        reviewer_settings: ModelSettings,
        compression_settings: ModelSettings,
        max_iterations: int = 8,
        auto_compress_after: Optional[int] = None,
        keep_recent_after_compression: int = 12,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if auto_compress_after is not None and auto_compress_after < 2:
            raise ValueError("auto_compress_after must be at least 2")
        if keep_recent_after_compression < 1:
            raise ValueError("keep_recent_after_compression must be at least 1")
        if (
            auto_compress_after is not None
            and keep_recent_after_compression >= auto_compress_after
        ):
            raise ValueError(
                "keep_recent_after_compression must be below auto_compress_after"
            )
        self.model_client = model_client
        self.session_store = session_store
        self.assistant = assistant
        self.reviewer = reviewer
        self.assistant_settings = assistant_settings
        self.reviewer_settings = reviewer_settings
        self.compression_settings = compression_settings
        self.max_iterations = max_iterations
        self.auto_compress_after = auto_compress_after
        self.keep_recent_after_compression = keep_recent_after_compression
        self.tools: Dict[str, Tool] = {tool.name: tool for tool in assistant.tools}

    def create_session(self, session_id: Optional[str] = None) -> Session:
        session = Session.create(session_id)
        self.session_store.save(session)
        return session

    def list_sessions(self) -> List[Session]:
        return self.session_store.list()

    def get_session(self, session_id: str) -> Session:
        session = self.session_store.load(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return session

    def branch_session(
        self,
        session_id: str,
        message_id: str,
        new_session_id: Optional[str] = None,
    ) -> Session:
        branch = self.get_session(session_id).branch(message_id, new_session_id)
        self.session_store.save(branch)
        return branch

    def compress_session(self, session_id: str, keep_recent: int = 8) -> Session:
        if keep_recent < 1:
            raise ValueError("keep_recent must be at least 1")
        session = self.get_session(session_id)
        active_messages = session.context_messages()
        if len(active_messages) <= keep_recent:
            return session

        messages_to_summarize = active_messages[:-keep_recent]
        context = Context(
            instruction=(
                "Summarize the conversation history for future model calls. "
                "Preserve user goals, decisions, constraints, unresolved work, "
                "important tool results, and exact identifiers. Do not invent facts."
            ),
            tools=(),
            messages=messages_to_summarize,
            output_type=ConversationSummary,
            summary=session.summary,
        )
        result = self.model_client.generate(context, self.compression_settings)
        compressed = session.with_summary(
            result.text,
            messages_to_summarize[-1].id,
        )
        self.session_store.save(compressed)
        return compressed

    def send_message(self, session_id: str, text: str) -> AssistantMessage:
        session = self.get_session(session_id).append(UserMessage.create(text))
        self.session_store.save(session)
        last_response: Optional[AssistantMessage] = None

        for _ in range(self.max_iterations):
            if (
                self.auto_compress_after is not None
                and len(session.context_messages()) >= self.auto_compress_after
            ):
                session = self.compress_session(
                    session.id,
                    keep_recent=self.keep_recent_after_compression,
                )
            response = self.model_client.generate(
                self.assistant.context(session),
                self.assistant_settings,
            )
            session = session.append(response)
            self.session_store.save(session)
            last_response = response
            if not response.tool_calls:
                return response

            for call in response.tool_calls:
                decision = self.model_client.generate(
                    self.reviewer.context(session, call),
                    self.reviewer_settings,
                )
                if not decision.allowed:
                    result = ToolResult.create(
                        call.id,
                        decision.reason or "Tool call rejected by reviewer.",
                        is_error=True,
                    )
                else:
                    result = self._execute_tool(call.id, call.name, call.arguments)
                session = session.append(result)
                self.session_store.save(session)

        if last_response is None:
            raise RuntimeError("Agent loop ended without a model response")
        return last_response

    def _execute_tool(self, call_id: str, name: str, arguments: dict) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.create(
                call_id,
                f"Unknown tool: {name}",
                is_error=True,
            )
        try:
            return ToolResult.create(call_id, tool.execute(arguments))
        except Exception as error:
            return ToolResult.create(call_id, str(error), is_error=True)
