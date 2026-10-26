from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zyagent.adapters.tools.bash import BashTool, ToolExecutionError


class BashToolTests(unittest.TestCase):
    def test_executes_allowlisted_read_only_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hello.txt").write_text("hello", encoding="utf-8")
            tool = BashTool(root=root)

            output = tool.execute({"command": "cat hello.txt"})

            self.assertEqual(output, "hello")

    def test_rejects_shell_operators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = BashTool(root=Path(directory))

            with self.assertRaises(ToolExecutionError):
                tool.execute({"command": "ls; rm -rf ."})

    def test_rejects_non_allowlisted_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = BashTool(root=Path(directory))

            with self.assertRaises(ToolExecutionError):
                tool.execute({"command": "rm file.txt"})

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = BashTool(root=Path(directory))

            with self.assertRaises(ToolExecutionError):
                tool.execute({"command": "cat ../secret.txt"})

    def test_rejects_mutating_find_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = BashTool(root=Path(directory))

            with self.assertRaises(ToolExecutionError):
                tool.execute({"command": "find . -delete"})


if __name__ == "__main__":
    unittest.main()
