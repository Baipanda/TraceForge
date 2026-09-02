"""Pytest defaults: keep tests fast and offline."""

from __future__ import annotations

import os


def pytest_configure() -> None:
    os.environ.setdefault("TRACEFORGE_MEMORY_EMBEDDING_PROVIDER", "none")
