from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zyagent.config import load_dotenv


class DotenvTests(unittest.TestCase):
    def test_loads_values_and_supports_quotes_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                'PLAIN=value\nQUOTED="two words"\nexport EMPTY=\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(path)

                self.assertEqual(os.environ["PLAIN"], "value")
                self.assertEqual(os.environ["QUOTED"], "two words")
                self.assertEqual(os.environ["EMPTY"], "")

    def test_does_not_replace_exported_environment_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("MODEL=file-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"MODEL": "shell-value"}, clear=True):
                load_dotenv(path)

                self.assertEqual(os.environ["MODEL"], "shell-value")

    def test_rejects_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("not an assignment\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_dotenv(path)


if __name__ == "__main__":
    unittest.main()
