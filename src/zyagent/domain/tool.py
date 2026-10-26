from __future__ import annotations

from typing import Any, Dict, Protocol


class Tool(Protocol):
    name: str
    description: str
    parameters: Dict[str, Any]

    def execute(self, arguments: Dict[str, Any]) -> str: ...
