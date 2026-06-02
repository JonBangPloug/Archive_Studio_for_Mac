"""SQLAlchemy 2.0 declarative models — the per-project SQLite schema.

Six tables:

* ``project_info`` — single-row metadata.
* ``pages`` — one row per imported page image.
* ``task_runs`` — one row per AI batch invocation.
* ``text_versions`` — all historical text for each page/stage, with
  provenance (``created_by``, ``source_version_id``, ``task_run_id``).
* ``verification_results`` — independent verifier transcriptions for review.
* ``verification_flags`` — text differences awaiting human decision.

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


SCHEMA_VERSION = 2


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
TASK_STATUS_CANCELLED = "cancelled"


# --- Verification review status --------------------------------------------

VERIFICATION_FLAG_REPLACE = "replace"
VERIFICATION_FLAG_INSERT = "insert"
VERIFICATION_FLAG_DELETE = "delete"
VERIFICATION_FLAG_ALIGNMENT_WARNING = "alignment_warning"
VERIFICATION_FLAG_TYPES: tuple[str, ...] = (
    VERIFICATION_FLAG_REPLACE,
    VERIFICATION_FLAG_INSERT,
    VERIFICATION_FLAG_DELETE,
    VERIFICATION_FLAG_ALIGNMENT_WARNING,
)

VERIFICATION_STATUS_OPEN = "open"
VERIFICATION_STATUS_KEPT_PRIMARY = "kept_primary"
VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE = "accepted_alternative"
VERIFICATION_STATUS_MANUAL_EDIT = "manual_edit"
VERIFICATION_STATUS_STALE = "stale"
VERIFICATION_FLAG_STATUSES: tuple[str, ...] = (
    VERIFICATION_STATUS_OPEN,
    VERIFICATION_STATUS_KEPT_PRIMARY,
    VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
    VERIFICATION_STATUS_MANUAL_EDIT,
    VERIFICATION_STATUS_STALE,
)


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
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="VerificationResult.created_at",
    )
    verification_flags: Mapped[list["VerificationFlag"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="VerificationFlag.created_at",
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
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        back_populates="task_run"
    )

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
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        back_populates="source_text_version",
        foreign_keys="VerificationResult.source_text_version_id",
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


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_text_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("text_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    verifier_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alignment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    alignment_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    page: Mapped[Page] = relationship(back_populates="verification_results")
    source_text_version: Mapped[TextVersion] = relationship(
        back_populates="verification_results",
        foreign_keys=[source_text_version_id],
    )
    task_run: Mapped[Optional[TaskRun]] = relationship(back_populates="verification_results")
    flags: Mapped[list["VerificationFlag"]] = relationship(
        back_populates="verification_result",
        cascade="all, delete-orphan",
        order_by="VerificationFlag.primary_start",
    )

    __table_args__ = (
        Index("idx_verification_results_page_source", "page_id", "source_text_version_id"),
        Index("idx_verification_results_task_run", "task_run_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<VerificationResult page={self.page_id} "
            f"source_version={self.source_text_version_id}>"
        )


class VerificationFlag(Base):
    __tablename__ = "verification_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    verification_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("verification_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_text_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("text_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    primary_start: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_end: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alternative_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    flag_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=VERIFICATION_STATUS_OPEN,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resulting_text_version_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("text_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    verification_result: Mapped[VerificationResult] = relationship(back_populates="flags")
    page: Mapped[Page] = relationship(back_populates="verification_flags")
    source_text_version: Mapped[TextVersion] = relationship(
        foreign_keys=[source_text_version_id],
    )
    resulting_text_version: Mapped[Optional[TextVersion]] = relationship(
        foreign_keys=[resulting_text_version_id],
    )

    __table_args__ = (
        Index("idx_verification_flags_page_status", "page_id", "status"),
        Index(
            "idx_verification_flags_source_status",
            "source_text_version_id",
            "status",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<VerificationFlag page={self.page_id} type={self.flag_type!r} "
            f"status={self.status!r}>"
        )
