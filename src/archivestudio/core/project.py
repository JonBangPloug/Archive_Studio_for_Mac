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
from datetime import datetime
from pathlib import Path
import re
import sqlite3

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


@dataclass(frozen=True)
class ProjectSummary:
    """Lightweight project listing for picker UIs."""

    root: Path
    name: str
    modified_at: datetime | None


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


def project_root_from_selection(selection: Path) -> Path:
    """Resolve a user-selected folder or ``project.db`` file to a project root."""
    selection = Path(selection).expanduser()
    if selection.is_file():
        if selection.name == PROJECT_DB_FILENAME:
            candidate = selection.parent
        else:
            raise ProjectNotFoundError(_invalid_project_selection_message(selection))
    else:
        candidate = selection

    if (candidate / PROJECT_DB_FILENAME).is_file():
        return candidate

    if candidate.is_dir():
        child_roots = sorted(
            child
            for child in candidate.iterdir()
            if child.is_dir() and (child / PROJECT_DB_FILENAME).is_file()
        )
        if len(child_roots) == 1:
            return child_roots[0]
        if len(child_roots) > 1:
            raise ProjectNotFoundError(
                f"{candidate} contains more than one Archive Studio project folder. "
                "Please choose the specific project folder you want to open."
            )

    raise ProjectNotFoundError(_invalid_project_selection_message(selection))


def open_project_selection(selection: Path) -> Project:
    """Open a user-selected project folder, project DB, or unambiguous parent folder."""
    return open_project(project_root_from_selection(selection))


def discover_projects(parent: Path) -> list[ProjectSummary]:
    """Return valid Archive Studio project folders below ``parent`` for picker UIs."""
    parent = Path(parent).expanduser()
    candidates: list[Path] = []
    if (parent / PROJECT_DB_FILENAME).is_file():
        candidates.append(parent)
    if parent.is_dir():
        candidates.extend(
            child
            for child in parent.iterdir()
            if child.is_dir() and (child / PROJECT_DB_FILENAME).is_file()
        )

    summaries = [
        summary
        for candidate in candidates
        if (summary := project_summary(candidate)) is not None
    ]
    return sorted(
        summaries,
        key=lambda summary: (
            summary.modified_at is None,
            -(summary.modified_at.timestamp() if summary.modified_at else 0),
            summary.name.casefold(),
        ),
    )


def project_summary(root: Path) -> ProjectSummary | None:
    """Read minimal project metadata without opening/migrating the project."""
    root = Path(root).expanduser()
    db_path = root / PROJECT_DB_FILENAME
    if not db_path.is_file():
        return None
    try:
        with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT name FROM project_info LIMIT 1").fetchone()
    except sqlite3.Error:
        log.warning("Could not read project summary from %s", db_path, exc_info=True)
        return None
    if row is None or not str(row[0]).strip():
        return None

    try:
        modified_at = datetime.fromtimestamp(db_path.stat().st_mtime)
    except OSError:
        modified_at = None
    return ProjectSummary(root=root, name=str(row[0]), modified_at=modified_at)


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


def _invalid_project_selection_message(selection: Path) -> str:
    return (
        "This does not look like an Archive Studio project folder. "
        "Please choose a folder containing project.db."
    )


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
        if info.schema_version > SCHEMA_VERSION:
            raise ProjectSchemaError(
                f"Project schema {info.schema_version} != app schema {SCHEMA_VERSION}"
            )
        if info.schema_version < SCHEMA_VERSION:
            old_version = info.schema_version
            create_all(engine)
            info.schema_version = SCHEMA_VERSION
            log.info(
                "Migrated project schema at %s from %s to %s",
                db_path,
                old_version,
                SCHEMA_VERSION,
            )
        name = info.name

    log.info("Opened project %r at %s", name, root)
    return Project(root=root, name=name, engine=engine, sessionmaker=factory)
