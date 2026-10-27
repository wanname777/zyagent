from __future__ import annotations

import unittest

from tests.fakes import (
    EchoTool,
    MemorySessionStore,
    QueueModelClient,
    allow,
    assistant,
    summary,
)
from zyagent.application.ports import Effort, ModelSettings
from zyagent.application.service import AgentService
from zyagent.domain.messages import AssistantMessage, ToolCall, ToolResult, UserMessage
from zyagent.domain.roles import Assistant, ToolCallReviewer
from zyagent.domain.session import Session


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemorySessionStore()
        self.assistant_settings = ModelSettings("assistant-model", Effort.MEDIUM)
        self.reviewer_settings = ModelSettings("reviewer-model", Effort.LOW)
        self.compression_settings = ModelSettings("summary-model", Effort.LOW)

    def service(self, model: QueueModelClient) -> AgentService:
        return AgentService(
            model_client=model,
            session_store=self.store,
            assistant=Assistant("Help the user.", (EchoTool(),)),
            reviewer=ToolCallReviewer("Reject unsafe tool calls."),
            assistant_settings=self.assistant_settings,
            reviewer_settings=self.reviewer_settings,
            compression_settings=self.compression_settings,
            max_iterations=4,
        )

    def test_send_message_runs_reviewed_tool_and_continues_loop(self) -> None:
        call = ToolCall.create("echo", {"text": "done"})
        model = QueueModelClient(
            AssistantMessage.create(tool_calls=(call,)),
            allow(),
            assistant("The tool said done."),
        )
        service = self.service(model)
        session = service.create_session("session")

        response = service.send_message(session.id, "echo done")
        saved = self.store.load(session.id)

        self.assertEqual(response.text, "The tool said done.")
        self.assertEqual(
            [type(message) for message in saved.messages],
            [UserMessage, AssistantMessage, ToolResult, AssistantMessage],
        )
        self.assertEqual(saved.messages[2].content, "done")
        self.assertEqual(
            model.settings,
            [
                self.assistant_settings,
                self.reviewer_settings,
                self.assistant_settings,
            ],
        )

    def test_rejected_tool_call_is_returned_to_model_as_error(self) -> None:
        call = ToolCall.create("echo", {"text": "no"})
        model = QueueModelClient(
            AssistantMessage.create(tool_calls=(call,)),
            type(allow())(allowed=False, reason="policy denied"),
            assistant("I cannot do that."),
        )
        service = self.service(model)
        session = service.create_session("session")

        service.send_message(session.id, "do it")
        result = self.store.load(session.id).messages[2]

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.is_error)
        self.assertEqual(result.content, "policy denied")

    def test_reviewer_context_excludes_pending_assistant_tool_call(self) -> None:
        call = ToolCall.create("echo", {"text": "done"})
        model = QueueModelClient(
            AssistantMessage.create(tool_calls=(call,)),
            allow(),
            assistant("done"),
        )
        service = self.service(model)
        session = service.create_session("session")

        service.send_message(session.id, "echo done")

        reviewer_context = model.contexts[1]
        self.assertEqual(
            [type(message) for message in reviewer_context.messages],
            [UserMessage],
        )

    def test_multiple_tool_calls_use_same_valid_reviewer_history(self) -> None:
        first = ToolCall.create("echo", {"text": "one"})
        second = ToolCall.create("echo", {"text": "two"})
        model = QueueModelClient(
            AssistantMessage.create(tool_calls=(first, second)),
            allow(),
            allow(),
            assistant("finished"),
        )
        service = self.service(model)
        session = service.create_session("session")

        service.send_message(session.id, "echo twice")
        saved = self.store.load(session.id)

        self.assertEqual(
            [type(message) for message in saved.messages],
            [
                UserMessage,
                AssistantMessage,
                ToolResult,
                ToolResult,
                AssistantMessage,
            ],
        )
        self.assertEqual(model.contexts[1].messages, model.contexts[2].messages)
        self.assertEqual(
            [type(message) for message in model.contexts[2].messages],
            [UserMessage],
        )

    def test_resume_repairs_interrupted_tool_calls_before_model_request(self) -> None:
        first = ToolCall.create("echo", {"text": "one"})
        second = ToolCall.create("echo", {"text": "two"})
        interrupted = (
            Session.create("session")
            .append(UserMessage.create("start"))
            .append(AssistantMessage.create(tool_calls=(first, second)))
            .append(ToolResult.create(first.id, "one"))
            .append(UserMessage.create("retry"))
        )
        self.store.save(interrupted)
        model = QueueModelClient(assistant("recovered"))
        service = self.service(model)

        response = service.resume_session(interrupted.id)
        saved = self.store.load(interrupted.id)

        self.assertEqual(response.text, "recovered")
        self.assertEqual(
            [type(message) for message in saved.messages],
            [
                UserMessage,
                AssistantMessage,
                ToolResult,
                ToolResult,
                UserMessage,
                AssistantMessage,
            ],
        )
        repaired_result = saved.messages[3]
        self.assertTrue(repaired_result.is_error)
        self.assertEqual(repaired_result.tool_call_id, second.id)

    def test_branch_session_is_independent_from_parent(self) -> None:
        model = QueueModelClient(assistant("parent answer"))
        service = self.service(model)
        parent = service.create_session("parent")
        service.send_message(parent.id, "question")
        branch_point = self.store.load(parent.id).messages[0].id

        branch = service.branch_session(parent.id, branch_point, "branch")
        self.store.save(branch.append(UserMessage.create("branch only")))

        self.assertEqual(len(self.store.load(parent.id).messages), 2)
        self.assertEqual(len(self.store.load(branch.id).messages), 2)

    def test_compression_summarizes_old_messages_but_keeps_full_history(self) -> None:
        model = QueueModelClient(summary("condensed history"))
        service = self.service(model)
        session = service.create_session("session")
        for index in range(8):
            session = session.append(UserMessage.create(f"message {index}"))
        self.store.save(session)

        compressed = service.compress_session(session.id, keep_recent=3)

        self.assertEqual(len(compressed.messages), 8)
        self.assertEqual(compressed.summary, "condensed history")
        self.assertEqual(compressed.context_messages(), compressed.messages[-3:])
        self.assertEqual(model.contexts[0].output_type.__name__, "ConversationSummary")


if __name__ == "__main__":
    unittest.main()
