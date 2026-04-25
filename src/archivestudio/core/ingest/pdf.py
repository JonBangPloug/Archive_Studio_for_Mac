"""Import PDF pages into a project by rasterizing them to images."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

from archivestudio.core.ingest.common import (
    ImportResult,
    ImportedPage,
    build_project_image_name,
    create_page_row,
    next_page_sequence,
    project_image_absolute_path,
    project_image_relative_path,
    rollback_files,
)
from archivestudio.core.project import Project


log = logging.getLogger(__name__)

DEFAULT_PDF_DPI = 200


class PdfImportError(ValueError):
    """Raised when a PDF import request is invalid."""


def import_pdf(
    project: Project,
    pdf_path: Path,
    *,
    source_type: str | None = None,
    dpi: int = DEFAULT_PDF_DPI,
) -> ImportResult:
    """Rasterize each PDF page and add it to ``project`` as a page image."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfImportError(f"Expected a PDF file, got: {pdf_path}")

    imported: list[ImportedPage] = []
    written_files: list[Path] = []

    try:
        with fitz.open(pdf_path) as document:
            if document.page_count == 0:
                raise PdfImportError(f"PDF has no pages: {pdf_path}")

            with project.session() as session:
                sequence = next_page_sequence(session)
                for page_index in range(document.page_count):
                    page = document.load_page(page_index)
                    filename = build_project_image_name(sequence, ".png")
                    destination = project_image_absolute_path(project, filename)

                    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                    pixmap.save(destination)
                    written_files.append(destination)

                    page_row = create_page_row(
                        session,
                        sequence=sequence,
                        image_path=project_image_relative_path(filename),
                        source_type=source_type,
                        notes=f"Imported from PDF: {pdf_path.name} page {page_index + 1}",
                    )
                    imported.append(
                        ImportedPage(
                            page_id=page_row.id,
                            sequence=page_row.sequence,
                            image_path=page_row.image_path,
                        )
                    )
                    sequence += 1
    except Exception:
        rollback_files(written_files)
        raise

    log.info("Imported %s PDF pages from %s", len(imported), pdf_path)
    return ImportResult(pages=imported)
