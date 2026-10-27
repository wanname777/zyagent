from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

from tests.fakes import MemorySessionStore, QueueModelClient, assistant, summary
from zyagent.application.ports import Effort, ModelSettings
from zyagent.application.service import AgentService
from zyagent.domain.messages import UserMessage
from zyagent.domain.roles import Assistant, ToolCallReviewer
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


if __name__ == "__main__":
    unittest.main()
