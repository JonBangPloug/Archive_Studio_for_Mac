"""Shared export data structures and record collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from archivestudio.core.models import Page, STAGES, TextVersion
from archivestudio.core.project import Project


@dataclass(frozen=True)
class ExportPageRecord:
    """One exported page record with current text versions."""

    page_id: str
    page_sequence: int
    image_path: str
    source_type: str | None
    selected_stage: str
    selected_text: str
    text_versions: dict[str, str]
    version_metadata: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class ExportBundle:
    """Collected export payload before rendering to a file format."""

    project_name: str
    project_root: str
    export_format: str
    export_profile: str
    selected_stage: str
    exported_at: str
    scope_label: str
    records: list[ExportPageRecord]


def collect_export_bundle(
    project: Project,
    *,
    export_format: str,
    export_profile: str,
    selected_stage: str,
    scope_label: str,
    page_ids: list[str] | None = None,
) -> ExportBundle:
    """Collect the current text state for selected pages."""
    if selected_stage not in STAGES:
        raise ValueError(f"Unsupported export stage: {selected_stage}")

    with project.session() as session:
        pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
        if page_ids is not None:
            allowed_ids = set(page_ids)
            pages = [page for page in pages if page.id in allowed_ids]

        records: list[ExportPageRecord] = []
        for page in pages:
            current_versions = _current_versions_for_page(session, page.id)
            selected_text = current_versions.get(selected_stage, "")
            metadata = _version_metadata_for_page(session, page.id)
            records.append(
                ExportPageRecord(
                    page_id=page.id,
                    page_sequence=page.sequence,
                    image_path=page.image_path,
                    source_type=page.source_type,
                    selected_stage=selected_stage,
                    selected_text=selected_text,
                    text_versions=current_versions,
                    version_metadata=metadata,
                )
            )

    return ExportBundle(
        project_name=project.name,
        project_root=str(project.root),
        export_format=export_format,
        export_profile=export_profile,
        selected_stage=selected_stage,
        exported_at=datetime.now(timezone.utc).isoformat(),
        scope_label=scope_label,
        records=records,
    )


def _current_versions_for_page(session, page_id: str) -> dict[str, str]:
    versions = session.execute(
        select(TextVersion).where(
            TextVersion.page_id == page_id,
            TextVersion.is_current.is_(True),
        )
    ).scalars().all()
    return {version.stage: version.content for version in versions}


def _version_metadata_for_page(session, page_id: str) -> dict[str, dict[str, str | None]]:
    versions = session.execute(
        select(TextVersion).where(
            TextVersion.page_id == page_id,
            TextVersion.is_current.is_(True),
        )
    ).scalars().all()
    metadata: dict[str, dict[str, str | None]] = {}
    for version in versions:
        metadata[version.stage] = {
            "created_at": version.created_at.isoformat(),
            "created_by": version.created_by,
            "source_version_id": version.source_version_id,
            "task_run_id": version.task_run_id,
        }
    for stage in STAGES:
        metadata.setdefault(
            stage,
            {
                "created_at": None,
                "created_by": None,
                "source_version_id": None,
                "task_run_id": None,
            },
        )
    return metadata
