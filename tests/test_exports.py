"""Export service tests."""

from __future__ import annotations

import json
import pytest

from sqlalchemy import select

from archivestudio.core.export import (
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    EXPORT_FORMAT_JSONL,
    EXPORT_FORMAT_MARKDOWN,
    EXPORT_FORMAT_TEXT,
    export_project_records,
)
from archivestudio.core.export.profiles import EXPORT_PROFILE_PATIENT_JOURNAL
from archivestudio.core.models import Page, STAGE_CORRECTED, STAGE_ORIGINAL, STAGE_TRANSLATED, TextVersion
from archivestudio.core.project import create_project
from archivestudio.core.tasks.text_versions import save_manual_text_version


def test_markdown_export_writes_structured_page_text(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Letterbook")
    try:
        page_id = _make_page_with_text(project, sequence=1, stage=STAGE_CORRECTED, content="# Heading\nBody")
        target = tmp_path / "export.md"

        result = export_project_records(
            project,
            export_format=EXPORT_FORMAT_MARKDOWN,
            selected_stage=STAGE_CORRECTED,
            scope_label="current page",
            page_ids=[page_id],
            output_path=target,
        )

        content = target.read_text(encoding="utf-8")
        assert result.output_path == target
        assert "# Letterbook" in content
        assert "## Page 0001" in content
        assert "### Corrected Text" in content
        assert "# Heading\nBody" in content
    finally:
        project.close()


def test_text_export_writes_plain_text_file(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Notes")
    try:
        page_id = _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="Body text")
        target = tmp_path / "export.txt"

        export_project_records(
            project,
            export_format=EXPORT_FORMAT_TEXT,
            selected_stage=STAGE_ORIGINAL,
            scope_label="current page",
            page_ids=[page_id],
            output_path=target,
        )

        content = target.read_text(encoding="utf-8")
        assert "# Notes" in content
        assert "## Page 0001" in content
        assert "Body text" in content
    finally:
        project.close()


def test_json_export_includes_all_current_text_versions(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Journals")
    try:
        page_id = _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="orig")
        with project.session() as session:
            save_manual_text_version(
                session,
                page_id=page_id,
                stage=STAGE_TRANSLATED,
                content="translated text",
            )

        target = tmp_path / "export.json"
        export_project_records(
            project,
            export_format=EXPORT_FORMAT_JSON,
            selected_stage=STAGE_TRANSLATED,
            scope_label="all pages",
            output_path=target,
        )

        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["project"]["name"] == "Journals"
        assert payload["export"]["selected_stage"] == STAGE_TRANSLATED
        assert payload["records"][0]["text_versions"][STAGE_ORIGINAL] == "orig"
        assert payload["records"][0]["text_versions"][STAGE_TRANSLATED] == "translated text"
        assert payload["records"][0]["selected_text"] == "translated text"
    finally:
        project.close()


def test_json_export_supports_patient_journal_profile(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Patients")
    try:
        page_id = _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="journal entry")
        target = tmp_path / "patient.json"
        export_project_records(
            project,
            export_format=EXPORT_FORMAT_JSON,
            export_profile=EXPORT_PROFILE_PATIENT_JOURNAL,
            selected_stage=STAGE_ORIGINAL,
            scope_label="current page",
            page_ids=[page_id],
            output_path=target,
        )

        payload = json.loads(target.read_text(encoding="utf-8"))
        record = payload["records"][0]
        assert payload["export"]["profile"] == EXPORT_PROFILE_PATIENT_JOURNAL
        assert record["record_type"] == "patient_journal_page"
        assert record["journal_text"]["selected_text"] == "journal entry"
        assert "structured_fields" in record
    finally:
        project.close()


def test_jsonl_export_writes_one_record_per_line(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Patients")
    try:
        _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="page one")
        _make_page_with_text(project, sequence=2, stage=STAGE_ORIGINAL, content="page two")

        target = tmp_path / "export.jsonl"
        export_project_records(
            project,
            export_format=EXPORT_FORMAT_JSONL,
            selected_stage=STAGE_ORIGINAL,
            scope_label="all pages",
            output_path=target,
        )

        lines = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2
        assert lines[0]["page_sequence"] == 1
        assert lines[1]["page_sequence"] == 2
        assert lines[0]["selected_text"] == "page one"
        assert lines[1]["selected_text"] == "page two"
    finally:
        project.close()


def test_csv_export_writes_page_rows(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Sheets")
    try:
        _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="page one")
        target = tmp_path / "export.csv"
        export_project_records(
            project,
            export_format=EXPORT_FORMAT_CSV,
            selected_stage=STAGE_ORIGINAL,
            scope_label="all pages",
            output_path=target,
        )

        content = target.read_text(encoding="utf-8")
        assert "project_name,page_id,page_sequence" in content
        assert "Sheets" in content
        assert "page one" in content
    finally:
        project.close()


def test_export_rejects_invalid_selected_stage(tmp_path) -> None:
    project = create_project(tmp_path / "project", name="Invalid Stage")
    try:
        _make_page_with_text(project, sequence=1, stage=STAGE_ORIGINAL, content="page one")
        with pytest.raises(ValueError, match="Unsupported export stage"):
            export_project_records(
                project,
                export_format=EXPORT_FORMAT_TEXT,
                selected_stage="not-a-real-stage",
                scope_label="all pages",
            )
    finally:
        project.close()


def _make_page_with_text(project, *, sequence: int, stage: str, content: str) -> str:
    with project.session() as session:
        page = Page(sequence=sequence, image_path=f"images/page_{sequence:04d}.png")
        session.add(page)
        session.flush()
        page_id = page.id
        save_manual_text_version(
            session,
            page_id=page_id,
            stage=stage,
            content=content,
        )
        return page_id
