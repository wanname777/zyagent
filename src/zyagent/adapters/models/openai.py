from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Protocol, TypeVar, cast

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

T = TypeVar("T")


class ModelResponseError(RuntimeError):
    pass


class JsonTransport(Protocol):
    def request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]: ...


class UrllibJsonTransport:
    def request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return cast(
                    Dict[str, Any],
                    json.loads(response.read().decode("utf-8")),
                )
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise ModelResponseError(
                f"Model API returned HTTP {error.code}: {body[:1000]}"
            ) from error
        except urllib.error.URLError as error:
            raise ModelResponseError(
                f"Model API request failed: {error.reason}"
            ) from error


class OpenAICompatibleModelClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        organization: Optional[str] = None,
        timeout_seconds: float = 60.0,
        transport: Optional[JsonTransport] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.organization = organization
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrllibJsonTransport()

    def generate(self, context: Context[T], settings: ModelSettings) -> T:
        if not self.api_key:
            raise ModelResponseError(
                "OPENAI_API_KEY is required for model-backed commands"
            )
        payload = self._payload(context, settings)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        response = self.transport.request(
            f"{self.base_url}/chat/completions",
            headers,
            payload,
            self.timeout_seconds,
        )
        return self._parse_response(context, response)

    def _payload(
        self, context: Context[Any], settings: ModelSettings
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._system_instruction(context),
                },
                *[self._message(message) for message in context.messages],
            ],
        }
        if settings.effort != Effort.OFF:
            payload["reasoning_effort"] = settings.effort.value
        if settings.temperature is not None:
            payload["temperature"] = settings.temperature
        if context.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in context.tools
            ]
            payload["tool_choice"] = "auto"
        if context.output_type in (Decision, ConversationSummary):
            payload["response_format"] = {"type": "json_object"}
        return payload

    @staticmethod
    def _system_instruction(context: Context[Any]) -> str:
        parts = [context.instruction]
        if context.summary:
            parts.append(f"Earlier conversation summary:\n{context.summary}")
        if context.output_type is Decision:
            parts.append(
                'Respond only as JSON: {"allowed": boolean, "reason": string}.'
            )
        elif context.output_type is ConversationSummary:
            parts.append('Respond only as JSON: {"text": string}.')
        return "\n\n".join(parts)

    @staticmethod
    def _message(message: Any) -> Dict[str, Any]:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.text}
        if isinstance(message, AssistantMessage):
            result: Dict[str, Any] = {
                "role": "assistant",
                "content": message.text or None,
            }
            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    }
                    for call in message.tool_calls
                ]
            return result
        if isinstance(message, ToolResult):
            content = message.content
            if message.is_error:
                content = f"ERROR: {content}"
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": content,
            }
        raise TypeError(f"Unsupported message type: {type(message).__name__}")

    @staticmethod
    def _parse_response(context: Context[T], response: Dict[str, Any]) -> T:
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelResponseError(
                "Model response has no assistant message"
            ) from error

        if context.output_type is AssistantMessage:
            calls = []
            for item in message.get("tool_calls") or []:
                function = item["function"]
                raw_arguments = function.get("arguments", "{}")
                arguments = (
                    raw_arguments
                    if isinstance(raw_arguments, dict)
                    else json.loads(raw_arguments)
                )
                calls.append(
                    ToolCall(
                        id=item.get("id")
                        or ToolCall.create(function["name"], arguments).id,
                        name=function["name"],
                        arguments=arguments,
                    )
                )
            return cast(
                T,
                AssistantMessage.create(
                    text=message.get("content") or "",
                    tool_calls=tuple(calls),
                ),
            )

        data = _parse_json_object(message.get("content"))
        if context.output_type is Decision:
            return cast(
                T,
                Decision(
                    allowed=bool(data["allowed"]),
                    reason=str(data.get("reason", "")),
                ),
            )
        if context.output_type is ConversationSummary:
            return cast(T, ConversationSummary(text=str(data["text"])))
        raise ModelResponseError(
            f"Unsupported output type: {context.output_type.__name__}"
        )


def _parse_json_object(content: Any) -> Dict[str, Any]:
    if not isinstance(content, str):
        raise ModelResponseError("Expected model response content to be text")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ModelResponseError("Model returned invalid JSON") from error
    if not isinstance(data, dict):
        raise ModelResponseError("Model returned JSON that is not an object")
    return data
