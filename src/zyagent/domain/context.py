from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, Tuple, Type, TypeVar

from .messages import Message
from .tool import Tool

T = TypeVar("T")


@dataclass(frozen=True)
class Context(Generic[T]):
    instruction: str
    tools: Tuple[Tool, ...]
    messages: Tuple[Message, ...]
    output_type: Type[T]
    summary: Optional[str] = None
