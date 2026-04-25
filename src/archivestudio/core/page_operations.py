"""Page-level project operations."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Literal
import uuid

from PIL import Image
from sqlalchemy import select

from archivestudio.core.models import Page
from archivestudio.core.project import Project


class PageOperationError(Exception):
    """Base exception for page-level project operations."""


class PageNotFoundError(PageOperationError):
    """Raised when a requested page does not exist."""


@dataclass(frozen=True)
class RotatedPage:
    page_id: str
    sequence: int
    image_path: str


@dataclass(frozen=True)
class DeletedPage:
    page_id: str
    sequence: int
    image_path: str


def delete_project_page(project: Project, *, page_id: str) -> DeletedPage:
    """Delete a page row and its dependent text versions from a project."""
    deleted_pages = delete_project_pages(project, page_ids=[page_id])
    return deleted_pages[0]


def rotate_project_pages(project: Project, *, page_ids: list[str]) -> list[RotatedPage]:
    """Rotate one or more project page images 90 degrees clockwise in place."""
    normalized_ids = list(dict.fromkeys(page_ids))
    if not normalized_ids:
        return []

    with project.session() as session:
        pages = session.execute(
            select(Page).where(Page.id.in_(normalized_ids)).order_by(Page.sequence)
        ).scalars().all()
        if len(pages) != len(normalized_ids):
            found_ids = {page.id for page in pages}
            missing = next(page_id for page_id in normalized_ids if page_id not in found_ids)
            raise PageNotFoundError(f"No page exists with id {missing}")

    rotated_files: list[tuple[Path, Path]] = []
    backup_paths: list[tuple[Path, Path]] = []
    rotated_pages: list[RotatedPage] = []

    try:
        for page in pages:
            image_path = project.root / page.image_path
            if not image_path.exists():
                raise PageOperationError(
                    f"Could not rotate page {page.sequence}: missing image {image_path}"
                )

            temp_path = _temporary_sibling_path(image_path)
            with Image.open(image_path) as image:
                rotated = image.rotate(-90, expand=True)
                rotated.save(temp_path)
                rotated.close()

            rotated_files.append((image_path, temp_path))
            rotated_pages.append(
                RotatedPage(
                    page_id=page.id,
                    sequence=page.sequence,
                    image_path=page.image_path,
                )
            )

        for image_path, temp_path in rotated_files:
            backup_path = image_path.with_name(
                f"{image_path.name}.rotate-backup-{uuid.uuid4().hex}"
            )
            image_path.replace(backup_path)
            backup_paths.append((image_path, backup_path))
            temp_path.replace(image_path)
    except Exception as exc:
        for original_path, backup_path in reversed(backup_paths):
            try:
                if backup_path.exists():
                    if original_path.exists():
                        original_path.unlink()
                    backup_path.replace(original_path)
            except OSError:
                pass
        for _, temp_path in rotated_files:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, PageOperationError):
            raise
        raise PageOperationError(f"Could not rotate selected pages: {exc}") from exc

    for _, backup_path in backup_paths:
        try:
            if backup_path.exists():
                backup_path.unlink()
        except OSError:
            pass

    return rotated_pages


def _temporary_sibling_path(image_path: Path) -> Path:
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{image_path.stem}_rotate_",
        suffix=image_path.suffix,
        dir=image_path.parent,
    )
    os.close(fd)
    Path(temp_name).unlink(missing_ok=True)
    return Path(temp_name)


def delete_project_pages(project: Project, *, page_ids: list[str]) -> list[DeletedPage]:
    """Delete multiple pages and their dependent text versions from a project."""
    normalized_ids = list(dict.fromkeys(page_ids))
    if not normalized_ids:
        return []

    with project.session() as session:
        pages = session.execute(
            select(Page).where(Page.id.in_(normalized_ids)).order_by(Page.sequence)
        ).scalars().all()
        if len(pages) != len(normalized_ids):
            found_ids = {page.id for page in pages}
            missing = next(page_id for page_id in normalized_ids if page_id not in found_ids)
            raise PageNotFoundError(f"No page exists with id {missing}")

        deleted_pages = [
            DeletedPage(
                page_id=page.id,
                sequence=page.sequence,
                image_path=page.image_path,
            )
            for page in pages
        ]
        image_paths = [
            project.root / page.image_path
            for page in pages
        ]
        for page in pages:
            session.delete(page)

    # Best-effort cleanup of project-local image files after DB deletion.
    for image_path in image_paths:
        try:
            if image_path.exists():
                image_path.unlink()
        except OSError:
            # Keep deletion successful even if an image file cannot be removed.
            pass

    return deleted_pages


@dataclass(frozen=True)
class ReorderedPage:
    page_id: str
    old_sequence: int
    new_sequence: int


def move_project_pages(
    project: Project,
    *,
    page_ids: list[str],
    direction: Literal["up", "down"],
) -> list[ReorderedPage]:
    """Move selected pages up or down by one slot while preserving relative order."""
    normalized_ids = list(dict.fromkeys(page_ids))
    if not normalized_ids:
        return []

    with project.session() as session:
        pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
        page_map = {page.id: page for page in pages}
        missing = next((page_id for page_id in normalized_ids if page_id not in page_map), None)
        if missing is not None:
            raise PageNotFoundError(f"No page exists with id {missing}")

        selected_ids = set(normalized_ids)
        ordered_ids = [page.id for page in pages]
        original_sequences = {page.id: page.sequence for page in pages}

        if direction == "up":
            for index in range(1, len(ordered_ids)):
                if ordered_ids[index] in selected_ids and ordered_ids[index - 1] not in selected_ids:
                    ordered_ids[index - 1], ordered_ids[index] = ordered_ids[index], ordered_ids[index - 1]
        else:
            for index in range(len(ordered_ids) - 2, -1, -1):
                if ordered_ids[index] in selected_ids and ordered_ids[index + 1] not in selected_ids:
                    ordered_ids[index], ordered_ids[index + 1] = ordered_ids[index + 1], ordered_ids[index]

        if ordered_ids == [page.id for page in pages]:
            return []

        # Avoid transient uniqueness conflicts on pages.sequence by moving through
        # a temporary negative sequence space before assigning final values.
        for index, page_id in enumerate(ordered_ids, start=1):
            page_map[page_id].sequence = -index
        session.flush()

        for index, page_id in enumerate(ordered_ids, start=1):
            page_map[page_id].sequence = index

        return [
            ReorderedPage(
                page_id=page_id,
                old_sequence=original_sequences[page_id],
                new_sequence=index,
            )
            for index, page_id in enumerate(ordered_ids, start=1)
            if original_sequences[page_id] != index
        ]
