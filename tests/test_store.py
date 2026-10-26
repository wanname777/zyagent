from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zyagent.adapters.stores.jsonl import JsonlSessionStore
from zyagent.domain.messages import AssistantMessage, ToolCall, ToolResult, UserMessage
from zyagent.domain.session import Session


class JsonlSessionStoreTests(unittest.TestCase):
    def test_round_trip_preserves_all_message_types_and_branch_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            call = ToolCall.create("echo", {"text": "hello"})
            session = (
                Session.create("child", parent_session_id="parent")
                .append(UserMessage.create("hello"))
                .append(AssistantMessage.create(tool_calls=(call,)))
                .append(ToolResult.create(call.id, "hello"))
            )
            session = session.with_summary("summary", session.messages[0].id)

            store.save(session)
            loaded = store.load("child")

            self.assertEqual(loaded, session)
            self.assertEqual(store.list(), [session])

    def test_save_replaces_existing_session_instead_of_duplicating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlSessionStore(Path(directory) / "sessions.jsonl")
            session = Session.create("one")
            store.save(session)
            store.save(session.append(UserMessage.create("new")))

            self.assertEqual(len(store.list()), 1)
            self.assertEqual(len(store.load("one").messages), 1)


if __name__ == "__main__":
    unittest.main()
