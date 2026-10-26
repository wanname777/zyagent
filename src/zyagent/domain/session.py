from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .messages import Message, new_id, now


@dataclass(frozen=True)
class Session:
    id: str
    messages: Tuple[Message, ...]
    created_at: str
    updated_at: str
    parent_session_id: Optional[str] = None
    branch_message_id: Optional[str] = None
    summary: Optional[str] = None
    summary_through_message_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        session_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        branch_message_id: Optional[str] = None,
    ) -> "Session":
        timestamp = now()
        return cls(
            id=session_id or new_id(),
            messages=(),
            created_at=timestamp,
            updated_at=timestamp,
            parent_session_id=parent_session_id,
            branch_message_id=branch_message_id,
        )

    def append(self, message: Message) -> "Session":
        return replace(
            self,
            messages=(*self.messages, message),
            updated_at=now(),
        )

    def message_index(self, message_id: str) -> int:
        for index, message in enumerate(self.messages):
            if message.id == message_id:
                return index
        raise ValueError(f"Message not found: {message_id}")

    def branch(
        self, message_id: str, new_session_id: Optional[str] = None
    ) -> "Session":
        branch_index = self.message_index(message_id)
        inherited_summary = self.summary
        inherited_summary_through = self.summary_through_message_id
        if inherited_summary_through is not None:
            summary_index = self.message_index(inherited_summary_through)
            if summary_index > branch_index:
                inherited_summary = None
                inherited_summary_through = None

        timestamp = now()
        return Session(
            id=new_session_id or new_id(),
            messages=self.messages[: branch_index + 1],
            created_at=timestamp,
            updated_at=timestamp,
            parent_session_id=self.id,
            branch_message_id=message_id,
            summary=inherited_summary,
            summary_through_message_id=inherited_summary_through,
        )

    def with_summary(self, text: str, through_message_id: str) -> "Session":
        self.message_index(through_message_id)
        return replace(
            self,
            summary=text,
            summary_through_message_id=through_message_id,
            updated_at=now(),
        )

    def context_messages(self) -> Tuple[Message, ...]:
        if self.summary_through_message_id is None:
            return self.messages
        summary_index = self.message_index(self.summary_through_message_id)
        return self.messages[summary_index + 1 :]
