from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_dotenv(path: Path) -> None:
    """Load a small, shell-like .env file without replacing exported values."""
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid .env entry at {path}:{line_number}")

        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _ENVIRONMENT_NAME.fullmatch(name):
            raise ValueError(
                f"Invalid environment variable name at {path}:{line_number}"
            )
        try:
            values = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as error:
            raise ValueError(f"Invalid .env value at {path}:{line_number}") from error
        if len(values) > 1:
            raise ValueError(f"Unquoted whitespace at {path}:{line_number}")
        os.environ.setdefault(name, values[0] if values else "")
