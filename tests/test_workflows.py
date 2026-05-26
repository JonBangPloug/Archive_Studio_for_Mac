"""Workflow tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from archivestudio.core.ai.base import AIProvider, CorrectionResult, TranscriptionResult
from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import STAGE_CORRECTED, STAGE_ORIGINAL, Page, TextVersion
from archivestudio.core.project import create_project
from archivestudio.core.tasks import get_builtin_preset
from archivestudio.core.tasks.text_versions import save_manual_text_version
from archivestudio.core.tasks.workflows import (
    HANDWRITTEN_HTR_CORRECTION_WORKFLOW,
    PRINTED_OCR_CORRECTION_WORKFLOW,
    run_handwritten_htr_and_correction,
    run_printed_ocr_and_correction,
)


class FakeWorkflowProvider(AIProvider):
    provider_name = "fake"
    model_id = "workflow-model"
    supports_batching = True

    def __init__(self) -> None:
        self.batch_sequences: list[list[int]] = []
        self.correction_sequences: list[int] = []

    def transcribe_pages(self, requests, *, model_config):
        self.batch_sequences.append([request.page_sequence for request in requests])
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription=f"transcribed page {request.page_sequence}",
            )
            for request in requests
        ]

    def correct_pages(self, requests, *, model_config):
        self.correction_sequences.extend(request.page_sequence for request in requests)
        return [
            CorrectionResult(
                page_id=request.page_id,
                corrected_text=f"corrected::{request.source_text}",
            )
            for request in requests
        ]


def test_handwritten_htr_and_correction_workflow_creates_both_stages(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Workflow")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (50, 40), color="red").save(source_dir / "page1.png")
    Image.new("RGB", (50, 40), color="blue").save(source_dir / "page2.png")
    import_image_folder(project, source_dir, source_type="handwritten")

    provider = FakeWorkflowProvider()

    try:
        summary = run_handwritten_htr_and_correction(project, provider)

        assert summary.workflow_name == HANDWRITTEN_HTR_CORRECTION_WORKFLOW
        assert summary.pages_requested == 2
        assert summary.pages_completed == 2
        assert summary.pages_failed == 0
        assert summary.final_stage == "corrected"
        assert len(summary.step_summaries) == 2

        with project.session() as session:
            versions = session.execute(
                select(TextVersion).order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert [version.stage for version in versions] == [
            STAGE_ORIGINAL,
            STAGE_ORIGINAL,
            STAGE_CORRECTED,
            STAGE_CORRECTED,
        ]
        assert versions[2].content == "corrected::transcribed page 1"
        assert versions[3].content == "corrected::transcribed page 2"
    finally:
        project.close()


def test_workflow_corrects_only_pages_transcribed_in_current_run(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-partial", name="Partial Workflow")
    source_dir = tmp_path / "images-partial"
    source_dir.mkdir()
    Image.new("RGB", (50, 40), color="red").save(source_dir / "page1.png")
    Image.new("RGB", (50, 40), color="blue").save(source_dir / "page2.png")
    import_image_folder(project, source_dir, source_type="printed")

    class PartialProvider(FakeWorkflowProvider):
        def transcribe_pages(self, requests, *, model_config):
            self.batch_sequences.append([request.page_sequence for request in requests])
            return [
                TranscriptionResult(
                    page_id=request.page_id,
                    transcription=f"fresh page {request.page_sequence}",
                )
                for request in requests
                if request.page_sequence == 1
            ]

    provider = PartialProvider()

    try:
        with project.session() as session:
            page_two = session.execute(
                select(Page).where(Page.sequence == 2)
            ).scalar_one()
            save_manual_text_version(
                session,
                page_id=page_two.id,
                stage=STAGE_ORIGINAL,
                content="stale old OCR",
            )

        summary = run_printed_ocr_and_correction(project, provider)

        assert summary.pages_requested == 2
        assert summary.pages_completed == 1
        assert summary.pages_failed == 1
        assert provider.correction_sequences == [1]

        with project.session() as session:
            corrected_versions = session.execute(
                select(TextVersion)
                .join(Page, Page.id == TextVersion.page_id)
                .where(TextVersion.stage == STAGE_CORRECTED)
                .order_by(Page.sequence)
            ).scalars().all()

        assert len(corrected_versions) == 1
        assert corrected_versions[0].content == "corrected::fresh page 1"
    finally:
        project.close()


def test_printed_ocr_and_correction_workflow_creates_both_stages(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-printed", name="Printed Workflow")
    source_dir = tmp_path / "images-printed"
    source_dir.mkdir()
    Image.new("RGB", (50, 40), color="green").save(source_dir / "page1.png")
    Image.new("RGB", (50, 40), color="yellow").save(source_dir / "page2.png")
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeWorkflowProvider()

    try:
        summary = run_printed_ocr_and_correction(project, provider)

        assert summary.workflow_name == PRINTED_OCR_CORRECTION_WORKFLOW
        assert summary.pages_requested == 2
        assert summary.pages_completed == 2
        assert summary.pages_failed == 0
        assert summary.final_stage == "corrected"
        assert len(summary.step_summaries) == 2

        with project.session() as session:
            versions = session.execute(
                select(TextVersion).order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert [version.stage for version in versions] == [
            STAGE_ORIGINAL,
            STAGE_ORIGINAL,
            STAGE_CORRECTED,
            STAGE_CORRECTED,
        ]
        assert versions[2].content == "corrected::transcribed page 1"
        assert versions[3].content == "corrected::transcribed page 2"
    finally:
        project.close()


def test_combined_workflow_uses_passed_transcription_preset_batching(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-batched", name="Workflow Batching")
    source_dir = tmp_path / "images-batched"
    source_dir.mkdir()
    for idx, color in enumerate(("red", "blue", "green", "yellow"), start=1):
        Image.new("RGB", (50, 40), color=color).save(source_dir / f"page{idx}.png")
    import_image_folder(project, source_dir, source_type="printed")

    provider = FakeWorkflowProvider()
    transcription_preset = replace(get_builtin_preset("Printed Transcription"), batch_size=2)

    try:
        summary = run_printed_ocr_and_correction(
            project,
            provider,
            transcription_preset=transcription_preset,
        )

        assert summary.pages_completed == 4
        assert provider.batch_sequences == [[1, 2], [3, 4]]
    finally:
        project.close()


def test_combined_workflow_uses_separate_correction_provider(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-separate-provider", name="Workflow Providers")
    source_dir = tmp_path / "images-separate-provider"
    source_dir.mkdir()
    Image.new("RGB", (50, 40), color="red").save(source_dir / "page1.png")
    import_image_folder(project, source_dir, source_type="printed")

    transcription_provider = FakeWorkflowProvider()
    correction_provider = FakeWorkflowProvider()
    transcription_provider.model_id = "transcription-model"
    correction_provider.model_id = "correction-model"

    try:
        summary = run_printed_ocr_and_correction(
            project,
            transcription_provider,
            correction_provider=correction_provider,
        )

        assert summary.pages_completed == 1
        assert transcription_provider.batch_sequences == [[1]]
        assert transcription_provider.correction_sequences == []
        assert correction_provider.correction_sequences == [1]

        with project.session() as session:
            corrected = session.execute(
                select(TextVersion).where(TextVersion.stage == STAGE_CORRECTED)
            ).scalar_one()

        assert corrected.created_by == "ai:fake:correction-model"
    finally:
        project.close()
