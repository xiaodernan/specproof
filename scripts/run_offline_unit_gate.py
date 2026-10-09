"""Run the offline unit suite (no e2e, no slow markers) and exit with its code.

Invoked by the dev gate so the marker expression does not have to survive
PowerShell argument quoting: ``Start-Process -ArgumentList`` re-splits array
elements on whitespace, which turns ``-m "not e2e and not slow"`` into
``-m not e2e and not slow`` and pytest then reports ``file or directory not
found: e2e`` after collecting 0 items -- a green-looking log that ran nothing.
"""

from __future__ import annotations

import sys

import pytest


def main() -> int:
    return pytest.main(
        ["-q", "--no-header", "-m", "not e2e and not slow", "tests/unit"]
    )


if __name__ == "__main__":
    sys.exit(main())
