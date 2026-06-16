"""Stage 2 task and provider tests."""

from __future__ import annotations

import csv
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
    VERIFICATION_STATUS_OPEN,
    VERIFICATION_STATUS_STALE,
    Page,
    TaskRun,
    TextVersion,
    VerificationFlag,
    VerificationResult,
)
from archivestudio.core.project import create_project
from archivestudio.core.tasks import (
    get_builtin_preset,
    run_correction,
    run_transcription,
    run_translation,
    run_verification,
)
import archivestudio.core.tasks.checkpoints as checkpoints
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


class MissingSecondTranscriptionProvider(FakeTranscriptionProvider):
    def transcribe_pages(self, requests, *, model_config):
        results = super().transcribe_pages(requests, model_config=model_config)
        return results[:1]


def _build_source_images(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for idx in range(1, count + 1):
        Image.new("RGB", (60, 40), color=(idx * 20, idx * 10, idx * 5)).save(
            folder / f"page{idx}.png"
        )


def _checkpoint_path(project, stage: str, page_sequence: int) -> Path:
    return project.exports_dir / "checkpoints" / stage / f"page_{page_sequence:06d}.txt"


def _manifest_rows(project, stage: str) -> list[dict[str, str]]:
    path = project.exports_dir / "checkpoints" / stage / "manifest.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
        assert _checkpoint_path(project, STAGE_ORIGINAL, 1).read_text(encoding="utf-8") == "page 1 run-1"
        assert _checkpoint_path(project, STAGE_ORIGINAL, 2).read_text(encoding="utf-8") == "page 2 run-1"
        assert _checkpoint_path(project, STAGE_ORIGINAL, 3).read_text(encoding="utf-8") == "page 3 run-2"
        manifest_rows = _manifest_rows(project, STAGE_ORIGINAL)
        assert [row["status"] for row in manifest_rows] == ["completed", "completed", "completed"]
        assert manifest_rows[0]["output_filename"] == "page_000001.txt"
        assert manifest_rows[0]["provider"] == "fake"
        assert manifest_rows[0]["model"] == "test-model"

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
        assert _checkpoint_path(project, STAGE_ORIGINAL, 1).read_text(encoding="utf-8") == "page 1 run-2"
        manifest_rows = [
            row
            for row in _manifest_rows(project, STAGE_ORIGINAL)
            if row["status"] == "completed"
        ]
        assert len(manifest_rows) == 1
        assert manifest_rows[0]["text_version_id"] == versions[1].id
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
        assert _checkpoint_path(project, STAGE_CORRECTED, 1).read_text(encoding="utf-8") == "corrected::page 1 run-1"
        assert _checkpoint_path(project, STAGE_CORRECTED, 2).read_text(encoding="utf-8") == "corrected::page 2 run-1"
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
        assert _checkpoint_path(project, STAGE_TRANSLATED, 1).read_text(encoding="utf-8") == translated.content
    finally:
        project.close()


def test_checkpoint_writing_can_be_disabled(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="No Checkpoints")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    try:
        summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=1),
            write_checkpoints=False,
        )

        assert summary.status == TASK_STATUS_COMPLETED
        assert not (project.exports_dir / "checkpoints").exists()
        with project.session() as session:
            assert session.execute(select(TextVersion)).scalar_one().content == "page 1 run-1"
    finally:
        project.close()


def test_later_page_failure_keeps_earlier_checkpoint_and_records_manifest(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Partial Checkpoints")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=2)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = MissingSecondTranscriptionProvider()

    try:
        summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=2),
        )

        assert summary.pages_completed == 1
        assert summary.pages_failed == 1
        assert _checkpoint_path(project, STAGE_ORIGINAL, 1).read_text(encoding="utf-8") == "page 1 run-1"
        assert not _checkpoint_path(project, STAGE_ORIGINAL, 2).exists()
        rows = _manifest_rows(project, STAGE_ORIGINAL)
        assert [row["status"] for row in rows] == ["completed", "failed"]
        assert rows[1]["page_sequence"] == "2"
        assert "Provider returned no result" in rows[1]["error_message"]
    finally:
        project.close()


