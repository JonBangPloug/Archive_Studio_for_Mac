"""Project lifecycle and Stage 1 import tests."""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image
import pytest
from sqlalchemy import select

from archivestudio.core.ingest import (
    import_image_file,
    import_image_files,
    import_image_folder,
    import_pdf,
)
from archivestudio.core.ingest.images import ImageImportError
from archivestudio.core.models import (
    Page,
    ProjectInfo,
    SCHEMA_VERSION,
    STAGE_ORIGINAL,
    TextVersion,
)
from archivestudio.core.project import (
    PROJECT_DB_FILENAME,
    ProjectExistsError,
    ProjectNotFoundError,
    available_project_root,
    create_project,
    create_project_with_available_name,
    open_project,
    rename_project,
    safe_project_name,
)


def test_create_and_open_project(tmp_project_root: Path) -> None:
    project = create_project(tmp_project_root, name="Test Letterbook")
    try:
        assert project.root == tmp_project_root
        assert (tmp_project_root / PROJECT_DB_FILENAME).is_file()
        assert (tmp_project_root / "images").is_dir()
        assert (tmp_project_root / "exports").is_dir()

        with project.session() as s:
            info = s.execute(select(ProjectInfo)).scalar_one()
            assert info.name == "Test Letterbook"
            assert info.schema_version == SCHEMA_VERSION
    finally:
        project.close()

    reopened = open_project(tmp_project_root)
    try:
        assert reopened.name == "Test Letterbook"
    finally:
        reopened.close()


def test_create_project_rejects_nonempty_dir(tmp_project_root: Path) -> None:
    tmp_project_root.mkdir(parents=True)
    (tmp_project_root / "stray.txt").write_text("hello")

    with pytest.raises(ProjectExistsError):
        create_project(tmp_project_root, name="Nope")


def test_available_project_root_adds_suffix_for_name_collision(tmp_path: Path) -> None:
    parent = tmp_path / "projects"
    parent.mkdir()
    (parent / "Ledger").mkdir()
    (parent / "Ledger" / "project.db").write_text("existing")

    assert available_project_root(parent, "Ledger") == parent / "Ledger 2"


def test_create_project_with_available_name_sanitizes_and_uses_safe_variant(tmp_path: Path) -> None:
    parent = tmp_path / "projects"
    parent.mkdir()
    create_project(parent / "Archive Project", name="Archive Project").close()

    project = create_project_with_available_name(parent, "  Archive/Project:  ")
    try:
        assert project.name == "Archive Project 2"
        assert project.root == parent / "Archive Project 2"
        assert project.db_path.exists()
    finally:
        project.close()


def test_rename_project_updates_project_info_without_moving_folder(tmp_project_root: Path) -> None:
    project = create_project(tmp_project_root, name="Old Name")
    try:
        rename_project(project, "New/Name:")
        assert project.name == "New Name"
        assert project.root == tmp_project_root
    finally:
        project.close()

    reopened = open_project(tmp_project_root)
    try:
        assert reopened.name == "New Name"
    finally:
        reopened.close()


def test_safe_project_name_falls_back_for_empty_names() -> None:
    assert safe_project_name("///") == "Archive Project"


def test_open_project_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        open_project(tmp_path / "does-not-exist")


def test_text_version_current_uniqueness(tmp_project_root: Path) -> None:
    """Two rows with is_current=True for the same (page, stage) must violate the index."""
    project = create_project(tmp_project_root, name="Uniq")
    try:
        with project.session() as s:
            page = Page(sequence=1, image_path="images/p001.png")
            s.add(page)
            s.flush()

            s.add(TextVersion(
                page_id=page.id,
                stage=STAGE_ORIGINAL,
                content="first",
                created_by="user",
                is_current=True,
            ))

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            with project.session() as s:
                page_id = s.execute(select(Page.id)).scalar_one()
                s.add(TextVersion(
                    page_id=page_id,
                    stage=STAGE_ORIGINAL,
                    content="second",
                    created_by="user",
                    is_current=True,
                ))

        # A non-current second row is fine.
        with project.session() as s:
            page_id = s.execute(select(Page.id)).scalar_one()
            s.add(TextVersion(
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="second-but-historical",
                created_by="user",
                is_current=False,
            ))
    finally:
        project.close()


