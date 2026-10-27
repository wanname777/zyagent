from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple
from unittest.mock import patch

from tests.fakes import MemorySessionStore, QueueModelClient, assistant, summary
from zyagent.application.ports import Effort, ModelSettings
from zyagent.application.service import AgentService
from zyagent.domain.messages import AssistantMessage, ToolCall, ToolResult, UserMessage
from zyagent.domain.roles import Assistant, ToolCallReviewer
from zyagent.web.exports import session_html, session_markdown
from zyagent.web.server import create_web_server


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = QueueModelClient()
        self.store = MemorySessionStore()
        settings = ModelSettings("test-model", Effort.OFF)
        self.service = AgentService(
            model_client=self.model,
            session_store=self.store,
            assistant=Assistant("Help.", ()),
            reviewer=ToolCallReviewer("Review."),
            assistant_settings=settings,
            reviewer_settings=settings,
            compression_settings=settings,
        )
        self.server = create_web_server(self.service, "127.0.0.1", 0)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self,
        method: str,
        path: str,
        payload: Dict[str, Any] | None = None,
    ) -> Tuple[int, Dict[str, Any]]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_session_message_and_branch_workflow(self) -> None:
        self.model.responses.append(assistant("hello from web"))
        status, created = self.request("POST", "/api/sessions", {})
        self.assertEqual(status, 201)
        session_id = created["session"]["id"]

        status, sent = self.request(
            "POST",
            f"/api/sessions/{session_id}/messages",
            {"text": "hello"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(sent["response"]["text"], "hello from web")
        self.assertEqual(sent["session"]["message_count"], 2)

        message_id = sent["session"]["messages"][0]["id"]
        status, branched = self.request(
            "POST",
            f"/api/sessions/{session_id}/branches",
            {"message_id": message_id},
        )
        self.assertEqual(status, 201)
        self.assertEqual(branched["session"]["parent_session_id"], session_id)
        self.assertEqual(branched["session"]["message_count"], 1)

        status, sessions = self.request("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(len(sessions["sessions"]), 2)

    def test_returns_structured_errors(self) -> None:
        status, payload = self.request("GET", "/api/sessions/missing")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "session_not_found")

    def test_compresses_context_without_removing_history(self) -> None:
        session = self.service.create_session("compress-me")
        for index in range(4):
            session = session.append(UserMessage.create(f"message {index}"))
        self.store.save(session)
        self.model.responses.append(summary("condensed context"))

        status, payload = self.request(
            "POST",
            "/api/sessions/compress-me/compress",
            {"keep_recent": 2},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["session"]["summary"], "condensed context")
        self.assertEqual(payload["session"]["active_message_count"], 2)
        self.assertEqual(payload["session"]["message_count"], 4)

    def test_resumes_a_session_with_an_unanswered_user_message(self) -> None:
        session = self.service.create_session("resume-me")
        self.store.save(session.append(UserMessage.create("please continue")))
        self.model.responses.append(assistant("continued"))

        status, payload = self.request(
            "POST",
            "/api/sessions/resume-me/resume",
            {},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["response"]["text"], "continued")
        self.assertEqual(payload["session"]["message_count"], 2)

    def test_serves_application_shell_and_health_metadata(self) -> None:
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
        status, health = self.request("GET", "/api/health")

        self.assertIn('id="app"', html)
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["model"], "test-model")

    def test_exports_session_as_branded_html_and_markdown(self) -> None:
        session = self.service.create_session("export-me")
        self.store.save(session.append(UserMessage.create("需求农场: market report")))

        html_request = urllib.request.Request(
            self.base_url + "/api/sessions/export-me/export?format=html"
        )
        with urllib.request.urlopen(html_request, timeout=3) as response:
            html_body = response.read().decode("utf-8")
            disposition = response.headers["Content-Disposition"]
        markdown_request = urllib.request.Request(
            self.base_url + "/api/sessions/export-me/export?format=md"
        )
        with urllib.request.urlopen(markdown_request, timeout=3) as response:
            markdown_body = response.read().decode("utf-8")

        self.assertIn("Generated by", html_body)
        self.assertIn("https://github.com/wanname777/zyagent", html_body)
        self.assertIn("attachment;", disposition)
        self.assertIn("zyagent-market-report-export-m.html", disposition)
        self.assertIn("# 需求农场: market report", markdown_body)
        self.assertIn("Generated by [zyagent]", markdown_body)
        self.assertIn("未验证草稿", html_body)
        self.assertIn("未验证草稿", markdown_body)

    def test_research_requires_matching_tool_evidence_and_a_final_response(
        self,
    ) -> None:
        call = ToolCall.create("market_signals", {"query": "workflow pricing"})
        statuses = {
            "hacker_news": "ok",
            "github": "no_results",
            "google_news": "no_results",
        }
        item = {
            "source": "hacker_news",
            "url": "https://news.ycombinator.com/item?id=123",
        }
        cases = [
            ("collected", {**statuses}, [item, item], False, True),
            ("partial", {**statuses, "github": "error"}, [item], False, True),
            ("insufficient", dict.fromkeys(statuses, "no_results"), [], False, True),
            ("failed", statuses, [item], True, True),
            ("failed", {"hacker_news": {}}, [], False, True),
            ("incomplete", statuses, [item], False, False),
        ]
        for index, (expected, coverage, items, is_error, complete) in enumerate(cases):
            with self.subTest(expected=expected, coverage=coverage):
                session = self.service.create_session(f"research-{index}")
                session = session.append(UserMessage.create("需求农场：workflow"))
                session = session.append(AssistantMessage.create(tool_calls=(call,)))
                session = session.append(
                    ToolResult.create(
                        call.id,
                        json.dumps({"source_status": coverage, "items": items}),
                        is_error=is_error,
                    )
                )
                if complete:
                    session = session.append(assistant("市场结论仍需访谈验证。"))
                self.store.save(session)
                status, payload = self.request("GET", f"/api/sessions/{session.id}")
                self.assertEqual(status, 200)
                research = payload["session"]["research"]
                self.assertEqual(research["status"], expected)
                self.assertEqual(
                    research["ready"], expected in {"collected", "partial"}
                )
                if expected == "collected":
                    self.assertEqual(research["evidence_count"], 1)
                    compressed = session.with_summary("摘要", session.messages[-2].id)
                    self.assertIn("已采集公开信号", session_html(compressed))

        orphan = self.service.create_session("orphan")
        orphan = orphan.append(UserMessage.create("需求农场：workflow"))
        orphan = orphan.append(
            ToolResult.create(
                "unknown-call",
                json.dumps({"source_status": statuses, "items": [item]}),
            )
        ).append(assistant("这些数据不能算已采集证据。"))
        self.store.save(orphan)
        _, payload = self.request("GET", "/api/sessions/orphan")
        self.assertEqual(payload["session"]["research"]["status"], "unverified")
        self.assertEqual(payload["session"]["research"]["evidence_count"], 0)

    def test_research_rejects_invalid_tool_payloads(self) -> None:
        for index, content in enumerate(("not-json", "[]", "{}", '{"items": []}')):
            with self.subTest(content=content):
                call = ToolCall.create("market_signals", {"query": "workflow"})
                session = self.service.create_session(f"invalid-{index}")
                session = session.append(UserMessage.create("需求农场：workflow"))
                session = session.append(AssistantMessage.create(tool_calls=(call,)))
                session = session.append(ToolResult.create(call.id, content))
                session = session.append(assistant("需要重新采集。"))
                self.store.save(session)
                _, payload = self.request("GET", f"/api/sessions/{session.id}")
                self.assertEqual(payload["session"]["research"]["status"], "failed")

    def test_exports_redact_secrets_and_local_paths_but_keep_source_links(self) -> None:
        secret = "sample-secret-with-&-characters"
        session = self.service.create_session("redact")
        session = session.append(UserMessage.create("需求农场：workflow"))
        session = session.append(
            ToolResult.create(
                "file-call",
                f"{secret}\n/Users/test/workspace/.env\n"
                "file:///tmp/private-report.md\n"
                "https://example.com/home/pricing",
            )
        )
        session = session.append(
            assistant("Key: sk-0123456789abcdefghijklmnop\n/home/test/report.md")
        )
        session = session.with_summary(f"保留信息：{secret}", session.messages[0].id)
        with patch.dict(os.environ, {"OPENAI_API_KEY": secret}):
            for exporter in (session_html, session_markdown):
                with self.subTest(exporter=exporter.__name__):
                    content = exporter(session)
                    self.assertNotIn(secret, content)
                    self.assertNotIn("sample-secret-with-&amp;-characters", content)
                    self.assertNotIn("sk-0123456789abcdefghijklmnop", content)
                    self.assertNotIn("/Users/test/", content)
                    self.assertNotIn("/home/test/", content)
                    self.assertNotIn("file:///", content)
                    self.assertIn("https://example.com/home/pricing", content)
                    self.assertIn("[REDACTED]", content)
                    self.assertIn("[LOCAL_PATH]", content)
        self.assertIn(secret, session.messages[1].content)


if __name__ == "__main__":
    unittest.main()
