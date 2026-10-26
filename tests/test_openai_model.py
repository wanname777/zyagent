from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List

from tests.fakes import EchoTool
from zyagent.adapters.models.openai import OpenAICompatibleModelClient
from zyagent.application.ports import Effort, ModelSettings
from zyagent.domain.context import Context
from zyagent.domain.messages import (
    AssistantMessage,
    ConversationSummary,
    Decision,
    ToolCall,
    ToolResult,
    UserMessage,
)


class RecordingTransport:
    def __init__(self, response: Dict[str, Any]) -> None:
        self.response = response
        self.requests: List[Dict[str, Any]] = []

    def request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return self.response


class OpenAICompatibleModelClientTests(unittest.TestCase):
    def test_translates_context_and_parses_assistant_tool_calls(self) -> None:
        transport = RecordingTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": "checking",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "echo",
                                        "arguments": '{"text":"hello"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleModelClient(
            api_key="secret",
            base_url="https://example.test/v1",
            transport=transport,
        )
        call = ToolCall(id="old-call", name="echo", arguments={"text": "old"})
        context = Context(
            instruction="Help.",
            tools=(EchoTool(),),
            messages=(
                UserMessage(id="u1", text="hello", created_at="time"),
                AssistantMessage(id="a1", tool_calls=(call,), created_at="time"),
                ToolResult(
                    id="r1",
                    tool_call_id=call.id,
                    content="old",
                    created_at="time",
                ),
            ),
            output_type=AssistantMessage,
            summary="Earlier facts.",
        )

        result = client.generate(
            context,
            ModelSettings("gpt-test", Effort.LOW, temperature=0.2),
        )
        payload = transport.requests[0]["payload"]

        self.assertEqual(result.text, "checking")
        self.assertEqual(result.tool_calls[0].id, "call-1")
        self.assertEqual(result.tool_calls[0].arguments, {"text": "hello"})
        self.assertIn("Earlier facts.", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][2]["tool_calls"][0]["id"], "old-call")
        self.assertEqual(payload["messages"][3]["role"], "tool")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["tools"][0]["function"]["name"], "echo")

    def test_parses_structured_decision(self) -> None:
        transport = RecordingTransport(
            {"choices": [{"message": {"content": '{"allowed":false,"reason":"no"}'}}]}
        )
        client = OpenAICompatibleModelClient(
            api_key="secret",
            transport=transport,
        )
        context = Context(
            instruction="Review.",
            tools=(),
            messages=(),
            output_type=Decision,
        )

        result = client.generate(context, ModelSettings("gpt-test"))

        self.assertEqual(result, Decision(allowed=False, reason="no"))
        self.assertEqual(
            transport.requests[0]["payload"]["response_format"],
            {"type": "json_object"},
        )

    def test_parses_summary_from_json(self) -> None:
        transport = RecordingTransport(
            {"choices": [{"message": {"content": json.dumps({"text": "short"})}}]}
        )
        client = OpenAICompatibleModelClient(
            api_key="secret",
            transport=transport,
        )
        context = Context(
            instruction="Summarize.",
            tools=(),
            messages=(),
            output_type=ConversationSummary,
        )

        result = client.generate(context, ModelSettings("gpt-test", Effort.OFF))

        self.assertEqual(result, ConversationSummary("short"))
        self.assertNotIn(
            "reasoning_effort",
            transport.requests[0]["payload"],
        )


if __name__ == "__main__":
    unittest.main()