def test_import_image_folder_creates_pages_in_natural_order(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    source_dir = tmp_path / "images_in"
    source_dir.mkdir()

    Image.new("RGB", (40, 30), color="red").save(source_dir / "page10.png")
    Image.new("RGB", (40, 30), color="blue").save(source_dir / "page2.png")

    project = create_project(project_root, name="Image Import")
    try:
        result = import_image_folder(project, source_dir, source_type="printed")
        assert result.page_count == 2

        with project.session() as s:
            pages = s.execute(select(Page).order_by(Page.sequence)).scalars().all()

        assert [page.sequence for page in pages] == [1, 2]
        assert [page.image_path for page in pages] == [
            "images/page_0001.png",
            "images/page_0002.png",
        ]
        assert pages[0].source_type == "printed"
        assert pages[0].notes == "Imported from image file: page2.png"
        assert pages[1].notes == "Imported from image file: page10.png"
        assert (project.images_dir / "page_0001.png").is_file()
        assert (project.images_dir / "page_0002.png").is_file()
    finally:
        project.close()


def test_import_image_file_creates_single_page(tmp_path: Path) -> None:
    project_root = tmp_path / "project-single"
    image_path = tmp_path / "single.png"
    Image.new("RGB", (40, 30), color="purple").save(image_path)

    project = create_project(project_root, name="Single Image Import")
    try:
        result = import_image_file(project, image_path, source_type="handwritten")
        assert result.page_count == 1

        with project.session() as s:
            pages = s.execute(select(Page).order_by(Page.sequence)).scalars().all()

        assert [page.sequence for page in pages] == [1]
        assert [page.image_path for page in pages] == ["images/page_0001.png"]
        assert pages[0].source_type == "handwritten"
        assert pages[0].notes == "Imported from image file: single.png"
        assert (project.images_dir / "page_0001.png").is_file()
    finally:
        project.close()


def test_import_image_files_creates_multiple_pages_in_natural_order(tmp_path: Path) -> None:
    project_root = tmp_path / "project-multi"
    image_one = tmp_path / "page10.png"
    image_two = tmp_path / "page2.png"
    Image.new("RGB", (40, 30), color="orange").save(image_one)
    Image.new("RGB", (40, 30), color="cyan").save(image_two)

    project = create_project(project_root, name="Multi Image Import")
    try:
        result = import_image_files(
            project,
            [image_one, image_two],
            source_type="printed",
        )
        assert result.page_count == 2

        with project.session() as s:
            pages = s.execute(select(Page).order_by(Page.sequence)).scalars().all()

        assert [page.sequence for page in pages] == [1, 2]
        assert [page.image_path for page in pages] == [
            "images/page_0001.png",
            "images/page_0002.png",
        ]
        assert pages[0].notes == "Imported from image file: page2.png"
        assert pages[1].notes == "Imported from image file: page10.png"
    finally:
        project.close()


def test_import_image_folder_rejects_empty_directory(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Empty Import")
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    try:
        with pytest.raises(ImageImportError):
            import_image_folder(project, empty_dir)
    finally:
        project.close()


def test_import_pdf_appends_pages_after_existing_images(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="PDF Import")

    image_dir = tmp_path / "images_in"
    image_dir.mkdir()
    Image.new("RGB", (30, 20), color="green").save(image_dir / "page1.jpg")

    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    for idx in range(2):
        page = document.new_page(width=200, height=100)
        page.insert_text((24, 50), f"Sample page {idx + 1}")
    document.save(pdf_path)
    document.close()

    try:
        import_image_folder(project, image_dir, source_type="handwritten")
        result = import_pdf(project, pdf_path, source_type="printed", dpi=100)

        assert result.page_count == 2

        with project.session() as s:
            pages = s.execute(select(Page).order_by(Page.sequence)).scalars().all()

        assert [page.sequence for page in pages] == [1, 2, 3]
        assert [page.image_path for page in pages] == [
            "images/page_0001.jpg",
            "images/page_0002.png",
            "images/page_0003.png",
        ]
        assert pages[1].notes == "Imported from PDF: sample.pdf page 1"
        assert pages[2].notes == "Imported from PDF: sample.pdf page 2"
        assert (project.images_dir / "page_0002.png").is_file()
        assert (project.images_dir / "page_0003.png").is_file()
    finally:
        project.close()
