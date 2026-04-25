"""Shared helpers for project ingestion."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from archivestudio.core.models import Page
from archivestudio.core.project import IMAGES_SUBDIR, Project


log = logging.getLogger(__name__)

_NATURAL_SORT_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class ImportedPage:
    """Information about a newly imported page."""

    page_id: str
    sequence: int
    image_path: str


@dataclass(frozen=True)
class ImportResult:
    """Summary of an import operation."""

    pages: list[ImportedPage]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def natural_sort_key(value: str) -> list[int | str]:
    """Sort strings in a human-friendly way, e.g. 2 before 10."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in _NATURAL_SORT_RE.split(value)
        if part
    ]


def next_page_sequence(session: Session) -> int:
    """Return the next available 1-based page sequence."""
    current_max = session.execute(select(func.max(Page.sequence))).scalar_one()
    if current_max is None:
        return 1
    return int(current_max) + 1


def build_project_image_name(sequence: int, suffix: str) -> str:
    """Return the canonical project-local image filename."""
    normalized_suffix = suffix.lower()
    if not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"
    return f"page_{sequence:04d}{normalized_suffix}"


def project_image_relative_path(filename: str) -> str:
    return Path(IMAGES_SUBDIR, filename).as_posix()


def project_image_absolute_path(project: Project, filename: str) -> Path:
    return project.images_dir / filename


def create_page_row(
    session: Session,
    *,
    sequence: int,
    image_path: str,
    source_type: str | None,
    notes: str | None = None,
) -> Page:
    """Insert and flush a page row so its ID is immediately available."""
    page = Page(
        sequence=sequence,
        image_path=image_path,
        source_type=source_type,
        notes=notes,
    )
    session.add(page)
    session.flush()
    return page


def rollback_files(paths: Iterable[Path]) -> None:
    """Best-effort cleanup for files created during a failed import."""
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            log.warning("Failed to remove staged import file %s", path, exc_info=True)
