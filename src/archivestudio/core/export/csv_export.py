"""CSV export rendering."""

from __future__ import annotations

import csv
from io import StringIO

from archivestudio.core.export.common import ExportBundle
from archivestudio.core.models import (
    STAGE_CORRECTED,
    STAGE_ORIGINAL,
    STAGE_TRANSLATED,
)


def render_csv(bundle: ExportBundle) -> str:
    """Render a page-level CSV export."""
    output = StringIO()
    fieldnames = [
        "project_name",
        "page_id",
        "page_sequence",
        "source_type",
        "image_path",
        "selected_stage",
        "selected_text",
        "original_text",
        "corrected_text",
        "translated_text",
        "original_created_by",
        "corrected_created_by",
        "translated_created_by",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for record in bundle.records:
        writer.writerow(
            {
                "project_name": bundle.project_name,
                "page_id": record.page_id,
                "page_sequence": record.page_sequence,
                "source_type": record.source_type or "",
                "image_path": record.image_path,
                "selected_stage": record.selected_stage,
                "selected_text": record.selected_text,
                "original_text": record.text_versions.get(STAGE_ORIGINAL, ""),
                "corrected_text": record.text_versions.get(STAGE_CORRECTED, ""),
                "translated_text": record.text_versions.get(STAGE_TRANSLATED, ""),
                "original_created_by": record.version_metadata[STAGE_ORIGINAL]["created_by"] or "",
                "corrected_created_by": record.version_metadata[STAGE_CORRECTED]["created_by"] or "",
                "translated_created_by": record.version_metadata[STAGE_TRANSLATED]["created_by"] or "",
            }
        )

    return output.getvalue()
