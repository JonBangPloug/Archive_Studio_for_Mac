"""Demo provider integration tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from archivestudio.core.ai.demo import DemoAIProvider
from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import STAGE_CORRECTED, STAGE_ORIGINAL, STAGE_TRANSLATED, TextVersion
from archivestudio.core.project import create_project
from archivestudio.core.tasks import get_builtin_preset, run_correction, run_transcription, run_translation


def test_demo_provider_runs_core_text_pipeline(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Demo Provider")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (50, 40), color="navy").save(source_dir / "page1.png")
    import_image_folder(project, source_dir, source_type="printed")

    provider = DemoAIProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Printed Transcription"), batch_size=1),
        )
        run_correction(project, provider, replace(get_builtin_preset("Printed Correction"), batch_size=1))
        run_translation(
            project,
            provider,
            replace(get_builtin_preset("Scholarly Translation to English"), batch_size=1),
        )

        with project.session() as session:
            versions = session.execute(
                select(TextVersion).order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert [version.stage for version in versions] == [
            STAGE_ORIGINAL,
            STAGE_CORRECTED,
            STAGE_TRANSLATED,
        ]
        assert all(version.created_by == "ai:demo:local-preview" for version in versions)
        assert versions[0].content.startswith("[DEMO TRANSCRIPTION]")
        assert versions[1].content.startswith("[DEMO CORRECTION]")
        assert versions[2].content.startswith("[DEMO TRANSLATION]")
    finally:
        project.close()
