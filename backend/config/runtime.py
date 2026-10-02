"""Check the Python version required by the local backend."""

import sys
from typing import Optional, Sequence


def require_supported_python(version: Optional[Sequence[int]] = None) -> None:
    current = sys.version_info if version is None else version
    if tuple(current[:2]) < (3, 14):
        raise SystemExit("Kakei backend requires Python 3.14 or newer.")
