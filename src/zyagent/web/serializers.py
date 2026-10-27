from __future__ import annotations

import json
from typing import Any, Dict, Optional

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
    research = research_payload(session)
    if research is not None:
        payload["research"] = research
    if include_messages:
        payload["messages"] = [message_payload(message) for message in session.messages]
    return payload


def research_payload(session: Session) -> Optional[Dict[str, Any]]:
    first_user = next(
        (message for message in session.messages if isinstance(message, UserMessage)),
        None,
    )
    if first_user is None or not first_user.text.strip().startswith(
        ("需求农场：", "需求农场:")
    ):
        return None

    call_ids = {
        call.id
        for message in session.messages
        if isinstance(message, AssistantMessage)
        for call in message.tool_calls
        if call.name == "market_signals"
    }
    resolved_ids = set()
    source_status: Dict[str, str] = {}
    urls = set()
    failed = False
    for message in session.messages:
        if not isinstance(message, ToolResult) or message.tool_call_id not in call_ids:
            continue
        resolved_ids.add(message.tool_call_id)
        if message.is_error:
            failed = True
            continue
        try:
            result = json.loads(message.content)
        except (TypeError, ValueError):
            failed = True
            continue
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("source_status"), dict)
            or not isinstance(result.get("items"), list)
        ):
            failed = True
            continue
        statuses = result["source_status"]
        for source in ("hacker_news", "github", "google_news"):
            status = statuses.get(source)
            if not isinstance(status, str) or status not in {
                "ok",
                "no_results",
                "error",
            }:
                status = "error"
                failed = True
            if source_status.get(source) != "error":
                source_status[source] = status
        for item in result["items"]:
            if (
                isinstance(item, dict)
                and isinstance(item.get("source"), str)
                and statuses.get(item.get("source")) == "ok"
                and isinstance(item.get("url"), str)
                and item["url"].startswith(("https://", "http://"))
            ):
                urls.add(item["url"])
        failed = (
            failed or bool(result.get("errors")) or "error" in source_status.values()
        )

    last = session.messages[-1]
    response_complete = (
        isinstance(last, AssistantMessage)
        and not last.tool_calls
        and bool(last.text.strip())
    )
    if not call_ids:
        status, label = "unverified", "未验证草稿：尚未采集公开信号"
    elif call_ids != resolved_ids or not response_complete:
        status, label = "incomplete", "报告未完成：请继续回复或重试"
    elif not urls:
        if failed:
            status, label = "failed", "采集失败：没有可用证据，请重试"
        else:
            status, label = "insufficient", "证据不足：未找到可用公开信号"
    elif failed or "error" in source_status.values():
        status, label = "partial", "部分来源失败：报告包含覆盖缺口"
    else:
        status, label = "collected", "已采集公开信号：购买意愿仍需验证"
    return {
        "status": status,
        "label": label,
        "evidence_count": len(urls),
        "source_status": source_status,
        "ready": status in {"collected", "partial"},
        "note": "公开信号和关键词标签不等于真实购买意愿；定价建议需要访谈与预售验证。",
    }


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
