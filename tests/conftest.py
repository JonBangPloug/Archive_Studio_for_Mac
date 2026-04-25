"""Shared pytest fixtures.

Nothing here touches Qt; ``core`` tests run headless without PySide6's event
loop. UI tests (Stage 4+) will opt in via ``pytest-qt``'s ``qtbot``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_project_root(tmp_path: Path) -> Path:
    """Return an empty tmp directory suitable for ``create_project``."""
    root = tmp_path / "project"
    return root
