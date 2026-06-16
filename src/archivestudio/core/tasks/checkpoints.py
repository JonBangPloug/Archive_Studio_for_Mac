"""Durable per-page checkpoint files for long-running text tasks."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import tempfile

from archivestudio.core.project import Project
from archivestudio.core.models import STAGE_CORRECTED, STAGE_ORIGINAL, STAGE_TRANSLATED


MANIFEST_COLUMNS = (
    "page_sequence",
    "page_id",
    "stage",
    "status",
    "provider",
    "model",
    "text_version_id",
    "output_filename",
    "timestamp",
    "error_message",
)


class CheckpointWriteError(RuntimeError):
    """Raised when checkpoint writing fails after DB persistence succeeded."""


@dataclass(frozen=True)
class CheckpointRecord:
    page_sequence: int
    page_id: str
    stage: str
    status: str
    provider: str
    model: str
    text_version_id: str = ""
    output_filename: str = ""
    error_message: str = ""


def checkpoint_filename(page_sequence: int) -> str:
    """Return the stable per-page checkpoint filename."""
    return f"page_{page_sequence:06d}.txt"


def checkpoint_stage_dir(project: Project, stage: str) -> Path:
    """Return the checkpoint directory for a text stage."""
    _validate_stage(stage)
    return project.exports_dir / "checkpoints" / stage


def write_completed_checkpoint(
    project: Project,
    *,
    page_sequence: int,
    page_id: str,
    stage: str,
    content: str,
    provider: str,
    model: str,
    text_version_id: str,
    enabled: bool = True,
) -> Path | None:
    """Write the checkpoint text file and completed manifest row."""
    if not enabled:
        return None

    stage_dir = checkpoint_stage_dir(project, stage)
    output_filename = checkpoint_filename(page_sequence)
    output_path = stage_dir / output_filename
    record = CheckpointRecord(
        page_sequence=page_sequence,
        page_id=page_id,
        stage=stage,
        status="completed",
        provider=provider,
        model=model,
        text_version_id=text_version_id,
        output_filename=output_filename,
    )
    try:
        stage_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(output_path, content)
        _write_manifest_record(stage_dir / "manifest.csv", record)
    except Exception as exc:
        raise CheckpointWriteError(
            f"Could not write checkpoint for page {page_sequence} ({stage}) at {output_path}: {exc}"
        ) from exc
    return output_path


def write_failed_checkpoint_record(
    project: Project,
    *,
    page_sequence: int,
    page_id: str,
    stage: str,
    provider: str,
    model: str,
    error_message: str,
    enabled: bool = True,
) -> None:
    """Record a failed page in the per-stage checkpoint manifest."""
    if not enabled:
        return

    stage_dir = checkpoint_stage_dir(project, stage)
    record = CheckpointRecord(
        page_sequence=page_sequence,
        page_id=page_id,
        stage=stage,
        status="failed",
        provider=provider,
        model=model,
        error_message=error_message,
    )
    try:
        stage_dir.mkdir(parents=True, exist_ok=True)
        _write_manifest_record(stage_dir / "manifest.csv", record)
    except Exception as exc:
        raise CheckpointWriteError(
            f"Could not write checkpoint manifest failure row for page {page_sequence} ({stage}): {exc}"
        ) from exc


def _write_manifest_record(path: Path, record: CheckpointRecord) -> None:
    rows = _read_manifest_rows(path)
    row = _record_to_row(record)
    if record.status == "completed":
        rows = [
            existing
            for existing in rows
            if not (
                existing.get("page_id") == record.page_id
                and existing.get("stage") == record.stage
                and existing.get("status") == "completed"
            )
        ]
    rows.append(row)
    rows.sort(key=lambda item: (_sort_int(item.get("page_sequence")), item.get("timestamp", "")))
    _atomic_write_text(path, _render_manifest(rows))


def _read_manifest_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {column: str(row.get(column, "") or "") for column in MANIFEST_COLUMNS}
            for row in reader
        ]


def _record_to_row(record: CheckpointRecord) -> dict[str, str]:
    return {
        "page_sequence": str(record.page_sequence),
        "page_id": record.page_id,
        "stage": record.stage,
        "status": record.status,
        "provider": record.provider,
        "model": record.model,
        "text_version_id": record.text_version_id,
        "output_filename": record.output_filename,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error_message": record.error_message,
    }


def _render_manifest(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise


def _sort_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _validate_stage(stage: str) -> None:
    allowed_stages = {STAGE_ORIGINAL, STAGE_CORRECTED, STAGE_TRANSLATED}
    if stage not in allowed_stages:
        raise ValueError(f"Unsupported checkpoint stage: {stage}")
