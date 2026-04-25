"""Text-version helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from archivestudio.core.models import Page, STAGE_ORIGINAL, STAGE_TRANSLATED, TextVersion
from archivestudio.core.project import create_project
from archivestudio.core.tasks.text_versions import replace_current_text_version, save_manual_text_version


def test_save_manual_text_version_creates_and_replaces_current_row(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Manual Save")
    try:
        with project.session() as session:
            page = Page(sequence=1, image_path="images/page_0001.png")
            session.add(page)
            session.flush()
            page_id = page.id

        with project.session() as session:
            first = save_manual_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="first text",
            )

        with project.session() as session:
            second = save_manual_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="second text",
            )
            versions = session.execute(
                select(TextVersion)
                .where(TextVersion.page_id == page_id, TextVersion.stage == STAGE_ORIGINAL)
                .order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert len(versions) == 2
        assert versions[0].id == first.id
        assert versions[0].is_current is False
        assert versions[1].id == second.id
        assert versions[1].is_current is True
        assert versions[1].source_version_id == first.id
        assert versions[1].created_by == "user:manual_edit"
    finally:
        project.close()


def test_save_manual_text_version_keeps_stages_independent(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Manual Stages")
    try:
        with project.session() as session:
            page = Page(sequence=1, image_path="images/page_0001.png")
            session.add(page)
            session.flush()
            page_id = page.id

        with project.session() as session:
            save_manual_text_version(session, page_id=page_id, stage=STAGE_ORIGINAL, content="original")
            save_manual_text_version(session, page_id=page_id, stage=STAGE_TRANSLATED, content="translated")
            versions = session.execute(
                select(TextVersion)
                .where(TextVersion.page_id == page_id)
                .order_by(TextVersion.stage, TextVersion.created_at)
            ).scalars().all()

        assert len(versions) == 2
        assert {version.stage for version in versions} == {STAGE_ORIGINAL, STAGE_TRANSLATED}
        assert all(version.is_current for version in versions)
    finally:
        project.close()


def test_replace_current_text_version_flushes_demotion_before_insert(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Explicit Flush")
    try:
        with project.session() as session:
            page = Page(sequence=1, image_path="images/page_0001.png")
            session.add(page)
            session.flush()
            page_id = page.id

            replace_current_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="first text",
                created_by="user",
            )
            replace_current_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="second text",
                created_by="user",
            )

            versions = session.execute(
                select(TextVersion)
                .where(TextVersion.page_id == page_id, TextVersion.stage == STAGE_ORIGINAL)
                .order_by(TextVersion.created_at, TextVersion.id)
            ).scalars().all()

        assert len(versions) == 2
        assert [version.is_current for version in versions] == [False, True]
    except IntegrityError as exc:  # pragma: no cover - regression guard
        raise AssertionError("replace_current_text_version should not violate the current-row invariant") from exc
    finally:
        project.close()
