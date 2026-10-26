from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4


class WorkspacePathError(ValueError):
    pass


class _WorkspaceTool:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def resolve(self, path_value: Any) -> Path:
        if not isinstance(path_value, str) or not path_value.strip():
            raise WorkspacePathError("path must be a non-empty string")
        candidate = (self.root / path_value).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise WorkspacePathError("path must stay inside the workspace") from error
        return candidate


class ReadFileTool(_WorkspaceTool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the configured workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the workspace.",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, root: Path, max_chars: int = 40_000) -> None:
        super().__init__(root)
        self.max_chars = max_chars

    def execute(self, arguments: Dict[str, Any]) -> str:
        path = self.resolve(arguments.get("path"))
        if not path.is_file():
            raise FileNotFoundError(f"file not found: {path.relative_to(self.root)}")
        content = path.read_text(encoding="utf-8")
        if len(content) > self.max_chars:
            return content[: self.max_chars] + "\n[content truncated]"
        return content


class WriteFileTool(_WorkspaceTool):
    name = "write_file"
    description = (
        "Create or replace one UTF-8 text file inside the configured workspace. "
        "The write is atomic."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the workspace.",
            },
            "content": {
                "type": "string",
                "description": "Complete UTF-8 file content.",
            },
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def execute(self, arguments: Dict[str, Any]) -> str:
        path = self.resolve(arguments.get("path"))
        content = arguments.get("content")
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return f"wrote {len(content)} characters to {path.relative_to(self.root)}"
