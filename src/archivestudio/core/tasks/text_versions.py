"""Shared text-version persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from archivestudio.core.models import TextVersion


def get_current_text_version(session: Session, *, page_id: str, stage: str) -> TextVersion | None:
    """Return the current text version for ``(page_id, stage)`` if present."""
    return session.execute(
        select(TextVersion).where(
            TextVersion.page_id == page_id,
            TextVersion.stage == stage,
            TextVersion.is_current.is_(True),
        )
    ).scalar_one_or_none()


def replace_current_text_version(
    session: Session,
    *,
    page_id: str,
    stage: str,
    content: str,
    created_by: str,
    task_run_id: str | None = None,
    source_version_id: str | None = None,
) -> TextVersion:
    """Insert a new current text version and demote any previous current row."""
    current = get_current_text_version(session, page_id=page_id, stage=stage)
    if current is not None:
        current.is_current = False
        if source_version_id is None:
            source_version_id = current.id
        # Flush the demotion before inserting the replacement so the partial
        # unique index on (page_id, stage, is_current) cannot see two current
        # rows in one flush ordering.
        session.flush()

    text_version = TextVersion(
        page_id=page_id,
        stage=stage,
        content=content,
        created_by=created_by,
        source_version_id=source_version_id,
        task_run_id=task_run_id,
        is_current=True,
    )
    session.add(text_version)
    session.flush()
    return text_version


def save_manual_text_version(
    session: Session,
    *,
    page_id: str,
    stage: str,
    content: str,
    source_version_id: str | None = None,
) -> TextVersion:
    """Persist a manual edit as the new current text version for a stage."""
    return replace_current_text_version(
        session,
        page_id=page_id,
        stage=stage,
        content=content,
        created_by="user:manual_edit",
        source_version_id=source_version_id,
    )
