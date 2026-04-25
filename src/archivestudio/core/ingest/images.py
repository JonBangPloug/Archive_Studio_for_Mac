"""Import page images from a folder into a project."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from archivestudio.core.ingest.common import (
    ImportResult,
    ImportedPage,
    build_project_image_name,
    create_page_row,
    natural_sort_key,
    next_page_sequence,
    project_image_absolute_path,
    project_image_relative_path,
    rollback_files,
)
from archivestudio.core.project import Project


log = logging.getLogger(__name__)


SUPPORTED_IMAGE_SUFFIXES = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


class ImageImportError(ValueError):
    """Raised when an image-folder import request is invalid."""


def import_image_files(
    project: Project,
    image_paths: list[Path],
    *,
    source_type: str | None = None,
) -> ImportResult:
    """Copy one or more supported image files into ``project``."""
    normalized_paths = [Path(path) for path in image_paths]
    if not normalized_paths:
        raise ImageImportError("No image files were provided for import")

    for image_path in normalized_paths:
        if not image_path.exists():
            raise FileNotFoundError(f"Image file does not exist: {image_path}")
        if not image_path.is_file():
            raise ImageImportError(f"Image import path is not a file: {image_path}")
        if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ImageImportError(f"Unsupported image file type: {image_path.suffix}")

    ordered_paths = sorted(normalized_paths, key=lambda path: natural_sort_key(path.name))
    source_label = (
        f"{len(ordered_paths)} selected image files"
        if len(ordered_paths) > 1
        else f"image file: {ordered_paths[0].name}"
    )
    return _import_image_paths(
        project,
        ordered_paths,
        source_type=source_type,
        source_description=source_label,
    )


def import_image_file(
    project: Project,
    image_path: Path,
    *,
    source_type: str | None = None,
) -> ImportResult:
    """Copy one supported image file into ``project``."""
    return import_image_files(project, [image_path], source_type=source_type)


def import_image_folder(
    project: Project,
    folder: Path,
    *,
    source_type: str | None = None,
) -> ImportResult:
    """Copy supported image files from ``folder`` into ``project``."""
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Image folder does not exist: {folder}")
    if not folder.is_dir():
        raise ImageImportError(f"Image import path is not a directory: {folder}")

    image_paths = sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        ],
        key=lambda path: natural_sort_key(path.name),
    )
    if not image_paths:
        raise ImageImportError(f"No supported image files found in {folder}")

    return _import_image_paths(
        project,
        image_paths,
        source_type=source_type,
        source_description=None,
    )


def _import_image_paths(
    project: Project,
    image_paths: list[Path],
    *,
    source_type: str | None = None,
    source_description: str | None = None,
) -> ImportResult:
    if not image_paths:
        raise ImageImportError("No image files were provided for import")

    imported: list[ImportedPage] = []
    written_files: list[Path] = []

    try:
        with project.session() as session:
            sequence = next_page_sequence(session)
            for image_path in image_paths:
                filename = build_project_image_name(sequence, image_path.suffix)
                destination = project_image_absolute_path(project, filename)
                shutil.copy2(image_path, destination)
                written_files.append(destination)

                page = create_page_row(
                    session,
                    sequence=sequence,
                    image_path=project_image_relative_path(filename),
                    source_type=source_type,
                    notes=(
                        f"Imported from image file: {image_path.name}"
                        if source_description is not None
                        else f"Imported from image file: {image_path.name}"
                    ),
                )
                imported.append(
                    ImportedPage(
                        page_id=page.id,
                        sequence=page.sequence,
                        image_path=page.image_path,
                    )
                )
                sequence += 1
    except Exception:
        rollback_files(written_files)
        raise

    source_label = source_description or image_paths[0].parent
    log.info("Imported %s image pages from %s", len(imported), source_label)
    return ImportResult(pages=imported)
