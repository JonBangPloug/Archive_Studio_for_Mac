"""Page operation tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest
from sqlalchemy import select

from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import Page, STAGE_ORIGINAL, TextVersion
from archivestudio.core import page_operations as page_operations_module
from archivestudio.core.page_operations import (
    delete_project_page,
    delete_project_pages,
    move_project_pages,
    PageOperationError,
    rotate_project_pages,
)
from archivestudio.core.project import create_project
from archivestudio.core.tasks.text_versions import save_manual_text_version


def test_delete_project_page_removes_page_text_versions_and_image(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Delete Page")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (40, 30), color="red").save(source_dir / "page1.png")
    Image.new("RGB", (40, 30), color="blue").save(source_dir / "page2.png")

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            save_manual_text_version(
                session,
                page_id=pages[0].id,
                stage=STAGE_ORIGINAL,
                content="first page text",
            )
            deleted_image_path = project.root / pages[0].image_path

        deleted = delete_project_page(project, page_id=pages[0].id)

        assert deleted.sequence == 1
        assert not deleted_image_path.exists()

        with project.session() as session:
            remaining_pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            remaining_versions = session.execute(select(TextVersion)).scalars().all()

        assert [page.sequence for page in remaining_pages] == [2]
        assert len(remaining_versions) == 0
    finally:
        project.close()


def test_delete_project_pages_removes_multiple_pages(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-bulk-delete", name="Delete Many Pages")
    source_dir = tmp_path / "images-bulk"
    source_dir.mkdir()
    for index, color in enumerate(("red", "blue", "green"), start=1):
        Image.new("RGB", (40, 30), color=color).save(source_dir / f"page{index}.png")

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            deleted_ids = [pages[0].id, pages[2].id]

        deleted = delete_project_pages(project, page_ids=deleted_ids)

        assert [page.sequence for page in deleted] == [1, 3]
        with project.session() as session:
            remaining_pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
        assert [page.sequence for page in remaining_pages] == [2]
    finally:
        project.close()


def test_move_project_pages_up_moves_selected_block(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-move-up", name="Move Pages Up")
    source_dir = tmp_path / "images-up"
    source_dir.mkdir()
    for index in range(1, 5):
        Image.new("RGB", (40, 30), color=(index * 30, 0, 0)).save(source_dir / f"page{index}.png")

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            moved_ids = [pages[2].id, pages[3].id]

        changed = move_project_pages(project, page_ids=moved_ids, direction="up")

        assert changed
        with project.session() as session:
            reordered = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
        assert [page.id for page in reordered] == [pages[0].id, pages[2].id, pages[3].id, pages[1].id]
    finally:
        project.close()


def test_move_project_pages_down_moves_selected_block(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-move-down", name="Move Pages Down")
    source_dir = tmp_path / "images-down"
    source_dir.mkdir()
    for index in range(1, 5):
        Image.new("RGB", (40, 30), color=(0, index * 30, 0)).save(source_dir / f"page{index}.png")

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
            moved_ids = [pages[0].id, pages[1].id]

        changed = move_project_pages(project, page_ids=moved_ids, direction="down")

        assert changed
        with project.session() as session:
            reordered = session.execute(select(Page).order_by(Page.sequence)).scalars().all()
        assert [page.id for page in reordered] == [pages[2].id, pages[0].id, pages[1].id, pages[3].id]
    finally:
        project.close()


def test_rotate_project_pages_rotates_selected_images_clockwise(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project-rotate", name="Rotate Pages")
    source_dir = tmp_path / "images-rotate"
    source_dir.mkdir()
    Image.new("RGB", (40, 30), color="red").save(source_dir / "page1.png")
    Image.new("RGB", (50, 20), color="blue").save(source_dir / "page2.png")

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()

        rotated = rotate_project_pages(project, page_ids=[pages[0].id, pages[1].id])

        assert [page.sequence for page in rotated] == [1, 2]

        with Image.open(project.root / pages[0].image_path) as first_image:
            assert first_image.size == (30, 40)
        with Image.open(project.root / pages[1].image_path) as second_image:
            assert second_image.size == (20, 50)
    finally:
        project.close()


def test_rotate_project_pages_restores_originals_on_replace_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = create_project(tmp_path / "project-rotate-rollback", name="Rotate Rollback")
    source_dir = tmp_path / "images-rotate-rollback"
    source_dir.mkdir()
    Image.new("RGB", (40, 30), color="red").save(source_dir / "page1.png")
    Image.new("RGB", (50, 20), color="blue").save(source_dir / "page2.png")

    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> Path:
        if self.name.startswith("page_0002_rotate_") and target.name == "page_0002.png":
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(page_operations_module.Path, "replace", flaky_replace)

    try:
        import_image_folder(project, source_dir, source_type="printed")
        with project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()

        with pytest.raises(PageOperationError):
            rotate_project_pages(project, page_ids=[pages[0].id, pages[1].id])

        with Image.open(project.root / pages[0].image_path) as first_image:
            assert first_image.size == (40, 30)
        with Image.open(project.root / pages[1].image_path) as second_image:
            assert second_image.size == (50, 20)
    finally:
        project.close()
