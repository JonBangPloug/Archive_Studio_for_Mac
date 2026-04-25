"""Cross-platform per-user paths via platformdirs.

These are the *user-scoped* locations — settings, log files, shared prompt
library. Project data lives inside each project directory, not here.
"""

from __future__ import annotations

from pathlib import Path

from platformdirs import PlatformDirs

_APP_NAME = "ArchiveStudio"
_APP_AUTHOR = "ArchiveStudio"

_dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR, roaming=False)


class PathAccessError(RuntimeError):
    """Raised when ArchiveStudio cannot access one of its user-scoped folders."""


def user_config_dir() -> Path:
    """Per-user config directory. Created on access."""
    return _ensure_dir(Path(_dirs.user_config_dir), fallback_name="config")


def user_data_dir() -> Path:
    """Per-user data directory (e.g. library, caches). Created on access."""
    return _ensure_dir(Path(_dirs.user_data_dir), fallback_name="data")


def user_log_dir() -> Path:
    """Per-user log directory. Created on access."""
    return _ensure_dir(Path(_dirs.user_log_dir), fallback_name="logs")


def user_log_file() -> Path:
    """Canonical rotating log file path."""
    return user_log_dir() / "archivestudio.log"


def user_settings_file() -> Path:
    """TOML settings file (provider choices and preferences; no API keys)."""
    return user_config_dir() / "settings.toml"


def user_library_dir() -> Path:
    """User-scoped prompt/preset/model-config library root."""
    return _ensure_dir(user_data_dir() / "library", fallback_name="library")


def default_projects_dir() -> Path:
    """Default user-facing location for automatically created projects."""
    documents_dir = Path.home() / "Documents"
    if documents_dir.exists():
        return _ensure_dir(documents_dir / "ArchiveStudio Projects", fallback_name="projects")
    return _ensure_dir(user_data_dir() / "projects", fallback_name="projects")


def _ensure_dir(path: Path, *, fallback_name: str) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError as exc:
        raise PathAccessError(
            "ArchiveStudio could not access its user "
            f"{fallback_name} directory at {path}. "
            "Check the folder permissions and try again."
        ) from exc
