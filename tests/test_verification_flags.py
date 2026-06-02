"""Verification flag decision persistence tests."""

from pathlib import Path

from PIL import Image
from sqlalchemy import select

from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import (
    STAGE_ORIGINAL,
    VERIFICATION_FLAG_REPLACE,
    VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
    VERIFICATION_STATUS_KEPT_PRIMARY,
    VERIFICATION_STATUS_MANUAL_EDIT,
    VERIFICATION_STATUS_OPEN,
    VERIFICATION_STATUS_STALE,
    Page,
    TextVersion,
    VerificationFlag,
    VerificationResult,
)
from archivestudio.core.project import create_project
from archivestudio.core.tasks.text_versions import save_manual_text_version
from archivestudio.core.verification import (
    apply_pending_verification_decisions,
    link_decided_flags_to_text_version,
    load_open_verification_flags,
    mark_open_verification_flags_stale,
    mark_verification_flag_decision,
)
from archivestudio.ui.main_window import MainWindow, PageRecord


def test_verification_flag_decisions_can_link_to_manual_text_version(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", name="Flag Decisions")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (60, 40), color="white").save(source_dir / "page1.png")
    import_image_folder(project, source_dir, source_type="printed")

    try:
        with project.session() as session:
            page = session.execute(select(Page)).scalar_one()
            source_version = save_manual_text_version(
                session,
                page_id=page.id,
                stage=STAGE_ORIGINAL,
                content="Alpha beta",
            )
            result = VerificationResult(
                page_id=page.id,
                source_text_version_id=source_version.id,
                source_stage=STAGE_ORIGINAL,
                verifier_text="Alpha betta",
                alignment_status="ok",
            )
            session.add(result)
            session.flush()
            flag = VerificationFlag(
                verification_result_id=result.id,
                page_id=page.id,
                source_text_version_id=source_version.id,
                primary_start=6,
                primary_end=10,
                primary_text="beta",
                alternative_text="betta",
                flag_type=VERIFICATION_FLAG_REPLACE,
            )
            session.add(flag)
            session.flush()
            flag_id = flag.id
            source_version_id = source_version.id
            page_id = page.id

        with project.session() as session:
            assert len(
                load_open_verification_flags(
                    session,
                    page_id=page_id,
                    source_text_version_id=source_version_id,
                )
            ) == 1
            mark_verification_flag_decision(
                session,
                flag_id=flag_id,
                status=VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
            )
            new_version = save_manual_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="Alpha betta",
            )
            link_decided_flags_to_text_version(
                session,
                source_text_version_id=source_version_id,
                resulting_text_version_id=new_version.id,
            )

        with project.session() as session:
            flag = session.get(VerificationFlag, flag_id)

        assert flag is not None
        assert flag.status == VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE
        assert flag.resulting_text_version_id == new_version.id
    finally:
        project.close()


def test_pending_decisions_apply_on_save_and_stale_open_flags(tmp_path: Path) -> None:
    project, page_id, source_version_id, flag_ids = _build_flagged_project(
        tmp_path,
        flag_count=3,
    )
    try:
        with project.session() as session:
            replacement = save_manual_text_version(
                session,
                page_id=page_id,
                stage=STAGE_ORIGINAL,
                content="Alpha betta gamma",
            )
            apply_pending_verification_decisions(
                session,
                source_text_version_id=source_version_id,
                decisions={
                    flag_ids[0]: VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
                    flag_ids[1]: VERIFICATION_STATUS_MANUAL_EDIT,
                },
                resulting_text_version_id=replacement.id,
            )
            mark_open_verification_flags_stale(
                session,
                source_text_version_id=source_version_id,
            )

        with project.session() as session:
            flags = {
                flag.id: flag
                for flag in session.execute(select(VerificationFlag)).scalars().all()
            }

        assert flags[flag_ids[0]].status == VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE
        assert flags[flag_ids[0]].resulting_text_version_id == replacement.id
        assert flags[flag_ids[1]].status == VERIFICATION_STATUS_MANUAL_EDIT
        assert flags[flag_ids[1]].resulting_text_version_id == replacement.id
        assert flags[flag_ids[2]].status == VERIFICATION_STATUS_STALE
        assert flags[flag_ids[2]].resulting_text_version_id is None
    finally:
        project.close()


def test_use_alternative_without_save_does_not_persist_acceptance(qtbot, tmp_path: Path) -> None:
    project, page_id, _source_version_id, flag_ids = _build_flagged_project(tmp_path)
    window = None
    try:
        window = _open_window_on_page(qtbot, project, page_id)

        window._use_verification_alternative(flag_ids[0])

        assert "betta" in window.text_editor.toPlainText()
        assert window.text_editor.document().isModified()
        with project.session() as session:
            flag = session.get(VerificationFlag, flag_ids[0])
        assert flag is not None
        assert flag.status == VERIFICATION_STATUS_OPEN
        assert flag.resulting_text_version_id is None
    finally:
        _close_without_prompt(window)
        project.close()


def test_resolved_after_edit_without_save_does_not_persist_manual_decision(
    qtbot,
    tmp_path: Path,
) -> None:
    project, page_id, _source_version_id, flag_ids = _build_flagged_project(tmp_path)
    window = None
    try:
        window = _open_window_on_page(qtbot, project, page_id)
        window.text_editor.appendPlainText("manual note")

        window._mark_verification_manual_edit(flag_ids[0])

        with project.session() as session:
            flag = session.get(VerificationFlag, flag_ids[0])
        assert flag is not None
        assert flag.status == VERIFICATION_STATUS_OPEN
        assert flag.resulting_text_version_id is None
    finally:
        _close_without_prompt(window)
        project.close()


