from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, List, Optional, Protocol, TypeVar

from zyagent.domain.context import Context
from zyagent.domain.session import Session

T = TypeVar("T")


class Effort(str, Enum):
    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


@dataclass(frozen=True)
class ModelSettings:
    model: str
    effort: Effort = Effort.MEDIUM
    temperature: Optional[float] = None


class ModelClient(Protocol, Generic[T]):
    def generate(self, context: Context[T], settings: ModelSettings) -> T: ...


class SessionStore(Protocol):
    def list(self) -> List[Session]: ...

    def load(self, session_id: str) -> Optional[Session]: ...

    def save(self, session: Session) -> None: ...
