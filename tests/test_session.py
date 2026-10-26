from __future__ import annotations

import unittest

from zyagent.domain.messages import AssistantMessage, UserMessage
from zyagent.domain.session import Session


class SessionTests(unittest.TestCase):
    def test_branch_copies_history_through_selected_message(self) -> None:
        first = UserMessage.create("first")
        second = AssistantMessage.create("second")
        third = UserMessage.create("third")
        original = Session.create("original").append(first).append(second).append(third)

        branch = original.branch(second.id, new_session_id="branch")

        self.assertEqual(branch.id, "branch")
        self.assertEqual(branch.parent_session_id, original.id)
        self.assertEqual(branch.branch_message_id, second.id)
        self.assertEqual(branch.messages, (first, second))
        self.assertEqual(original.messages, (first, second, third))

    def test_branch_after_summary_inherits_valid_summary(self) -> None:
        messages = tuple(UserMessage.create(str(index)) for index in range(5))
        session = Session.create("original")
        for message in messages:
            session = session.append(message)
        session = session.with_summary("old context", messages[2].id)

        branch = session.branch(messages[3].id, new_session_id="branch")

        self.assertEqual(branch.summary, "old context")
        self.assertEqual(branch.summary_through_message_id, messages[2].id)

    def test_branch_before_summary_drops_summary(self) -> None:
        messages = tuple(UserMessage.create(str(index)) for index in range(5))
        session = Session.create("original")
        for message in messages:
            session = session.append(message)
        session = session.with_summary("old context", messages[3].id)

        branch = session.branch(messages[1].id, new_session_id="branch")

        self.assertIsNone(branch.summary)
        self.assertIsNone(branch.summary_through_message_id)

    def test_context_messages_exclude_summarized_prefix(self) -> None:
        messages = tuple(UserMessage.create(str(index)) for index in range(5))
        session = Session.create("original")
        for message in messages:
            session = session.append(message)
        session = session.with_summary("old context", messages[2].id)

        self.assertEqual(session.context_messages(), messages[3:])


if __name__ == "__main__":
    unittest.main()
