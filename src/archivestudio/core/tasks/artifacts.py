"""Project-local task run provenance artifacts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from archivestudio.core.project import Project
from archivestudio.core.tasks.types import TaskPreset


def task_run_artifact_path(project: Project, task_run_id: str) -> Path:
    """Return the JSON artifact path for a task run."""
    return project.task_runs_dir / f"{task_run_id}.json"


def write_task_run_artifact(
    project: Project,
    *,
    task_run_id: str,
    task_type: str,
    provider_name: str,
    model_id: str,
    preset: TaskPreset,
    requests: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    errors: list[str],
) -> Path:
    """Persist an audit snapshot for one AI task run."""
    payload = {
        "schema_version": 1,
        "task_run_id": task_run_id,
        "task_type": task_type,
        "provider": {
            "name": provider_name,
            "model_id": model_id,
        },
        "preset": _preset_snapshot(preset),
        "requests": requests,
        "responses": responses,
        "errors": list(errors),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    path = task_run_artifact_path(project, task_run_id)
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def request_artifact(
    request: Any,
    *,
    prompt_system: str,
    prompt_user: str,
    source_text: str | None = None,
    source_text_stage: str | None = None,
    source_text_version_id: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe request snapshot for a provider call."""
    payload = {
        "page_id": request.page_id,
        "page_sequence": request.page_sequence,
        "source_type": request.source_type,
        "prompt": {
            "system": prompt_system,
            "user": prompt_user,
        },
    }
    image_path = getattr(request, "image_path", None)
    if image_path is not None:
        payload["image_path"] = str(image_path)
    if source_text is not None:
        payload["source_text"] = source_text
    if source_text_stage is not None:
        payload["source_text_stage"] = source_text_stage
    if source_text_version_id is not None:
        payload["source_text_version_id"] = source_text_version_id
    return payload


def response_artifact(
    *,
    page_id: str,
    page_sequence: int,
    output_text: str | None,
    raw_response: str | None,
) -> dict[str, Any]:
    """Return a JSON-safe response snapshot for a provider result."""
    return {
        "page_id": page_id,
        "page_sequence": page_sequence,
        "output_text": output_text,
        "raw_response": raw_response,
    }


def _preset_snapshot(preset: TaskPreset) -> dict[str, Any]:
    return asdict(preset)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
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
