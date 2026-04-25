"""High-level export file writer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archivestudio.core.export.common import collect_export_bundle
from archivestudio.core.export.csv_export import render_csv
from archivestudio.core.export.json_export import render_json, render_jsonl
from archivestudio.core.export.markdown import render_markdown
from archivestudio.core.export.profiles import EXPORT_PROFILE_GENERIC
from archivestudio.core.export.text import render_text
from archivestudio.core.project import Project


EXPORT_FORMAT_TEXT = "text"
EXPORT_FORMAT_MARKDOWN = "markdown"
EXPORT_FORMAT_CSV = "csv"
EXPORT_FORMAT_JSON = "json"
EXPORT_FORMAT_JSONL = "jsonl"


_FORMAT_TO_SUFFIX = {
    EXPORT_FORMAT_TEXT: ".txt",
    EXPORT_FORMAT_MARKDOWN: ".md",
    EXPORT_FORMAT_CSV: ".csv",
    EXPORT_FORMAT_JSON: ".json",
    EXPORT_FORMAT_JSONL: ".jsonl",
}


@dataclass(frozen=True)
class ExportResult:
    """Result of a completed export."""

    output_path: Path
    export_format: str
    selected_stage: str
    record_count: int
    scope_label: str


def export_project_records(
    project: Project,
    *,
    export_format: str,
    export_profile: str = EXPORT_PROFILE_GENERIC,
    selected_stage: str,
    scope_label: str,
    page_ids: list[str] | None = None,
    output_path: Path | None = None,
) -> ExportResult:
    """Export selected project records to a file."""
    bundle = collect_export_bundle(
        project,
        export_format=export_format,
        export_profile=export_profile,
        selected_stage=selected_stage,
        scope_label=scope_label,
        page_ids=page_ids,
    )

    if export_format == EXPORT_FORMAT_TEXT:
        content = render_text(bundle)
    elif export_format == EXPORT_FORMAT_MARKDOWN:
        content = render_markdown(bundle)
    elif export_format == EXPORT_FORMAT_CSV:
        content = render_csv(bundle)
    elif export_format == EXPORT_FORMAT_JSON:
        content = render_json(bundle)
    elif export_format == EXPORT_FORMAT_JSONL:
        content = render_jsonl(bundle)
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported export format: {export_format}")

    target = output_path if output_path is not None else default_export_path(
        project,
        export_format=export_format,
        selected_stage=selected_stage,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return ExportResult(
        output_path=target,
        export_format=export_format,
        selected_stage=selected_stage,
        record_count=len(bundle.records),
        scope_label=scope_label,
    )


def default_export_path(project: Project, *, export_format: str, selected_stage: str) -> Path:
    suffix = _FORMAT_TO_SUFFIX[export_format]
    safe_stage = selected_stage.replace(" ", "_")
    return project.exports_dir / f"{project.name}_{safe_stage}{suffix}"
