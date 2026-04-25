"""User path handling tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from archivestudio.core.config import paths as paths_module


def test_user_config_dir_raises_instead_of_falling_back_to_tmp(monkeypatch, tmp_path: Path) -> None:
    blocked_path = tmp_path / "blocked-config"
    monkeypatch.setattr(
        paths_module,
        "_dirs",
        SimpleNamespace(
            user_config_dir=str(blocked_path),
            user_data_dir=str(tmp_path / "data"),
            user_log_dir=str(tmp_path / "logs"),
        ),
    )

    def raise_permission_error(self, parents=False, exist_ok=False):  # noqa: ARG001
        raise PermissionError("permission denied")

    monkeypatch.setattr(paths_module.Path, "mkdir", raise_permission_error)

    with pytest.raises(paths_module.PathAccessError):
        paths_module.user_config_dir()
