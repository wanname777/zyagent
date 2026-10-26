from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zyagent.adapters.tools.files import ReadFileTool, WorkspacePathError, WriteFileTool


class FileToolTests(unittest.TestCase):
    def test_write_then_read_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = WriteFileTool(root)
            reader = ReadFileTool(root)

            result = writer.execute({"path": "notes/item.txt", "content": "hello"})

            self.assertIn("notes/item.txt", result)
            self.assertEqual(
                reader.execute({"path": "notes/item.txt"}),
                "hello",
            )

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = WriteFileTool(Path(directory))

            with self.assertRaises(WorkspacePathError):
                writer.execute({"path": "../escape.txt", "content": "no"})


if __name__ == "__main__":
    unittest.main()
