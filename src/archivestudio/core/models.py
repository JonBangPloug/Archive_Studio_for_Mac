"""SQLAlchemy 2.0 declarative models — the per-project SQLite schema.

Four tables:

* ``project_info`` — single-row metadata.
* ``pages`` — one row per imported page image.
* ``task_runs`` — one row per AI batch invocation.
* ``text_versions`` — all historical text for each page/stage, with
  provenance (``created_by``, ``source_version_id``, ``task_run_id``).

One *current* TextVersion per ``(page_id, stage)`` is enforced via a partial
unique index on ``is_current = 1``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


SCHEMA_VERSION = 1


# --- Stage constants ---------------------------------------------------------

STAGE_ORIGINAL = "original"
STAGE_CORRECTED = "corrected"
STAGE_TRANSLATED = "translated"
STAGES: tuple[str, ...] = (
    STAGE_ORIGINAL,
    STAGE_CORRECTED,
    STAGE_TRANSLATED,
)


# --- Task run status ---------------------------------------------------------

TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_PARTIAL = "partial"
TASK_STATUS_FAILED = "failed"


# --- Source type (how a page was ingested/what it shows) --------------------

SOURCE_TYPE_HANDWRITTEN = "handwritten"
SOURCE_TYPE_PRINTED = "printed"
SOURCE_TYPE_CATALOGUE = "catalogue"
SOURCE_TYPE_CUSTOM = "custom"
SOURCE_TYPES: tuple[str, ...] = (
    SOURCE_TYPE_HANDWRITTEN,
    SOURCE_TYPE_PRINTED,
    SOURCE_TYPE_CATALOGUE,
    SOURCE_TYPE_CUSTOM,
)

SOURCE_HANDWRITTEN = "handwritten"
SOURCE_PRINTED = "printed"
SOURCE_CATALOGUE = "catalogue"


def _new_id() -> str:
    """Generate a UUID4 string primary key."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class ProjectInfo(Base):
    __tablename__ = "project_info"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=SCHEMA_VERSION)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ProjectInfo name={self.name!r} schema_version={self.schema_version}>"


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    text_versions: Mapped[list["TextVersion"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="TextVersion.created_at",
    )

    __table_args__ = (
        UniqueConstraint("sequence", name="uq_pages_sequence"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Page seq={self.sequence} image={self.image_path!r}>"


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    preset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TASK_STATUS_RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pages_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    text_versions: Mapped[list["TextVersion"]] = relationship(back_populates="task_run")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<TaskRun type={self.task_type!r} preset={self.preset_name!r} status={self.status!r}>"


class TextVersion(Base):
    __tablename__ = "text_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("text_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    page: Mapped[Page] = relationship(back_populates="text_versions")
    task_run: Mapped[Optional[TaskRun]] = relationship(back_populates="text_versions")
    source_version: Mapped[Optional["TextVersion"]] = relationship(
        remote_side="TextVersion.id",
        foreign_keys=[source_version_id],
    )

    __table_args__ = (
        Index("idx_text_versions_page_stage", "page_id", "stage"),
        # Partial unique index: at most one *current* version per (page, stage).
        Index(
            "uq_text_versions_current",
            "page_id",
            "stage",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<TextVersion page={self.page_id} stage={self.stage!r} "
            f"current={self.is_current} by={self.created_by!r}>"
        )
