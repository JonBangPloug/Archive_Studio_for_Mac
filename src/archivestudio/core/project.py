"""Project lifecycle: create and open.

A *project* is a directory on disk containing:

* ``project.db`` — SQLite database with all metadata and text versions.
* ``images/``   — page images (copied in during ingest, Stage 1).
* ``exports/``  — user-triggered exports (Stage 6).
* ``task_runs/`` — JSON provenance artifacts for AI task runs.

The :class:`Project` dataclass is the value object passed around the rest of
the app. It bundles the directory path, the engine, and a sessionmaker so
callers can open short-lived transactional sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import re

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from archivestudio.core.db import create_all, make_engine, make_sessionmaker, session_scope
from archivestudio.core.models import SCHEMA_VERSION, ProjectInfo


log = logging.getLogger(__name__)


PROJECT_DB_FILENAME = "project.db"
IMAGES_SUBDIR = "images"
EXPORTS_SUBDIR = "exports"
TASK_RUNS_SUBDIR = "task_runs"


class ProjectError(Exception):
    """Base exception for project lifecycle failures."""


class ProjectExistsError(ProjectError):
    """Raised when asked to create a project in a non-empty directory."""


class ProjectNotFoundError(ProjectError):
    """Raised when asked to open a project that has no ``project.db``."""


class ProjectSchemaError(ProjectError):
    """Raised when a project's schema version is incompatible."""


@dataclass
class Project:
    """Handle to an open project."""

    root: Path
    name: str
    engine: Engine
    sessionmaker: sessionmaker[Session]

    @property
    def db_path(self) -> Path:
        return self.root / PROJECT_DB_FILENAME

    @property
    def images_dir(self) -> Path:
        return self.root / IMAGES_SUBDIR

    @property
    def exports_dir(self) -> Path:
        return self.root / EXPORTS_SUBDIR

    @property
    def task_runs_dir(self) -> Path:
        return self.root / TASK_RUNS_SUBDIR

    def session(self):
        """Context manager for a transactional session."""
        return session_scope(self.sessionmaker)

    def close(self) -> None:
        """Dispose of the underlying engine."""
        self.engine.dispose()


def _ensure_project_dirs(root: Path) -> None:
    (root / IMAGES_SUBDIR).mkdir(parents=True, exist_ok=True)
    (root / EXPORTS_SUBDIR).mkdir(parents=True, exist_ok=True)
    (root / TASK_RUNS_SUBDIR).mkdir(parents=True, exist_ok=True)


def create_project(root: Path, name: str) -> Project:
    """Create a new project rooted at ``root``.

    The directory must not already exist, or must be empty. Raises
    :class:`ProjectExistsError` otherwise.
    """
    root = Path(root)
    if root.exists():
        if any(root.iterdir()):
            raise ProjectExistsError(f"Directory is not empty: {root}")
    else:
        root.mkdir(parents=True)

    _ensure_project_dirs(root)

    db_path = root / PROJECT_DB_FILENAME
    engine = make_engine(db_path)
    create_all(engine)

    factory = make_sessionmaker(engine)
    with session_scope(factory) as s:
        s.add(ProjectInfo(name=name, schema_version=SCHEMA_VERSION))

    log.info("Created project %r at %s", name, root)
    return Project(root=root, name=name, engine=engine, sessionmaker=factory)


def create_project_with_available_name(parent: Path, suggested_name: str) -> Project:
    """Create a project under ``parent`` using a safe non-conflicting name."""
    project_name = safe_project_name(suggested_name)
    project_root = available_project_root(parent, project_name)
    return create_project(project_root, name=project_root.name)


def safe_project_name(value: str) -> str:
    """Return a user-friendly filesystem-safe project name."""
    cleaned = re.sub(r"[\s/\\:]+", " ", value).strip()
    cleaned = re.sub(r"[^\w .()#&+-]+", "", cleaned).strip(" .")
    return cleaned or "Archive Project"


def available_project_root(parent: Path, suggested_name: str) -> Path:
    """Return a project path, adding a numeric suffix when needed."""
    parent = Path(parent)
    base_name = safe_project_name(suggested_name)
    candidate = parent / base_name
    if _project_root_is_available(candidate):
        return candidate

    for index in range(2, 1000):
        candidate = parent / f"{base_name} {index}"
        if _project_root_is_available(candidate):
            return candidate
    raise ProjectExistsError(f"Could not find an available project name in {parent}")


def rename_project(project: Project, new_name: str) -> Project:
    """Rename a project's display name without moving its folder."""
    cleaned_name = safe_project_name(new_name)
    with project.session() as session:
        info = session.execute(select(ProjectInfo)).scalar_one_or_none()
        if info is None:  # pragma: no cover - defensive
            raise ProjectError(f"Project DB has no project_info row: {project.db_path}")
        info.name = cleaned_name
    project.name = cleaned_name
    log.info("Renamed project at %s to %r", project.root, cleaned_name)
    return project


def _project_root_is_available(root: Path) -> bool:
    if not root.exists():
        return True
    return root.is_dir() and not any(root.iterdir())


def open_project(root: Path) -> Project:
    """Open an existing project at ``root``."""
    root = Path(root)
    db_path = root / PROJECT_DB_FILENAME
    if not db_path.exists():
        raise ProjectNotFoundError(f"No project database at {db_path}")

    _ensure_project_dirs(root)

    engine = make_engine(db_path)
    factory = make_sessionmaker(engine)

    with session_scope(factory) as s:
        info = s.execute(select(ProjectInfo)).scalar_one_or_none()
        if info is None:
            raise ProjectError(f"Project DB has no project_info row: {db_path}")
        if info.schema_version != SCHEMA_VERSION:
            raise ProjectSchemaError(
                f"Project schema {info.schema_version} != app schema {SCHEMA_VERSION}"
            )
        name = info.name

    log.info("Opened project %r at %s", name, root)
    return Project(root=root, name=name, engine=engine, sessionmaker=factory)