def test_checkpoint_failure_does_not_roll_back_saved_text_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path / "project", name="Checkpoint Failure")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    def fail_atomic_write(path: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(checkpoints, "_atomic_write_text", fail_atomic_write)

    try:
        summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=1),
        )

        assert summary.status == TASK_STATUS_COMPLETED
        assert summary.pages_completed == 1
        assert any("Checkpoint warning" in error for error in summary.errors)
        with project.session() as session:
            text_version = session.execute(select(TextVersion)).scalar_one()
        assert text_version.content == "page 1 run-1"
        assert text_version.is_current is True
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


def test_custom_transcription_preset_folds_custom_notes_into_source_notes(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Custom Prompt")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="custom")

    provider = FakeTranscriptionProvider()
    preset = replace(
        get_builtin_preset("Custom Transcription"),
        structure_rules="Entries are in two columns; keep each numbered entry separate.",
        custom_instructions="Preserve page headers and render marginal notes in [MARGIN:] blocks.",
    )

    try:
        summary = run_transcription(project, provider, preset)

        assert summary.status == TASK_STATUS_COMPLETED
        assert provider.last_transcription_prompts
        assert "Entries are in two columns" in provider.last_transcription_prompts[0]
        assert "Preserve page headers" in provider.last_transcription_prompts[0]
        assert "Source instructions:" in provider.last_transcription_prompts[0]
        assert "Additional user instructions" not in provider.last_transcription_prompts[0]
    finally:
        project.close()


def test_builtin_transcription_prompt_treats_sequence_as_internal_reference(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Prompt Shape")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    try:
        summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=1),
        )

        assert summary.status == TASK_STATUS_COMPLETED
        assert provider.last_transcription_prompts
        prompt = provider.last_transcription_prompts[0]
        assert "Transcribe the page shown in the image." in prompt
        assert "Internal app page sequence: 1." in prompt
        assert "Transcribe page 1" not in prompt
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


def test_run_verification_creates_review_flags_without_overwriting_text(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path / "project", name="Verification Run")
    source_dir = tmp_path / "images"
    _build_source_images(source_dir, count=1)
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeTranscriptionProvider()

    try:
        transcription_summary = run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Handwritten Transcription"), batch_size=1),
        )
        verification_summary = run_verification(
            project,
            provider,
            replace(get_builtin_preset("Independent Transcription Verification"), batch_size=1),
        )

        assert transcription_summary.status == TASK_STATUS_COMPLETED
        assert verification_summary.status == TASK_STATUS_COMPLETED
        assert verification_summary.pages_completed == 1

        with project.session() as session:
            original_versions = session.execute(
                select(TextVersion).where(TextVersion.stage == STAGE_ORIGINAL)
            ).scalars().all()
            result = session.execute(select(VerificationResult)).scalar_one()
            flags = session.execute(select(VerificationFlag)).scalars().all()

        assert len(original_versions) == 1
        assert original_versions[0].content == "page 1 run-1"
        assert result.source_text_version_id == original_versions[0].id
        assert result.verifier_text == "page 1 run-2"
        assert result.task_run_id == verification_summary.task_run_id
        assert len(flags) == 1
        assert flags[0].status == VERIFICATION_STATUS_OPEN
        assert flags[0].primary_text == "1"
        assert flags[0].alternative_text == "2"
    finally:
        project.close()


def test_run_verification_prefers_current_corrected_text(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Verification Source Stage")
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
        run_verification(
            project,
            provider,
            replace(get_builtin_preset("Independent Transcription Verification"), batch_size=1),
        )

        with project.session() as session:
            corrected = session.execute(
                select(TextVersion).where(
                    TextVersion.stage == STAGE_CORRECTED,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()
            result = session.execute(select(VerificationResult)).scalar_one()

        assert result.source_stage == STAGE_CORRECTED
        assert result.source_text_version_id == corrected.id
    finally:
        project.close()


def test_run_verification_marks_previous_open_flags_stale(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Verification Rerun")
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
        run_verification(
            project,
            provider,
            replace(get_builtin_preset("Independent Transcription Verification"), batch_size=1),
        )
        run_verification(
            project,
            provider,
            replace(get_builtin_preset("Independent Transcription Verification"), batch_size=1),
        )

        with project.session() as session:
            flags = session.execute(
                select(VerificationFlag).order_by(VerificationFlag.created_at)
            ).scalars().all()

        assert [flag.status for flag in flags] == [
            VERIFICATION_STATUS_STALE,
            VERIFICATION_STATUS_OPEN,
        ]
    finally:
        project.close()