def test_save_changes_links_pending_decisions_and_stales_unresolved_flags(
    qtbot,
    tmp_path: Path,
) -> None:
    project, page_id, _source_version_id, flag_ids = _build_flagged_project(
        tmp_path,
        flag_count=3,
    )
    window = None
    try:
        window = _open_window_on_page(qtbot, project, page_id)

        window._use_verification_alternative(flag_ids[0])
        window._mark_verification_manual_edit(flag_ids[1])
        assert window._save_current_text_version() is True

        with project.session() as session:
            flags = {
                flag.id: flag
                for flag in session.execute(select(VerificationFlag)).scalars().all()
            }
            current = session.execute(
                select(TextVersion).where(
                    TextVersion.page_id == page_id,
                    TextVersion.stage == STAGE_ORIGINAL,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()

        assert flags[flag_ids[0]].status == VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE
        assert flags[flag_ids[0]].resulting_text_version_id == current.id
        assert flags[flag_ids[1]].status == VERIFICATION_STATUS_MANUAL_EDIT
        assert flags[flag_ids[1]].resulting_text_version_id == current.id
        assert flags[flag_ids[2]].status == VERIFICATION_STATUS_STALE
        assert flags[flag_ids[2]].resulting_text_version_id is None
        assert "betta" in current.content
    finally:
        _close_without_prompt(window)
        project.close()


def test_keep_current_is_immediate_and_not_staled_by_later_save(qtbot, tmp_path: Path) -> None:
    project, page_id, _source_version_id, flag_ids = _build_flagged_project(tmp_path)
    window = None
    try:
        window = _open_window_on_page(qtbot, project, page_id)

        window._keep_verification_primary(flag_ids[0])
        with project.session() as session:
            flag = session.get(VerificationFlag, flag_ids[0])
        assert flag is not None
        assert flag.status == VERIFICATION_STATUS_KEPT_PRIMARY
        assert flag.resulting_text_version_id is None

        window.text_editor.appendPlainText("later edit")
        assert window._save_current_text_version() is True

        with project.session() as session:
            flag = session.get(VerificationFlag, flag_ids[0])
        assert flag is not None
        assert flag.status == VERIFICATION_STATUS_KEPT_PRIMARY
        assert flag.resulting_text_version_id is None
    finally:
        _close_without_prompt(window)
        project.close()


def test_keep_current_does_not_clear_pending_alternative(qtbot, tmp_path: Path) -> None:
    project, page_id, _source_version_id, flag_ids = _build_flagged_project(
        tmp_path,
        flag_count=2,
    )
    window = None
    try:
        window = _open_window_on_page(qtbot, project, page_id)

        window._use_verification_alternative(flag_ids[0])
        window._keep_verification_primary(flag_ids[1])
        assert window._save_current_text_version() is True

        with project.session() as session:
            flags = {
                flag.id: flag
                for flag in session.execute(select(VerificationFlag)).scalars().all()
            }
            current = session.execute(
                select(TextVersion).where(
                    TextVersion.page_id == page_id,
                    TextVersion.stage == STAGE_ORIGINAL,
                    TextVersion.is_current.is_(True),
                )
            ).scalar_one()

        assert flags[flag_ids[0]].status == VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE
        assert flags[flag_ids[0]].resulting_text_version_id == current.id
        assert flags[flag_ids[1]].status == VERIFICATION_STATUS_KEPT_PRIMARY
        assert flags[flag_ids[1]].resulting_text_version_id is None
    finally:
        _close_without_prompt(window)
        project.close()


def _build_flagged_project(tmp_path: Path, *, flag_count: int = 1):
    project = create_project(tmp_path / "project", name="Flag Decisions")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (60, 40), color="white").save(source_dir / "page1.png")
    import_image_folder(project, source_dir, source_type="printed")

    with project.session() as session:
        page = session.execute(select(Page)).scalar_one()
        source_version = save_manual_text_version(
            session,
            page_id=page.id,
            stage=STAGE_ORIGINAL,
            content="Alpha beta gamma delta",
        )
        result = VerificationResult(
            page_id=page.id,
            source_text_version_id=source_version.id,
            source_stage=STAGE_ORIGINAL,
            verifier_text="Alpha betta gama delta",
            alignment_status="ok",
        )
        session.add(result)
        session.flush()
        flag_specs = [
            (6, 10, "beta", "betta"),
            (11, 16, "gamma", "gama"),
            (17, 22, "delta", "dellta"),
        ]
        flag_ids: list[str] = []
        for start, end, primary, alternative in flag_specs[:flag_count]:
            flag = VerificationFlag(
                verification_result_id=result.id,
                page_id=page.id,
                source_text_version_id=source_version.id,
                primary_start=start,
                primary_end=end,
                primary_text=primary,
                alternative_text=alternative,
                flag_type=VERIFICATION_FLAG_REPLACE,
            )
            session.add(flag)
            session.flush()
            flag_ids.append(flag.id)
        return project, page.id, source_version.id, flag_ids


def _open_window_on_page(qtbot, project, page_id: str) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window.project = project
    window._current_page_id = page_id
    window._current_stage = STAGE_ORIGINAL
    window._page_records = [
        PageRecord(
            id=page_id,
            sequence=1,
            image_path="images/page_0001.png",
            source_type="printed",
        )
    ]
    window._load_current_stage_text()
    return window


def _close_without_prompt(window: MainWindow | None) -> None:
    if window is None:
        return
    window.text_editor.document().setModified(False)
    window.close()
