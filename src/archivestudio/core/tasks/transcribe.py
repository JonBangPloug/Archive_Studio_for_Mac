"""Transcription task service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select

from archivestudio.core.ai.base import AIProvider, PromptMessages, TranscriptionRequest
from archivestudio.core.errors import classify_exception
from archivestudio.core.models import Page
from archivestudio.core.project import Project
from archivestudio.core.tasks.artifacts import (
    request_artifact,
    response_artifact,
    write_task_run_artifact,
)
from archivestudio.core.tasks.registry import get_task_definition
from archivestudio.core.tasks.runs import (
    ProgressCallback,
    TaskProgress,
    TaskRunSummary,
    chunked,
    complete_task_run,
    create_task_run,
    emit_progress,
    final_status,
    mark_task_run_failed_after_crash,
)
from archivestudio.core.tasks.text_versions import get_current_text_version, replace_current_text_version
from archivestudio.core.tasks.types import TASK_TRANSCRIBE, TaskPreset


log = logging.getLogger(__name__)

@dataclass(frozen=True)
class _TargetPage:
    id: str
    sequence: int
    image_path: str
    source_type: str | None


def run_transcription(
    project: Project,
    provider: AIProvider,
    preset: TaskPreset,
    *,
    page_ids: Sequence[str] | None = None,
    page_sequences: Sequence[int] | None = None,
    skip_existing: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> TaskRunSummary:
    """Run the transcription task for selected project pages."""
    if preset.task_type != TASK_TRANSCRIBE:
        raise ValueError(f"Preset {preset.name!r} is not a transcription preset")

    definition = get_task_definition(TASK_TRANSCRIBE)
    target_pages = _load_target_pages(
        project,
        page_ids=page_ids,
        page_sequences=page_sequences,
        output_stage=definition.output_stage,
        skip_existing=skip_existing,
    )
    if not target_pages:
        raise ValueError("No pages matched the transcription request")

    task_run_id = create_task_run(
        project,
        preset_name=preset.name,
        task_type=definition.task_type,
        model_id=f"{provider.provider_name}:{provider.model_id}",
        pages_requested=len(target_pages),
    )

    created_text_version_ids: list[str] = []
    errors: list[str] = []
    artifact_requests: list[dict[str, object]] = []
    artifact_responses: list[dict[str, object]] = []
    pages_completed = 0
    pages_failed = 0

    try:
        _emit_task_progress(
            progress_callback,
            preset=preset,
            total=len(target_pages),
            completed=pages_completed,
            failed=pages_failed,
            message="Starting transcription",
        )

        batch_size = max(1, preset.batch_size)
        if not provider.supports_batching:
            batch_size = 1
        if preset.model_config.max_batch_pages > 0:
            batch_size = min(batch_size, preset.model_config.max_batch_pages)

        for batch in chunked(target_pages, batch_size):
            current_pages = tuple(page.sequence for page in batch)
            _emit_task_progress(
                progress_callback,
                preset=preset,
                total=len(target_pages),
                completed=pages_completed,
                failed=pages_failed,
                current_pages=current_pages,
                message="Sending transcription request",
            )
            requests: list[TranscriptionRequest] = []
            missing_images = 0
            for page in batch:
                absolute_image_path = project.root / page.image_path
                if not absolute_image_path.exists():
                    message = f"Missing page image for page {page.sequence}: {absolute_image_path}"
                    errors.append(message)
                    log.error(message)
                    missing_images += 1
                    continue

                prompt = _render_prompt(page, preset)
                request = TranscriptionRequest(
                    page_id=page.id,
                    page_sequence=page.sequence,
                    image_path=absolute_image_path,
                    source_type=page.source_type,
                    prompt=prompt,
                )
                requests.append(request)
                artifact_requests.append(
                    request_artifact(
                        request,
                        prompt_system=prompt.system,
                        prompt_user=prompt.user,
                    )
                )

            if missing_images:
                pages_failed += missing_images
                _emit_task_progress(
                    progress_callback,
                    preset=preset,
                    total=len(target_pages),
                    completed=pages_completed,
                    failed=pages_failed,
                    current_pages=current_pages,
                    message="Missing image",
                )
            if not requests:
                continue

            try:
                results = provider.transcribe_pages(requests, model_config=preset.model_config)
            except Exception as exc:  # pragma: no cover - exercised by future error-path tests
                report = classify_exception(exc)
                log.exception(
                    "Transcription batch failed for pages %s [%s]: %s",
                    [page.sequence for page in batch],
                    report.category,
                    report.summary,
                )
                pages_failed += len(requests)
                errors.append(f"{report.category}: {report.summary} {report.suggestion}")
                _emit_task_progress(
                    progress_callback,
                    preset=preset,
                    total=len(target_pages),
                    completed=pages_completed,
                    failed=pages_failed,
                    current_pages=current_pages,
                    message="Transcription request failed",
                )
                continue

            result_map = {result.page_id: result for result in results}
            with project.session() as session:
                for request in requests:
                    result = result_map.get(request.page_id)
                    if result is None:
                        message = f"Provider returned no result for page {request.page_sequence}"
                        errors.append(message)
                        log.error(message)
                        pages_failed += 1
                        _emit_task_progress(
                            progress_callback,
                            preset=preset,
                            total=len(target_pages),
                            completed=pages_completed,
                            failed=pages_failed,
                            current_pages=(request.page_sequence,),
                            message="No provider result",
                        )
                        continue
                    artifact_responses.append(
                        response_artifact(
                            page_id=request.page_id,
                            page_sequence=request.page_sequence,
                            output_text=result.transcription,
                            raw_response=result.raw_response,
                        )
                    )

                    text_version = replace_current_text_version(
                        session,
                        page_id=request.page_id,
                        stage=definition.output_stage,
                        content=_normalize_response_text(result.transcription, preset.response_prefix),
                        created_by=f"ai:{provider.provider_name}:{provider.model_id}",
                        task_run_id=task_run_id,
                    )
                    created_text_version_ids.append(text_version.id)
                    pages_completed += 1
                    _emit_task_progress(
                        progress_callback,
                        preset=preset,
                        total=len(target_pages),
                        completed=pages_completed,
                        failed=pages_failed,
                        current_pages=(request.page_sequence,),
                        message="Transcription saved",
                    )

        status = final_status(pages_completed, pages_failed)
        complete_task_run(
            project,
            task_run_id=task_run_id,
            status=status,
            pages_completed=pages_completed,
            pages_failed=pages_failed,
            error_message="\n".join(errors) if errors else None,
        )
        try:
            write_task_run_artifact(
                project,
                task_run_id=task_run_id,
                task_type=definition.task_type,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                preset=preset,
                requests=artifact_requests,
                responses=artifact_responses,
                errors=errors,
            )
        except Exception:
            log.warning("Could not write transcription task artifact %s", task_run_id, exc_info=True)
        return TaskRunSummary(
            task_run_id=task_run_id,
            task_type=definition.task_type,
            preset_name=preset.name,
            pages_requested=len(target_pages),
            pages_completed=pages_completed,
            pages_failed=pages_failed,
            status=status,
            created_text_version_ids=created_text_version_ids,
            errors=errors,
        )
    except Exception as exc:
        mark_task_run_failed_after_crash(
            project,
            task_run_id=task_run_id,
            pages_requested=len(target_pages),
            pages_completed=pages_completed,
            pages_failed=pages_failed,
            error=exc,
        )
        raise


def _emit_task_progress(
    callback: ProgressCallback | None,
    *,
    preset: TaskPreset,
    total: int,
    completed: int,
    failed: int,
    current_pages: tuple[int, ...] = (),
    message: str = "",
) -> None:
    emit_progress(
        callback,
        TaskProgress(
            task_type=TASK_TRANSCRIBE,
            preset_name=preset.name,
            pages_total=total,
            pages_completed=completed,
            pages_failed=failed,
            current_pages=current_pages,
            message=message,
        ),
    )


def _render_prompt(page: _TargetPage, preset: TaskPreset) -> PromptMessages:
    structure_rules = [
        "- Preserve line breaks." if preset.preserve_line_breaks else "- Normalize line breaks when needed for readability.",
        "- Preserve marginalia explicitly." if preset.preserve_marginalia else "- Ignore decorative marginal marks unless they carry content.",
        "- Preserve original spacing and layout cues." if not preset.normalize_whitespace else "- Normalize repeated whitespace while preserving section structure.",
    ]
    custom_instructions = preset.custom_instructions.strip() or "None."
    user = preset.prompt_template.user_prompt_template.format(
        page_sequence=page.sequence,
        source_genre=preset.source_genre,
        structure_rules="\n".join(structure_rules),
        custom_instructions=custom_instructions,
        text_to_process="",
    )
    return PromptMessages(system=preset.prompt_template.system_prompt, user=user)


def _normalize_response_text(text: str, response_prefix: str) -> str:
    cleaned = text.strip()
    prefix = response_prefix.strip()
    if not prefix:
        return cleaned
    if cleaned.lower().startswith(prefix.lower()):
        cleaned = cleaned[len(prefix):].lstrip(" \n\r\t:-")
    return cleaned.strip()


def _load_target_pages(
    project: Project,
    *,
    page_ids: Sequence[str] | None,
    page_sequences: Sequence[int] | None,
    output_stage: str,
    skip_existing: bool,
) -> list[_TargetPage]:
    with project.session() as session:
        pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()

        if page_ids is not None:
            allowed_ids = set(page_ids)
            pages = [page for page in pages if page.id in allowed_ids]
        if page_sequences is not None:
            allowed_sequences = set(page_sequences)
            pages = [page for page in pages if page.sequence in allowed_sequences]

        selected: list[_TargetPage] = []
        for page in pages:
            if skip_existing and get_current_text_version(
                session,
                page_id=page.id,
                stage=output_stage,
            ) is not None:
                continue
            selected.append(
                _TargetPage(
                    id=page.id,
                    sequence=page.sequence,
                    image_path=page.image_path,
                    source_type=page.source_type,
                )
            )
        return selected
