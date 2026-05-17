"""Stage 2 task and provider tests."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PIL import Image
import pytest
from sqlalchemy import select

from archivestudio.core.ai.base import (
    AIProvider,
    CorrectionResult,
    TranslationResult,
    TranscriptionResult,
)
from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import (
    STAGE_CORRECTED,
    STAGE_ORIGINAL,
    STAGE_TRANSLATED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    Page,
    TaskRun,
    TextVersion,
)
from archivestudio.core.project import create_project
from archivestudio.core.tasks import (
    get_builtin_preset,
    run_correction,
    run_transcription,
    run_translation,
)
from archivestudio.core.tasks.artifacts import task_run_artifact_path
from archivestudio.core.tasks.cancellation import CancellationToken
from archivestudio.core.tasks.runs import TaskProgress


class FakeTranscriptionProvider(AIProvider):
    provider_name = "fake"
    model_id = "test-model"
    supports_batching = True

    def __init__(self) -> None:
        self.batch_sequences: list[list[int]] = []
        self.calls = 0
        self.last_transcription_prompts: list[str] = []

    def transcribe_pages(self, requests, *, model_config):
        self.calls += 1
        self.batch_sequences.append([request.page_sequence for request in requests])
        self.last_transcription_prompts = [request.prompt.user for request in requests]
        suffix = f"run-{self.calls}"
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription=f"page {request.page_sequence} {suffix}",
                raw_response=f"raw:{request.page_sequence}:{suffix}",
            )
            for request in requests
        ]

    def correct_pages(self, requests, *, model_config):
        return [
            CorrectionResult(
                page_id=request.page_id,
                corrected_text=f"corrected::{request.source_text}",
                raw_response=f"corrected:{request.page_sequence}",
            )
            for request in requests
        ]

    def translate_pages(self, requests, *, model_config):
        return [
            TranslationResult(
                page_id=request.page_id,
                translated_text=(
                    f"translated::{request.source_language}->{request.target_language}"
                    f"::{request.source_text_stage}::{request.source_text}"
                ),
                raw_response=f"translated:{request.page_sequence}:{request.source_text_stage}",
            )
            for request in requests
        ]


def _build_source_images(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for idx in range(1, count + 1):
        Image.new("RGB", (60, 40), color=(idx * 20, idx * 10, idx * 5)).save(
            folder / f"page{idx}.png"
        )


def test_run_transcription_creates_task_run_and_text_versions(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Task Run")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=3)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()
    preset = replace(
        get_builtin_preset("Handwritten Transcription"),
        batch_size=2,
        model_config=replace(
            get_builtin_preset("Handwritten Transcription").model_config,
            model_id="vision-model",
        ),
    )

    try:
        progress_events: list[TaskProgress] = []
        summary = run_transcription(
            project,
            provider,
            preset,
            progress_callback=progress_events.append,
        )

        assert summary.status == TASK_STATUS_COMPLETED
        assert summary.pages_requested == 3
        assert summary.pages_completed == 3
        assert summary.pages_failed == 0
        assert len(summary.created_text_version_ids) == 3
        assert provider.batch_sequences == [[1, 2], [3]]
        assert progress_events[0].pages_total == 3
        assert progress_events[0].pages_completed == 0
        assert progress_events[-1].pages_completed == 3
        assert progress_events[-1].pages_failed == 0
        assert any(event.current_pages == (1, 2) for event in progress_events)

        with project.session() as session:
            task_run = session.get(TaskRun, summary.task_run_id)
            assert task_run is not None
            assert task_run.status == TASK_STATUS_COMPLETED
            assert task_run.pages_requested == 3
            assert task_run.pages_completed == 3
            assert task_run.completed_at is not None

            text_versions = session.execute(
                select(TextVersion)
                .join(Page, Page.id == TextVersion.page_id)
                .order_by(Page.sequence, TextVersion.created_at)
            ).scalars().all()

        assert len(text_versions) == 3
        assert all(text_version.stage == STAGE_ORIGINAL for text_version in text_versions)
        assert all(text_version.is_current for text_version in text_versions)
        assert all(text_version.task_run_id == summary.task_run_id for text_version in text_versions)
        assert all(text_version.created_by == "ai:fake:test-model" for text_version in text_versions)
        assert [text_version.content for text_version in text_versions] == [
            "page 1 run-1",
            "page 2 run-1",
            "page 3 run-2",
        ]

        artifact = json.loads(
            task_run_artifact_path(project, summary.task_run_id).read_text(encoding="utf-8")
        )
        assert artifact["task_run_id"] == summary.task_run_id
        assert artifact["provider"] == {"name": "fake", "model_id": "test-model"}
        assert artifact["preset"]["name"] == "Handwritten Transcription"
        assert artifact["requests"][0]["prompt"]["user"]
        assert artifact["responses"][0]["raw_response"] == "raw:1:run-1"
    finally:
        project.close()


def test_run_transcription_can_be_cancelled_between_pages(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Cancel Task")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=3)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()
    preset = replace(get_builtin_preset("Handwritten Transcription"), batch_size=1)
    token = CancellationToken()

    def cancel_after_first_saved(progress: TaskProgress) -> None:
        if progress.pages_completed >= 1:
            token.cancel()

    try:
        summary = run_transcription(
            project,
            provider,
            preset,
            progress_callback=cancel_after_first_saved,
            cancellation_token=token,
        )

        assert summary.status == TASK_STATUS_CANCELLED
        assert summary.pages_requested == 3
        assert summary.pages_completed == 1
        assert summary.pages_failed == 0
        assert summary.errors == ["Task cancelled by user"]
        assert provider.calls == 1

        with project.session() as session:
            task_run = session.get(TaskRun, summary.task_run_id)
            assert task_run is not None
            assert task_run.status == TASK_STATUS_CANCELLED
            versions = session.execute(select(TextVersion)).scalars().all()
            assert len(versions) == 1
    finally:
        project.close()


def test_run_transcription_replaces_current_original_and_links_source_version(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Task Rerun")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeTranscriptionProvider()
    preset = replace(get_builtin_preset("Printed Transcription"), batch_size=1)

    try:
        first = run_transcription(project, provider, preset)
        second = run_transcription(project, provider, preset)

        with project.session() as session:
            page = session.execute(select(Page)).scalar_one()
            versions = session.execute(
                select(TextVersion)
                .where(TextVersion.page_id == page.id, TextVersion.stage == STAGE_ORIGINAL)
                .order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert first.status == TASK_STATUS_COMPLETED
        assert second.status == TASK_STATUS_COMPLETED
        assert len(versions) == 2
        assert versions[0].is_current is False
        assert versions[1].is_current is True
        assert versions[1].source_version_id == versions[0].id
        assert versions[1].task_run_id == second.task_run_id
        assert versions[1].content == "page 1 run-2"
    finally:
        project.close()


def test_run_correction_creates_corrected_text_linked_to_original(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Correction Run")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=2)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    try:
        transcription_summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=2),
        )
        correction_summary = run_correction(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Correction"), batch_size=2),
        )

        assert transcription_summary.status == TASK_STATUS_COMPLETED
        assert correction_summary.status == TASK_STATUS_COMPLETED
        assert correction_summary.pages_completed == 2

        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            corrected_versions = session.execute(
                select(TextVersion)
                .join(Page, Page.id == TextVersion.page_id)
                .where(TextVersion.stage == STAGE_CORRECTED)
                .order_by(Page.sequence, TextVersion.created_at)
            ).scalars().all()

            originals = {
                page.id: session.execute(
                    select(TextVersion).where(
                        TextVersion.page_id == page.id,
                        TextVersion.stage == STAGE_ORIGINAL,
                        TextVersion.is_current.is_(True),
                    )
                ).scalar_one()
                for page in pages
            }

        assert len(corrected_versions) == 2
        assert all(version.is_current for version in corrected_versions)
        assert all(version.task_run_id == correction_summary.task_run_id for version in corrected_versions)
        assert corrected_versions[0].content == "corrected::page 1 run-1"
        assert corrected_versions[1].content == "corrected::page 2 run-1"
        assert corrected_versions[0].source_version_id == originals[pages[0].id].id
        assert corrected_versions[1].source_version_id == originals[pages[1].id].id
    finally:
        project.close()


def test_run_translation_falls_back_to_corrected_text(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Translation Fallback")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeTranscriptionProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Printed Transcription"), batch_size=1),
        )
        run_correction(
            project,
            provider,
            replace(get_builtin_preset("Printed Correction"), batch_size=1),
        )
        translation_summary = run_translation(
            project,
            provider,
            replace(get_builtin_preset("Scholarly Translation to English"), batch_size=1),
        )

        assert translation_summary.status == TASK_STATUS_COMPLETED

        with project.session() as session:
            corrected = session.execute(
                select(TextVersion).where(
                    TextVersion.stage == STAGE_CORRECTED,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()
            translated = session.execute(
                select(TextVersion).where(
                    TextVersion.stage == STAGE_TRANSLATED,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()

        assert translated.source_version_id == corrected.id
        assert "::corrected::" in translated.content
    finally:
        project.close()


def test_run_translation_falls_back_to_original_text(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Translation Original Fallback")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeTranscriptionProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Printed Transcription"), batch_size=1),
        )
        translation_summary = run_translation(
            project,
            provider,
            replace(get_builtin_preset("Scholarly Translation to English"), batch_size=1),
        )

        assert translation_summary.status == TASK_STATUS_COMPLETED

        with project.session() as session:
            original = session.execute(
                select(TextVersion).where(
                    TextVersion.stage == STAGE_ORIGINAL,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()
            translated = session.execute(
                select(TextVersion).where(
                    TextVersion.stage == STAGE_TRANSLATED,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()

        assert translated.source_version_id == original.id
        assert "::original::" in translated.content
    finally:
        project.close()


def test_custom_transcription_preset_includes_custom_instructions_in_prompt(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Custom Prompt")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="custom")

    provider = FakeTranscriptionProvider()
    preset = replace(
        get_builtin_preset("Custom Transcription"),
        custom_instructions="Preserve page headers and render marginal notes in [MARGIN:] blocks.",
    )

    try:
        summary = run_transcription(project, provider, preset)

        assert summary.status == TASK_STATUS_COMPLETED
        assert provider.last_transcription_prompts
        assert "Preserve page headers" in provider.last_transcription_prompts[0]
        assert "Additional user instructions" in provider.last_transcription_prompts[0]
    finally:
        project.close()


def test_run_transcription_marks_task_run_failed_when_prompt_rendering_crashes(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Task Crash")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()
    base_preset = get_builtin_preset("Handwritten Transcription")
    bad_preset = replace(
        base_preset,
        prompt_template=replace(
            base_preset.prompt_template,
            user_prompt_template="This placeholder will fail: {unknown_placeholder}",
        ),
    )

    try:
        with pytest.raises(KeyError):
            run_transcription(project, provider, bad_preset)

        with project.session() as session:
            task_run = session.execute(select(TaskRun)).scalar_one()

        assert task_run.status == TASK_STATUS_FAILED
        assert task_run.pages_completed == 0
        assert task_run.pages_failed == 1
        assert task_run.completed_at is not None
        assert task_run.error_message
    finally:
        project.close()


def test_run_correction_marks_task_run_failed_when_prompt_rendering_crashes(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Correction Crash")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=1),
        )
        base_preset = get_builtin_preset("Handwritten Correction")
        bad_preset = replace(
            base_preset,
            prompt_template=replace(
                base_preset.prompt_template,
                user_prompt_template="This placeholder will fail: {unknown_placeholder}",
            ),
        )

        with pytest.raises(KeyError):
            run_correction(project, provider, bad_preset)

        with project.session() as session:
            task_run = session.execute(
                select(TaskRun).where(TaskRun.task_type == "correct")
            ).scalar_one()

        assert task_run.status == TASK_STATUS_FAILED
        assert task_run.pages_completed == 0
        assert task_run.pages_failed == 1
        assert task_run.completed_at is not None
        assert task_run.error_message
    finally:
        project.close()


def test_run_translation_marks_task_run_failed_when_prompt_rendering_crashes(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Translation Crash")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeTranscriptionProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Printed Transcription"), batch_size=1),
        )
        base_preset = get_builtin_preset("Scholarly Translation to English")
        bad_preset = replace(
            base_preset,
            prompt_template=replace(
                base_preset.prompt_template,
                user_prompt_template="This placeholder will fail: {unknown_placeholder}",
            ),
        )

        with pytest.raises(KeyError):
            run_translation(project, provider, bad_preset)

        with project.session() as session:
            task_run = session.execute(
                select(TaskRun).where(TaskRun.task_type == "translate")
            ).scalar_one()

        assert task_run.status == TASK_STATUS_FAILED
        assert task_run.pages_completed == 0
        assert task_run.pages_failed == 1
        assert task_run.completed_at is not None
        assert task_run.error_message
    finally:
        project.close()
