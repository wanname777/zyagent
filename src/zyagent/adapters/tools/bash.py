from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional


class ToolExecutionError(RuntimeError):
    pass


class BashTool:
    name = "bash"
    description = (
        "Run one read-only command inside the configured workspace. "
        "Shell operators, command substitution, and non-allowlisted programs are rejected."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "A single read-only command without shell operators.",
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    }
    DEFAULT_ALLOWED_COMMANDS = frozenset(
        {
            "cat",
            "find",
            "git",
            "grep",
            "head",
            "ls",
            "pwd",
            "rg",
            "sed",
            "tail",
            "wc",
        }
    )
    FORBIDDEN_TOKENS = (
        ";",
        "&&",
        "||",
        "|",
        ">",
        "<",
        "`",
        "$(",
        "\n",
        "\r",
    )
    SAFE_GIT_SUBCOMMANDS = frozenset({"diff", "log", "rev-parse", "show", "status"})
    UNSAFE_FIND_OPTIONS = (
        "-delete",
        "-exec",
        "-execdir",
        "-fls",
        "-fprintf",
        "-fprint",
        "-ok",
        "-okdir",
    )

    def __init__(
        self,
        root: Path,
        allowed_commands: Optional[FrozenSet[str]] = None,
        timeout_seconds: float = 10.0,
        max_output_chars: int = 20_000,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.allowed_commands = allowed_commands or self.DEFAULT_ALLOWED_COMMANDS
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def execute(self, arguments: Dict[str, Any]) -> str:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ToolExecutionError("command must be a non-empty string")
        if any(token in command for token in self.FORBIDDEN_TOKENS):
            raise ToolExecutionError(
                "shell operators and substitutions are not allowed"
            )
        try:
            argv = shlex.split(command)
        except ValueError as error:
            raise ToolExecutionError(f"invalid command: {error}") from error
        if not argv:
            raise ToolExecutionError("command must not be empty")

        executable = Path(argv[0]).name
        if executable not in self.allowed_commands:
            raise ToolExecutionError(f"command is not allowlisted: {executable}")
        if executable == "git":
            if len(argv) < 2 or argv[1] not in self.SAFE_GIT_SUBCOMMANDS:
                raise ToolExecutionError("git subcommand is not allowlisted")
        if executable == "find" and any(
            argument.startswith(self.UNSAFE_FIND_OPTIONS) for argument in argv[1:]
        ):
            raise ToolExecutionError("mutating find options are not allowed")
        if executable == "sed" and any(
            argument == "-i" or argument.startswith("-i") for argument in argv[1:]
        ):
            raise ToolExecutionError("in-place sed editing is not allowed")
        self._validate_paths(executable, argv[1:])

        try:
            completed = subprocess.run(
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as error:
            raise ToolExecutionError(
                f"command is not installed: {executable}"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ToolExecutionError(
                f"command timed out after {self.timeout_seconds:g}s"
            ) from error

        output = completed.stdout
        if completed.stderr:
            output = f"{output}\n{completed.stderr}" if output else completed.stderr
        output = output.strip()
        if len(output) > self.max_output_chars:
            output = output[: self.max_output_chars] + "\n[output truncated]"
        if completed.returncode != 0:
            raise ToolExecutionError(
                output or f"command exited with status {completed.returncode}"
            )
        return output

    def _validate_paths(self, executable: str, arguments: list) -> None:
        start = 1 if executable == "git" else 0
        for argument in arguments[start:]:
            if argument.startswith("-"):
                continue
            if not (
                argument.startswith(("/", "~", "."))
                or "/" in argument
                or "\\" in argument
            ):
                continue
            candidate = Path(argument).expanduser()
            if not candidate.is_absolute():
                candidate = self.root / candidate
            try:
                candidate.resolve().relative_to(self.root)
            except ValueError as error:
                raise ToolExecutionError(
                    f"path escapes the workspace: {argument}"
                ) from error
