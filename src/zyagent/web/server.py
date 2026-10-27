from __future__ import annotations

import json
import mimetypes
import re
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import unquote, urlparse

from zyagent.application.service import AgentService, SessionNotFoundError

from .serializers import message_payload, session_payload

_SESSION_ROUTE = re.compile(
    r"^/api/sessions/(?P<session_id>[^/]+)"
    r"(?P<action>/messages|/branches|/compress|/resume)?$"
)
_MAX_BODY_BYTES = 1_000_000


class ZyagentWebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: Tuple[str, int],
        service: AgentService,
        static_root: Path,
    ) -> None:
        self.service = service
        self.static_root = static_root
        super().__init__(address, ZyagentRequestHandler)


class ZyagentRequestHandler(BaseHTTPRequestHandler):
    server: ZyagentWebServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "model": self.server.service.assistant_settings.model,
                },
            )
            return
        if path == "/api/sessions":
            sessions = [
                session_payload(session, include_messages=False)
                for session in reversed(self.server.service.list_sessions())
            ]
            self._send_json(HTTPStatus.OK, {"sessions": sessions})
            return
        route = _SESSION_ROUTE.fullmatch(path)
        if route and route.group("action") is None:
            self._handle_api(
                lambda: {
                    "session": session_payload(
                        self.server.service.get_session(
                            unquote(route.group("session_id"))
                        )
                    )
                }
            )
            return
        if path.startswith("/api/"):
            self._send_error(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "API route not found.",
            )
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/sessions":
            self._handle_api(self._create_session, success=HTTPStatus.CREATED)
            return
        route = _SESSION_ROUTE.fullmatch(path)
        if not route or route.group("action") is None:
            self._send_error(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "API route not found.",
            )
            return

        session_id = unquote(route.group("session_id"))
        action = route.group("action")
        if action == "/messages":
            self._handle_api(lambda: self._send_message(session_id))
        elif action == "/branches":
            self._handle_api(
                lambda: self._branch_session(session_id),
                success=HTTPStatus.CREATED,
            )
        elif action == "/compress":
            self._handle_api(lambda: self._compress_session(session_id))
        elif action == "/resume":
            self._handle_api(lambda: self._resume_session(session_id))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _create_session(self) -> Dict[str, Any]:
        body = self._read_json()
        requested_id = body.get("id")
        if requested_id is not None and not isinstance(requested_id, str):
            raise ValueError("id must be a string")
        session = self.server.service.create_session(requested_id)
        return {"session": session_payload(session)}

    def _send_message(self, session_id: str) -> Dict[str, Any]:
        body = self._read_json()
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        response = self.server.service.send_message(session_id, text.strip())
        session = self.server.service.get_session(session_id)
        return {
            "response": message_payload(response),
            "session": session_payload(session),
        }

    def _branch_session(self, session_id: str) -> Dict[str, Any]:
        body = self._read_json()
        message_id = body.get("message_id")
        new_session_id = body.get("new_session_id")
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("message_id must be a non-empty string")
        if new_session_id is not None and not isinstance(new_session_id, str):
            raise ValueError("new_session_id must be a string")
        branch = self.server.service.branch_session(
            session_id,
            message_id,
            new_session_id,
        )
        return {"session": session_payload(branch)}

    def _compress_session(self, session_id: str) -> Dict[str, Any]:
        body = self._read_json()
        keep_recent = body.get("keep_recent", 12)
        if not isinstance(keep_recent, int):
            raise ValueError("keep_recent must be an integer")
        session = self.server.service.compress_session(session_id, keep_recent)
        return {"session": session_payload(session)}

    def _resume_session(self, session_id: str) -> Dict[str, Any]:
        response = self.server.service.resume_session(session_id)
        session = self.server.service.get_session(session_id)
        return {
            "response": message_payload(response),
            "session": session_payload(session),
        }

    def _handle_api(
        self,
        operation: Any,
        success: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        try:
            payload = operation()
        except SessionNotFoundError as error:
            self._send_error(
                HTTPStatus.NOT_FOUND,
                "session_not_found",
                str(error),
            )
            return
        except ValueError as error:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                str(error),
            )
            return
        except RuntimeError as error:
            self._send_error(
                HTTPStatus.BAD_GATEWAY,
                "agent_error",
                str(error),
            )
            return
        self._send_json(success, payload)

    def _read_json(self) -> Dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length < 0 or length > _MAX_BODY_BYTES:
            raise ValueError("Request body is too large")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _serve_static(self, request_path: str) -> None:
        relative_path = (
            "index.html" if request_path == "/" else request_path.lstrip("/")
        )
        candidate = (self.server.static_root / relative_path).resolve()
        try:
            candidate.relative_to(self.server.static_root.resolve())
        except ValueError:
            self._send_error(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "File not found.",
            )
            return
        if not candidate.is_file():
            candidate = self.server.static_root / "index.html"
        content_type, _ = mimetypes.guess_type(candidate.name)
        self._send_bytes(
            HTTPStatus.OK,
            candidate.read_bytes(),
            content_type or "application/octet-stream",
        )

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
    ) -> None:
        self._send_json(
            status,
            {"error": {"code": code, "message": message}},
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)


def create_web_server(
    service: AgentService,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ZyagentWebServer:
    static_root = Path(__file__).with_name("static")
    return ZyagentWebServer((host, port), service, static_root)


def run_web_server(
    service: AgentService,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    server = create_web_server(service, host, port)
    actual_host, actual_port = server.server_address
    display_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    url = f"http://{display_host}:{actual_port}"
    print(f"zyagent web: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping zyagent web.")
    finally:
        server.server_close()
