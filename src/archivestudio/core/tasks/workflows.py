"""Multi-step task workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select

from archivestudio.core.ai.base import AIProvider
from archivestudio.core.models import STAGE_CORRECTED, TASK_STATUS_CANCELLED, TextVersion
from archivestudio.core.project import Project
from archivestudio.core.tasks.correct import run_correction
from archivestudio.core.tasks.registry import get_preset
from archivestudio.core.tasks.runs import ProgressCallback, TaskRunSummary, final_status
from archivestudio.core.tasks.cancellation import CancellationToken
from archivestudio.core.tasks.transcribe import run_transcription
from archivestudio.core.tasks.types import TaskPreset


HANDWRITTEN_HTR_CORRECTION_WORKFLOW = "handwritten_htr_correction"
PRINTED_OCR_CORRECTION_WORKFLOW = "printed_ocr_correction"


@dataclass(frozen=True)
class WorkflowRunSummary:
    """Structured summary for a multi-step workflow."""

    workflow_name: str
    pages_requested: int
    pages_completed: int
    pages_failed: int
    status: str
    final_stage: str
    step_summaries: list[TaskRunSummary]
    created_text_version_ids: list[str]
    errors: list[str]


def run_handwritten_htr_and_correction(
    project: Project,
    provider: AIProvider,
    *,
    page_ids: Sequence[str] | None = None,
    page_sequences: Sequence[int] | None = None,
    transcription_preset: TaskPreset | None = None,
    correction_preset: TaskPreset | None = None,
    correction_provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_token: CancellationToken | None = None,
) -> WorkflowRunSummary:
    """Run handwritten transcription followed by handwritten correction."""
    return _run_transcribe_and_correct_workflow(
        project,
        provider,
        workflow_name=HANDWRITTEN_HTR_CORRECTION_WORKFLOW,
        transcription_preset_name="Handwritten Transcription",
        correction_preset_name="Handwritten Correction",
        page_ids=page_ids,
        page_sequences=page_sequences,
        transcription_preset=transcription_preset,
        correction_preset=correction_preset,
        correction_provider=correction_provider,
        progress_callback=progress_callback,
        cancellation_token=cancellation_token,
    )


def run_printed_ocr_and_correction(
    project: Project,
    provider: AIProvider,
    *,
    page_ids: Sequence[str] | None = None,
    page_sequences: Sequence[int] | None = None,
    transcription_preset: TaskPreset | None = None,
    correction_preset: TaskPreset | None = None,
    correction_provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_token: CancellationToken | None = None,
) -> WorkflowRunSummary:
    """Run printed OCR followed by printed correction."""
    return _run_transcribe_and_correct_workflow(
        project,
        provider,
        workflow_name=PRINTED_OCR_CORRECTION_WORKFLOW,
        transcription_preset_name="Printed Transcription",
        correction_preset_name="Printed Correction",
        page_ids=page_ids,
        page_sequences=page_sequences,
        transcription_preset=transcription_preset,
        correction_preset=correction_preset,
        correction_provider=correction_provider,
        progress_callback=progress_callback,
        cancellation_token=cancellation_token,
    )


def _run_transcribe_and_correct_workflow(
    project: Project,
    provider: AIProvider,
    *,
    workflow_name: str,
    transcription_preset_name: str,
    correction_preset_name: str,
    page_ids: Sequence[str] | None = None,
    page_sequences: Sequence[int] | None = None,
    transcription_preset: TaskPreset | None = None,
    correction_preset: TaskPreset | None = None,
    correction_provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_token: CancellationToken | None = None,
) -> WorkflowRunSummary:
    """Run a transcription preset followed by its matching correction preset."""
    resolved_transcription_preset = transcription_preset or get_preset(transcription_preset_name)
    transcription_summary = run_transcription(
        project,
        provider,
        resolved_transcription_preset,
        page_ids=page_ids,
        page_sequences=page_sequences,
        progress_callback=progress_callback,
        cancellation_token=cancellation_token,
    )

    step_summaries = [transcription_summary]
    created_text_version_ids = list(transcription_summary.created_text_version_ids)
    errors = list(transcription_summary.errors)
    pages_requested = transcription_summary.pages_requested

    if transcription_summary.status == TASK_STATUS_CANCELLED:
        return WorkflowRunSummary(
            workflow_name=workflow_name,
            pages_requested=pages_requested,
            pages_completed=transcription_summary.pages_completed,
            pages_failed=transcription_summary.pages_failed,
            status=TASK_STATUS_CANCELLED,
            final_stage=STAGE_CORRECTED,
            step_summaries=step_summaries,
            created_text_version_ids=created_text_version_ids,
            errors=errors,
        )

    if transcription_summary.pages_completed == 0:
        return WorkflowRunSummary(
            workflow_name=workflow_name,
            pages_requested=pages_requested,
            pages_completed=0,
            pages_failed=pages_requested,
            status=transcription_summary.status,
            final_stage=STAGE_CORRECTED,
            step_summaries=step_summaries,
            created_text_version_ids=created_text_version_ids,
            errors=errors,
        )

    corrected_page_ids = _page_ids_for_text_versions(
        project,
        transcription_summary.created_text_version_ids,
    )
    if not corrected_page_ids:
        errors.append("Transcription completed but no new page ids could be resolved for correction.")
        return WorkflowRunSummary(
            workflow_name=workflow_name,
            pages_requested=pages_requested,
            pages_completed=0,
            pages_failed=pages_requested,
            status=final_status(0, pages_requested),
            final_stage=STAGE_CORRECTED,
            step_summaries=step_summaries,
            created_text_version_ids=created_text_version_ids,
            errors=errors,
        )

    resolved_correction_preset = correction_preset or get_preset(correction_preset_name)
    resolved_correction_provider = correction_provider or provider
    correction_summary = run_correction(
        project,
        resolved_correction_provider,
        resolved_correction_preset,
        page_ids=corrected_page_ids,
        progress_callback=progress_callback,
        cancellation_token=cancellation_token,
    )
    step_summaries.append(correction_summary)
    created_text_version_ids.extend(correction_summary.created_text_version_ids)
    errors.extend(correction_summary.errors)

    pages_completed = correction_summary.pages_completed
    pages_failed = max(0, pages_requested - pages_completed)
    status = (
        TASK_STATUS_CANCELLED
        if correction_summary.status == TASK_STATUS_CANCELLED
        else final_status(pages_completed, pages_failed)
    )

    return WorkflowRunSummary(
        workflow_name=workflow_name,
        pages_requested=pages_requested,
        pages_completed=pages_completed,
        pages_failed=pages_failed,
        status=status,
        final_stage=STAGE_CORRECTED,
        step_summaries=step_summaries,
        created_text_version_ids=created_text_version_ids,
        errors=errors,
    )


def _page_ids_for_text_versions(project: Project, text_version_ids: Sequence[str]) -> list[str]:
    """Return page ids for created text versions, preserving creation order."""
    if not text_version_ids:
        return []
    with project.session() as session:
        versions = session.execute(
            select(TextVersion).where(TextVersion.id.in_(list(text_version_ids)))
        ).scalars().all()
    page_ids_by_version_id = {version.id: version.page_id for version in versions}
    return [
        page_ids_by_version_id[text_version_id]
        for text_version_id in text_version_ids
        if text_version_id in page_ids_by_version_id
    ]
