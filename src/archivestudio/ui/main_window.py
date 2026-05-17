"""Primary desktop window for project, page, image, and text workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from archivestudio import __display_name__
from archivestudio.core.ai import create_provider_from_settings
from archivestudio.core.config import load_app_settings, save_app_settings
from archivestudio.core.config.paths import default_projects_dir
from archivestudio.core.errors import classify_exception
from archivestudio.core.export import (
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    EXPORT_FORMAT_JSONL,
    EXPORT_FORMAT_MARKDOWN,
    EXPORT_FORMAT_TEXT,
    export_project_records,
)
from archivestudio.core.export.profiles import (
    EXPORT_PROFILE_GENERIC,
    EXPORT_PROFILE_LABELS,
    EXPORT_PROFILE_PATIENT_JOURNAL,
)
from archivestudio.core.ingest import import_image_files, import_image_folder, import_pdf
from archivestudio.core.models import STAGES, TASK_STATUS_CANCELLED, Page, TextVersion
from archivestudio.core.page_operations import (
    PageNotFoundError,
    delete_project_pages,
    move_project_pages,
    rotate_project_pages,
)
from archivestudio.core.project import (
    Project,
    available_project_root,
    create_project,
    create_project_with_available_name,
    open_project,
    rename_project,
    safe_project_name,
)
from archivestudio.core.tasks import (
    HANDWRITTEN_HTR_CORRECTION_WORKFLOW,
    PRINTED_OCR_CORRECTION_WORKFLOW,
    TASK_CORRECT,
    TASK_TRANSLATE,
    TASK_TRANSCRIBE,
    get_preset,
    list_presets,
    run_correction,
    run_handwritten_htr_and_correction,
    run_printed_ocr_and_correction,
    run_transcription,
    run_translation,
)
from archivestudio.core.tasks.runs import TaskProgress, TaskRunSummary
from archivestudio.core.tasks.cancellation import CancellationToken
from archivestudio.core.tasks.text_versions import get_current_text_version, save_manual_text_version
from archivestudio.core.tasks.workflows import WorkflowRunSummary
from archivestudio.ui.task_ranges import PageRangeParseError, parse_page_range_spec
from archivestudio.ui.task_launch import (
    TaskLaunch,
    TaskScopeSelection,
    prioritize_preset_names,
    recommended_preset_for_source_types,
    selected_source_types,
)
from archivestudio.ui.dialogs.settings_dialog import SettingsDialog
from archivestudio.ui.dialogs.activity_log_dialog import ActivityLogDialog
from archivestudio.ui.dialogs.task_prompt_settings_dialog import TaskPromptSettingsDialog
from archivestudio.ui.widgets.image_viewer import ImageViewer
from archivestudio.ui.workers.background_task_runner import BackgroundTaskRunner


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageRecord:
    id: str
    sequence: int
    image_path: str
    source_type: str | None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(__display_name__)
        self.resize(1400, 900)

        self.project: Project | None = None
        self._page_records: list[PageRecord] = []
        self._current_page_id: str | None = None
        self._current_stage = STAGES[0]
        self._loading_editor = False
        self._task_is_running = False
        self._active_task_launch: TaskLaunch | None = None
        self._background_tasks = BackgroundTaskRunner(self)
        self._background_tasks.finished.connect(self._on_background_task_finished)
        self._background_tasks.failed.connect(self._on_background_task_failed)
        self._background_tasks.cancelled.connect(self._on_background_task_cancelled)
        self._background_tasks.progress.connect(self._on_background_task_progress)
        self._background_tasks.running_changed.connect(self._on_background_task_running_changed)

        self._build_actions()
        self._build_ui()
        self._refresh_window_state()

        log.debug("MainWindow initialised")

    def closeEvent(self, event: QCloseEvent) -> None:  # pragma: no cover - GUI interaction
        if self._task_is_running:
            QMessageBox.information(
                self,
                "Task Running",
                "Please wait for the current background task to finish before closing the app.",
            )
            event.ignore()
            return

        if not self._maybe_resolve_unsaved_changes():
            event.ignore()
            return
        self._close_project()
        super().closeEvent(event)

    def _build_actions(self) -> None:
        self.new_project_action = QAction("New Project...", self)
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_project_action.triggered.connect(self._create_project_dialog)

        self.open_project_action = QAction("Open Project...", self)
        self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_project_action.triggered.connect(self._open_project_dialog)

        self.rename_project_action = QAction("Rename Project...", self)
        self.rename_project_action.triggered.connect(self._rename_project_dialog)

        self.import_image_action = QAction("Images...", self)
        self.import_image_action.triggered.connect(self._import_image_dialog)

        self.import_images_action = QAction("Image Folder...", self)
        self.import_images_action.triggered.connect(self._import_images_dialog)

        self.import_pdf_action = QAction("PDF...", self)
        self.import_pdf_action.triggered.connect(self._import_pdf_dialog)

        self.save_text_action = QAction("Save Changes", self)
        self.save_text_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_text_action.triggered.connect(self._save_current_text_version)

        self.delete_page_action = QAction("Delete Page(s)", self)
        self.delete_page_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self.delete_page_action.triggered.connect(self._delete_selected_page)

        self.move_page_up_action = QAction("Move Up", self)
        self.move_page_up_action.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Up))
        self.move_page_up_action.triggered.connect(lambda: self._move_selected_pages("up"))

        self.move_page_down_action = QAction("Move Down", self)
        self.move_page_down_action.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Down))
        self.move_page_down_action.triggered.connect(lambda: self._move_selected_pages("down"))

        self.rotate_pages_action = QAction("Rotate 90°", self)
        self.rotate_pages_action.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_R))
        self.rotate_pages_action.triggered.connect(self._rotate_selected_pages)

        self.export_text_action = QAction("Text...", self)
        self.export_text_action.triggered.connect(
            lambda: self._export_records_dialog(EXPORT_FORMAT_TEXT)
        )
        self.export_markdown_action = QAction("Markdown...", self)
        self.export_markdown_action.triggered.connect(
            lambda: self._export_records_dialog(EXPORT_FORMAT_MARKDOWN)
        )
        self.export_csv_action = QAction("CSV...", self)
        self.export_csv_action.triggered.connect(
            lambda: self._export_records_dialog(EXPORT_FORMAT_CSV)
        )
        self.export_json_action = QAction("JSON...", self)
        self.export_json_action.triggered.connect(
            lambda: self._export_records_dialog(EXPORT_FORMAT_JSON)
        )
        self.export_jsonl_action = QAction("JSONL...", self)
        self.export_jsonl_action.triggered.connect(
            lambda: self._export_records_dialog(EXPORT_FORMAT_JSONL)
        )

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)

        self.settings_action = QAction("Model...", self)
        preferences_key = getattr(QKeySequence.StandardKey, "Preferences", None)
        if preferences_key is not None:
            self.settings_action.setShortcut(preferences_key)
        self.settings_action.triggered.connect(self._open_settings_dialog)

        self.task_prompt_settings_action = QAction("Prompts...", self)
        self.task_prompt_settings_action.triggered.connect(self._open_task_prompt_settings_dialog)

        self.prev_page_action = QAction("Previous Page", self)
        self.prev_page_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Left))
        self.prev_page_action.triggered.connect(self._select_previous_page)

        self.next_page_action = QAction("Next Page", self)
        self.next_page_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Right))
        self.next_page_action.triggered.connect(self._select_next_page)

        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.triggered.connect(self._zoom_in)

        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.triggered.connect(self._zoom_out)

        self.fit_image_action = QAction("Fit Image", self)
        self.fit_image_action.triggered.connect(self._fit_image)

        self.activity_log_action = QAction("Activity Log...", self)
        self.activity_log_action.triggered.connect(self._open_activity_log_dialog)

        self.transcribe_action = QAction("Transcribe...", self)
        self.transcribe_action.triggered.connect(
            lambda: self._start_task(task_type=TASK_TRANSCRIBE, output_stage="original")
        )
        self.handwritten_htr_correction_action = QAction(
            "HTR + Correct...", self
        )
        self.handwritten_htr_correction_action.triggered.connect(
            self._start_handwritten_htr_correction_workflow
        )
        self.printed_ocr_correction_action = QAction(
            "Printed + Correct...", self
        )
        self.printed_ocr_correction_action.triggered.connect(
            self._start_printed_ocr_correction_workflow
        )
        self.correct_action = QAction("Correct...", self)
        self.correct_action.triggered.connect(
            lambda: self._start_task(task_type=TASK_CORRECT, output_stage="corrected")
        )
        self.translate_action = QAction("Translate...", self)
        self.translate_action.triggered.connect(
            lambda: self._start_task(task_type=TASK_TRANSLATE, output_stage="translated")
        )

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.rename_project_action)
        file_menu.addSeparator()
        import_menu = file_menu.addMenu("Import")
        import_menu.addAction(self.import_image_action)
        import_menu.addAction(self.import_images_action)
        import_menu.addAction(self.import_pdf_action)
        export_menu = file_menu.addMenu("Export")
        export_menu.addAction(self.export_text_action)
        export_menu.addAction(self.export_markdown_action)
        export_menu.addAction(self.export_csv_action)
        export_menu.addAction(self.export_json_action)
        export_menu.addAction(self.export_jsonl_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.save_text_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_page_action)
        edit_menu.addAction(self.move_page_up_action)
        edit_menu.addAction(self.move_page_down_action)
        edit_menu.addAction(self.rotate_pages_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.prev_page_action)
        view_menu.addAction(self.next_page_action)
        view_menu.addSeparator()
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_image_action)

        tasks_menu = self.menuBar().addMenu("&Tasks")
        tasks_menu.addAction(self.transcribe_action)
        workflow_menu = tasks_menu.addMenu("Workflows")
        workflow_menu.addAction(self.handwritten_htr_correction_action)
        workflow_menu.addAction(self.printed_ocr_correction_action)
        tasks_menu.addSeparator()
        tasks_menu.addAction(self.correct_action)
        tasks_menu.addAction(self.translate_action)

        settings_menu = self.menuBar().addMenu("&Settings")
        settings_menu.addAction(self.settings_action)
        settings_menu.addAction(self.task_prompt_settings_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.activity_log_action)

        navigation_toolbar = QToolBar("Navigation", self)
        navigation_toolbar.setMovable(False)
        navigation_toolbar.addAction(self.prev_page_action)
        navigation_toolbar.addAction(self.next_page_action)
        navigation_toolbar.addSeparator()
        navigation_toolbar.addAction(self.zoom_in_action)
        navigation_toolbar.addAction(self.zoom_out_action)
        navigation_toolbar.addAction(self.fit_image_action)
        self.addToolBar(navigation_toolbar)

        task_toolbar = QToolBar("Tasks", self)
        task_toolbar.setMovable(False)
        task_toolbar.addSeparator()
        task_toolbar.addAction(self.transcribe_action)
        task_toolbar.addAction(self.handwritten_htr_correction_action)
        task_toolbar.addAction(self.printed_ocr_correction_action)
        task_toolbar.addAction(self.correct_action)
        task_toolbar.addAction(self.translate_action)
        self.addToolBar(task_toolbar)

    def _build_ui(self) -> None:
        self.page_list = QListWidget(self)
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.page_list.currentItemChanged.connect(self._on_page_item_changed)
        self.page_list.addAction(self.delete_page_action)
        self.page_list.addAction(self.move_page_up_action)
        self.page_list.addAction(self.move_page_down_action)
        self.page_list.addAction(self.rotate_pages_action)

        self.image_viewer = ImageViewer(self)

        self.project_label = QLabel("No project open")
        self.page_label = QLabel("No page selected")
        self.image_label = QLabel("No image loaded")
        self.text_meta_label = QLabel("No text version loaded")
        for label in (self.project_label, self.page_label, self.image_label, self.text_meta_label):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.stage_combo = QComboBox(self)
        for stage in STAGES:
            self.stage_combo.addItem(stage.title(), userData=stage)
        self.stage_combo.currentIndexChanged.connect(self._on_stage_changed)

        self.save_button = QPushButton("Save Changes", self)
        self.save_button.clicked.connect(self._save_current_text_version)

        self.text_editor = QPlainTextEdit(self)
        self.text_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        monospace = QFont("Menlo")
        monospace.setStyleHint(QFont.StyleHint.Monospace)
        monospace.setPointSize(11)
        self.text_editor.setFont(monospace)
        self.text_editor.document().modificationChanged.connect(self._on_editor_modified_changed)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        page_header = QWidget(self)
        page_header_layout = QHBoxLayout(page_header)
        page_header_layout.setContentsMargins(0, 0, 0, 0)
        page_header_layout.addWidget(QLabel("Pages"))
        page_header_layout.addStretch(1)
        self.move_page_up_button = QPushButton("Up", self)
        self.move_page_up_button.clicked.connect(lambda: self._move_selected_pages("up"))
        page_header_layout.addWidget(self.move_page_up_button)
        self.move_page_down_button = QPushButton("Down", self)
        self.move_page_down_button.clicked.connect(lambda: self._move_selected_pages("down"))
        page_header_layout.addWidget(self.move_page_down_button)
        self.rotate_pages_button = QPushButton("Rotate 90°", self)
        self.rotate_pages_button.clicked.connect(self._rotate_selected_pages)
        page_header_layout.addWidget(self.rotate_pages_button)
        self.delete_page_button = QPushButton("Delete Page", self)
        self.delete_page_button.clicked.connect(self._delete_selected_page)
        page_header_layout.addWidget(self.delete_page_button)
        left_layout.addWidget(page_header)
        left_layout.addWidget(self.page_list)

        info_form = QWidget(self)
        info_layout = QFormLayout(info_form)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.addRow("Project", self.project_label)
        info_layout.addRow("Page", self.page_label)
        info_layout.addRow("Image", self.image_label)

        text_controls = QWidget(self)
        text_controls_layout = QHBoxLayout(text_controls)
        text_controls_layout.setContentsMargins(0, 0, 0, 0)
        text_controls_layout.addWidget(QLabel("Stage"))
        text_controls_layout.addWidget(self.stage_combo)
        text_controls_layout.addStretch(1)
        text_controls_layout.addWidget(self.save_button)

        text_panel = QWidget(self)
        text_panel_layout = QVBoxLayout(text_panel)
        text_panel_layout.setContentsMargins(0, 0, 0, 0)
        text_panel_layout.addWidget(text_controls)
        text_panel_layout.addWidget(self.text_editor, 1)
        text_panel_layout.addWidget(self.text_meta_label)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(info_form)
        right_layout.addWidget(self.image_viewer, 3)
        right_layout.addWidget(text_panel, 2)

        splitter = QSplitter(self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 1000])

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

        status_bar = QStatusBar(self)
        self.provider_status_label = QLabel("Task model: loading...")
        self.provider_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        status_bar.addPermanentWidget(self.provider_status_label)
        self._task_progress_label = QLabel("")
        self._task_progress_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._task_progress_label.setVisible(False)
        status_bar.addPermanentWidget(self._task_progress_label)
        self._cancel_task_button = QPushButton("Cancel Task", self)
        self._cancel_task_button.clicked.connect(self._cancel_background_task)
        self._cancel_task_button.setVisible(False)
        status_bar.addPermanentWidget(self._cancel_task_button)
        self._busy_indicator = QProgressBar(self)
        self._busy_indicator.setRange(0, 0)
        self._busy_indicator.setTextVisible(True)
        self._busy_indicator.setVisible(False)
        status_bar.addPermanentWidget(self._busy_indicator)
        self.setStatusBar(status_bar)

        self.page_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.image_viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._refresh_provider_status()

    def _refresh_window_state(self) -> None:
        has_project = self.project is not None
        has_page = self._current_page_id is not None
        can_interact = not self._task_is_running

        self.new_project_action.setEnabled(can_interact)
        self.open_project_action.setEnabled(can_interact)
        self.rename_project_action.setEnabled(has_project and can_interact)
        self.settings_action.setEnabled(can_interact)
        self.task_prompt_settings_action.setEnabled(can_interact)
        self.import_image_action.setEnabled(can_interact)
        self.import_images_action.setEnabled(can_interact)
        self.import_pdf_action.setEnabled(can_interact)
        self.export_text_action.setEnabled(has_project and can_interact)
        self.export_markdown_action.setEnabled(has_project and can_interact)
        self.export_csv_action.setEnabled(has_project and can_interact)
        self.export_json_action.setEnabled(has_project and can_interact)
        self.export_jsonl_action.setEnabled(has_project and can_interact)
        has_selected_pages = bool(self._selected_page_ids())
        self.delete_page_action.setEnabled(has_selected_pages and can_interact)
        self.move_page_up_action.setEnabled(has_selected_pages and can_interact)
        self.move_page_down_action.setEnabled(has_selected_pages and can_interact)
        self.rotate_pages_action.setEnabled(has_selected_pages and can_interact)
        self.prev_page_action.setEnabled(has_page and can_interact)
        self.next_page_action.setEnabled(has_page and can_interact)
        self.zoom_in_action.setEnabled(has_page)
        self.zoom_out_action.setEnabled(has_page)
        self.fit_image_action.setEnabled(has_page)
        self.transcribe_action.setEnabled(has_project and has_page and can_interact)
        self.handwritten_htr_correction_action.setEnabled(has_project and has_page and can_interact)
        self.printed_ocr_correction_action.setEnabled(has_project and has_page and can_interact)
        self.correct_action.setEnabled(has_project and has_page and can_interact)
        self.translate_action.setEnabled(has_project and has_page and can_interact)
        self.page_list.setEnabled(can_interact)
        self.delete_page_button.setEnabled(has_selected_pages and can_interact)
        self.move_page_up_button.setEnabled(has_selected_pages and can_interact)
        self.move_page_down_button.setEnabled(has_selected_pages and can_interact)
        self.rotate_pages_button.setEnabled(has_selected_pages and can_interact)
        self.stage_combo.setEnabled(has_page and can_interact)
        self.text_editor.setEnabled(has_page and can_interact)
        self.save_text_action.setEnabled(
            has_page and can_interact and self.text_editor.document().isModified()
        )
        self.save_button.setEnabled(
            has_page and can_interact and self.text_editor.document().isModified()
        )
        self._busy_indicator.setVisible(self._task_is_running)
        self._task_progress_label.setVisible(self._task_is_running)
        self._cancel_task_button.setVisible(self._task_is_running)
        self._cancel_task_button.setEnabled(self._task_is_running)

    def _create_project_dialog(self) -> None:
        if not self._maybe_resolve_unsaved_changes():
            return

        project = self._prompt_create_project()
        if project is None:
            return

        self._set_project(project)
        self.statusBar().showMessage(f"Created project at {project.root}", 5000)

    def _prompt_create_project(self, *, suggested_name: str | None = None) -> Project | None:
        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose Parent Directory for New Project",
            str(default_projects_dir()),
        )
        if not parent_dir:
            return None

        parent_path = Path(parent_dir)
        suggested = safe_project_name(suggested_name or "Archive Project")
        project_name, ok = QInputDialog.getText(
            self,
            "New Project",
            "Project name:",
            text=suggested,
        )
        if not ok or not project_name.strip():
            return None

        project_root = available_project_root(parent_path, project_name)
        return create_project(project_root, name=project_root.name)

    def _open_project_dialog(self) -> None:
        if not self._maybe_resolve_unsaved_changes():
            return

        project = self._prompt_open_project()
        if project is None:
            return

        self._set_project(project)
        self.statusBar().showMessage(f"Opened project {project.name}", 5000)

    def _prompt_open_project(self) -> Project | None:
        root = QFileDialog.getExistingDirectory(self, "Open Project", str(default_projects_dir()))
        if not root:
            return None
        return open_project(Path(root))

    def _rename_project_dialog(self) -> None:
        if self.project is None:
            return
        if not self._maybe_resolve_unsaved_changes():
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            "Project name:",
            text=self.project.name,
        )
        if not ok:
            return
        cleaned_name = safe_project_name(new_name)
        if not cleaned_name:
            return
        try:
            rename_project(self.project, cleaned_name)
        except Exception as exc:
            self._show_error("Could not rename project", exc)
            return
        self.project_label.setText(f"{self.project.name} ({self.project.root})")
        self.setWindowTitle(f"{__display_name__} — {self.project.name}")
        self.statusBar().showMessage(f"Renamed project to {self.project.name}", 5000)

    def _import_image_dialog(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Image",
            str(self._initial_import_dir()),
            IMAGE_FILE_FILTER,
        )
        if not filenames:
            return
        selected_paths = [Path(filename) for filename in filenames]
        self._remember_import_dir(selected_paths[0].parent)
        try:
            source_for_project = (
                selected_paths[0].parent if len(selected_paths) > 1 else selected_paths[0]
            )
            if not self._ensure_project_for_import(source_for_project, import_label="image"):
                return
            result = import_image_files(self.project, selected_paths, source_type=None)
        except Exception as exc:
            self._show_error("Could not import image", exc)
            return
        self._reload_pages(select_page_id=result.pages[0].page_id if result.pages else None)
        self.statusBar().showMessage(f"Imported {result.page_count} image page(s)", 5000)

    def _import_images_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Import Image Folder",
            str(self._initial_import_dir()),
        )
        if not folder:
            return
        self._remember_import_dir(Path(folder))
        try:
            if not self._ensure_project_for_import(Path(folder), import_label="image folder"):
                return
            result = import_image_folder(self.project, Path(folder), source_type=None)
        except Exception as exc:
            self._show_error("Could not import images", exc)
            return
        self._reload_pages(select_page_id=result.pages[0].page_id if result.pages else None)
        self.statusBar().showMessage(f"Imported {result.page_count} page images", 5000)

    def _import_pdf_dialog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import PDF",
            str(self._initial_import_dir()),
            "PDF files (*.pdf)",
        )
        if not filename:
            return
        self._remember_import_dir(Path(filename).parent)
        try:
            if not self._ensure_project_for_import(Path(filename), import_label="PDF"):
                return
            result = import_pdf(self.project, Path(filename), source_type=None)
        except Exception as exc:
            self._show_error("Could not import PDF", exc)
            return
        self._reload_pages(select_page_id=result.pages[0].page_id if result.pages else None)
        self.statusBar().showMessage(f"Imported {result.page_count} PDF pages", 5000)

    def _initial_import_dir(self) -> Path:
        try:
            settings = load_app_settings()
        except Exception:
            log.warning("Could not load settings for import directory", exc_info=True)
            return Path.home()
        if settings.last_import_dir:
            path = Path(settings.last_import_dir).expanduser()
            if path.is_dir():
                return path
        return Path.home()

    def _remember_import_dir(self, directory: Path) -> None:
        if not directory.is_dir():
            return
        try:
            settings = load_app_settings()
            save_app_settings(
                replace(settings, last_import_dir=str(directory)),
                store_credentials=False,
            )
        except Exception:
            log.warning("Could not save last import directory %s", directory, exc_info=True)

    def _ensure_project_for_import(self, source_path: Path, *, import_label: str) -> bool:
        if self.project is not None:
            return True
        if not self._maybe_resolve_unsaved_changes():
            return False

        suggested_name = self._suggest_project_name(source_path)
        try:
            project = create_project_with_available_name(default_projects_dir(), suggested_name)
        except Exception as exc:
            reply = QMessageBox.question(
                self,
                "Could Not Create Automatic Project",
                (
                    "ArchiveStudio could not create a project in the default Projects folder.\n\n"
                    f"{exc}\n\n"
                    "Would you like to choose a project location manually?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
            try:
                project = self._prompt_create_project(suggested_name=suggested_name)
            except Exception as manual_exc:
                self._show_error("Could not create project", manual_exc)
                return False
            if project is None:
                return False

        self._set_project(project)
        self.statusBar().showMessage(
            f"Created project '{project.name}' for imported {import_label}",
            5000,
        )
        return True

    def _suggest_project_name(self, source_path: Path) -> str:
        stem = source_path.stem if source_path.is_file() else source_path.name
        return safe_project_name(stem)

    def _set_project(self, project: Project) -> None:
        self._close_project()
        self.project = project
        self.project_label.setText(f"{project.name} ({project.root})")
        self._reload_pages()
        self.setWindowTitle(f"{__display_name__} — {project.name}")

    def _close_project(self) -> None:
        if self.project is not None:
            self.project.close()
        self.project = None
        self._page_records = []
        self._current_page_id = None
        self.page_list.clear()
        self.project_label.setText("No project open")
        self._load_page_details(None)
        self.setWindowTitle(__display_name__)
        self._refresh_window_state()

    def _reload_pages(
        self,
        *,
        select_page_id: str | None = None,
        selected_page_ids: list[str] | None = None,
    ) -> None:
        if self.project is None:
            self._page_records = []
            self.page_list.clear()
            self._current_page_id = None
            self._load_page_details(None)
            self._refresh_window_state()
            return

        with self.project.session() as session:
            pages = session.execute(select(Page).order_by(Page.sequence)).scalars().all()

        self._page_records = [
            PageRecord(
                id=page.id,
                sequence=page.sequence,
                image_path=page.image_path,
                source_type=page.source_type,
            )
            for page in pages
        ]

        self.page_list.blockSignals(True)
        self.page_list.clear()
        for record in self._page_records:
            suffix = f" [{record.source_type}]" if record.source_type else ""
            item = QListWidgetItem(f"Page {record.sequence:04d}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            self.page_list.addItem(item)
            if selected_page_ids and record.id in set(selected_page_ids):
                item.setSelected(True)
        self.page_list.blockSignals(False)

        if not self._page_records:
            self._current_page_id = None
            self._load_page_details(None)
            self._refresh_window_state()
            return

        target_id = select_page_id or self._current_page_id or self._page_records[0].id
        self._select_page_by_id(target_id)

    def _select_page_by_id(self, page_id: str) -> None:
        for index in range(self.page_list.count()):
            item = self.page_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                self.page_list.setCurrentItem(item)
                return

    def _select_previous_page(self) -> None:
        row = self.page_list.currentRow()
        if row > 0:
            self.page_list.setCurrentRow(row - 1)

    def _select_next_page(self) -> None:
        row = self.page_list.currentRow()
        if 0 <= row < self.page_list.count() - 1:
            self.page_list.setCurrentRow(row + 1)

    def _on_page_item_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        previous_id = previous.data(Qt.ItemDataRole.UserRole) if previous is not None else None
        current_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None

        if current_id == previous_id:
            return

        if not self._maybe_resolve_unsaved_changes():
            self.page_list.blockSignals(True)
            if previous is not None:
                self.page_list.setCurrentItem(previous)
            else:
                self.page_list.clearSelection()
            self.page_list.blockSignals(False)
            return

        self._current_page_id = current_id
        self._load_page_details(current_id)
        self._refresh_window_state()

    def _on_stage_changed(self) -> None:
        new_stage = self.stage_combo.currentData()
        if new_stage == self._current_stage:
            return

        if not self._maybe_resolve_unsaved_changes():
            self.stage_combo.blockSignals(True)
            index = self.stage_combo.findData(self._current_stage)
            if index >= 0:
                self.stage_combo.setCurrentIndex(index)
            self.stage_combo.blockSignals(False)
            return

        self._current_stage = str(new_stage)
        self._load_current_stage_text()
        self._refresh_window_state()

    def _load_page_details(self, page_id: str | None) -> None:
        if self.project is None or page_id is None:
            self.page_label.setText("No page selected")
            self.image_label.setText("No image loaded")
            self.text_meta_label.setText("No text version loaded")
            self._set_editor_text("")
            self.image_viewer.clear_image()
            self._refresh_window_state()
            return

        record = next((record for record in self._page_records if record.id == page_id), None)
        if record is None:
            self._load_page_details(None)
            return

        self.page_label.setText(f"{record.sequence:04d}")
        image_path = self.project.root / record.image_path
        if self.image_viewer.set_image_path(image_path):
            self.image_label.setText(str(image_path))
        else:
            self.image_label.setText(f"Could not load image: {image_path}")

        self._load_current_stage_text()

    def _load_current_stage_text(self) -> None:
        if self.project is None or self._current_page_id is None:
            self._set_editor_text("")
            self.text_meta_label.setText("No text version loaded")
            self._refresh_window_state()
            return

        with self.project.session() as session:
            version = get_current_text_version(
                session,
                page_id=self._current_page_id,
                stage=self._current_stage,
            )

        if version is None:
            self._set_editor_text("")
            self.text_meta_label.setText(
                f"No current {self._current_stage} text version. Edit and save to create one."
            )
        else:
            self._set_editor_text(version.content)
            meta_bits = [
                f"Stage: {version.stage}",
                f"By: {version.created_by}",
                f"At: {_format_display_timestamp(version.created_at)}",
            ]
            if version.source_version_id:
                meta_bits.append(f"Source version: {version.source_version_id}")
            self.text_meta_label.setText(" | ".join(meta_bits))
        self._refresh_window_state()

    def _set_editor_text(self, text: str) -> None:
        self._loading_editor = True
        self.text_editor.setPlainText(text)
        self.text_editor.document().setModified(False)
        self._loading_editor = False

    def _on_editor_modified_changed(self, modified: bool) -> None:
        if self._loading_editor:
            return
        self.save_text_action.setEnabled(
            modified and self._current_page_id is not None and not self._task_is_running
        )
        self.save_button.setEnabled(
            modified and self._current_page_id is not None and not self._task_is_running
        )

    def _save_current_text_version(self) -> bool:
        if self.project is None or self._current_page_id is None:
            return False

        content = self.text_editor.toPlainText()
        try:
            with self.project.session() as session:
                save_manual_text_version(
                    session,
                    page_id=self._current_page_id,
                    stage=self._current_stage,
                    content=content,
                )
        except Exception as exc:
            self._show_error("Could not save text", exc)
            return False

        self.text_editor.document().setModified(False)
        self._load_current_stage_text()
        self.statusBar().showMessage(
            f"Saved {self._current_stage} text for page {self.page_label.text()}",
            4000,
        )
        return True

    def _delete_selected_page(self) -> None:
        if self.project is None or self._current_page_id is None or self._task_is_running:
            return
        if not self._maybe_resolve_unsaved_changes():
            return

        selected_ids = self._selected_page_ids()
        selected_records = [record for record in self._page_records if record.id in set(selected_ids)]
        if not selected_records:
            return

        reply = QMessageBox.question(
            self,
            "Delete Pages",
            self._delete_pages_message(selected_records),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        select_page_id = self._neighbor_page_id_after_selection(selected_ids)
        try:
            deleted = delete_project_pages(self.project, page_ids=selected_ids)
        except PageNotFoundError as exc:
            self._show_error("Could not delete page", exc)
            return
        except Exception as exc:
            self._show_error("Could not delete page", exc)
            return

        self._reload_pages(select_page_id=select_page_id)
        if len(deleted) == 1:
            self.statusBar().showMessage(f"Deleted page {deleted[0].sequence}", 5000)
        else:
            self.statusBar().showMessage(f"Deleted {len(deleted)} pages", 5000)

    def _neighbor_page_id(self, page_id: str) -> str | None:
        for index, record in enumerate(self._page_records):
            if record.id != page_id:
                continue
            if index + 1 < len(self._page_records):
                return self._page_records[index + 1].id
            if index - 1 >= 0:
                return self._page_records[index - 1].id
            return None
        return None

    def _neighbor_page_id_after_selection(self, selected_ids: list[str]) -> str | None:
        selected_set = set(selected_ids)
        if not selected_set:
            return None
        first_selected_index = next(
            (index for index, record in enumerate(self._page_records) if record.id in selected_set),
            None,
        )
        if first_selected_index is None:
            return None
        for record in self._page_records[first_selected_index + 1 :]:
            if record.id not in selected_set:
                return record.id
        for record in reversed(self._page_records[:first_selected_index]):
            if record.id not in selected_set:
                return record.id
        return None

    def _selected_page_ids(self) -> list[str]:
        selected_ids = self._explicitly_selected_page_ids()
        if selected_ids:
            return selected_ids
        if self._current_page_id is not None:
            return [self._current_page_id]
        return []

    def _explicitly_selected_page_ids(self) -> list[str]:
        selected_items = self.page_list.selectedItems()
        if selected_items:
            return [
                str(item.data(Qt.ItemDataRole.UserRole))
                for item in selected_items
            ]
        return []

    def _delete_pages_message(self, records: list[PageRecord]) -> str:
        if len(records) == 1:
            return (
                f"Delete page {records[0].sequence:04d}?\n\n"
                "This removes the page and all of its text versions from the project."
            )
        return (
            f"Delete {len(records)} selected pages?\n\n"
            "This removes the selected pages and all of their text versions from the project."
        )

    def _move_selected_pages(self, direction: str) -> None:
        if self.project is None or self._task_is_running:
            return
        selected_ids = self._selected_page_ids()
        if not selected_ids:
            return

        try:
            changed = move_project_pages(self.project, page_ids=selected_ids, direction=direction)
        except PageNotFoundError as exc:
            self._show_error("Could not reorder pages", exc)
            return
        except Exception as exc:
            self._show_error("Could not reorder pages", exc)
            return

        if not changed:
            self.statusBar().showMessage(
                "The selected pages are already at the edge and cannot be moved further.",
                4000,
            )
            return

        current_page_id = (
            self._current_page_id
            if self._current_page_id in set(selected_ids)
            else selected_ids[0]
        )
        self._reload_pages(select_page_id=current_page_id, selected_page_ids=selected_ids)
        self.statusBar().showMessage(
            f"Moved selected pages {direction}.",
            4000,
        )

    def _rotate_selected_pages(self) -> None:
        if self.project is None or self._task_is_running:
            return

        selected_ids = self._selected_page_ids()
        if not selected_ids:
            return

        try:
            rotated = rotate_project_pages(self.project, page_ids=selected_ids)
        except PageNotFoundError as exc:
            self._show_error("Could not rotate pages", exc)
            return
        except Exception as exc:
            self._show_error("Could not rotate pages", exc)
            return

        current_page_id = self._current_page_id
        self._reload_pages(
            select_page_id=current_page_id,
            selected_page_ids=selected_ids,
        )
        rotated_label = self._format_page_sequence_label([page.sequence for page in rotated])
        self.statusBar().showMessage(f"Rotated pages {rotated_label} by 90°.", 5000)

    def _open_settings_dialog(self) -> None:
        try:
            settings = load_app_settings()
        except Exception as exc:
            self._show_error("Could not load settings", exc)
            return

        dialog = SettingsDialog(settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            saved_path = save_app_settings(dialog.settings_value())
        except Exception as exc:
            self._show_error("Could not save settings", exc)
            return

        self._refresh_provider_status()
        self.statusBar().showMessage(f"Saved settings to {saved_path}", 5000)

    def _open_task_prompt_settings_dialog(self) -> None:
        dialog = TaskPromptSettingsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.statusBar().showMessage("Saved task prompt settings", 5000)

    def _open_activity_log_dialog(self) -> None:
        dialog = ActivityLogDialog(self)
        dialog.exec()

    def _refresh_provider_status(self) -> None:
        try:
            settings = load_app_settings()
            selection = create_provider_from_settings(settings)
        except Exception:
            self.provider_status_label.setText("Task model: unavailable")
            return

        model_id = getattr(selection.provider, "model_id", "unknown")
        if selection.used_fallback and selection.message:
            self.provider_status_label.setText(
                "Task model: not configured"
            )
            self.provider_status_label.setToolTip(selection.message)
            return

        self.provider_status_label.setText(
            f"Task model: {selection.provider.provider_name}:{model_id}"
        )
        self.provider_status_label.setToolTip(
            f"LLM used for tasks: {settings.default_provider}"
        )

    def _export_records_dialog(self, export_format: str) -> None:
        if self.project is None:
            return
        if not self._maybe_resolve_unsaved_changes():
            return

        selected_stage = self._choose_export_stage()
        if selected_stage is None:
            return

        export_profile = EXPORT_PROFILE_GENERIC
        if export_format in {EXPORT_FORMAT_JSON, EXPORT_FORMAT_JSONL}:
            export_profile = self._choose_export_profile()
            if export_profile is None:
                return

        selection = self._choose_export_scope()
        if selection is None:
            return
        scope_label, page_ids = selection

        suffix = {
            EXPORT_FORMAT_TEXT: "txt",
            EXPORT_FORMAT_MARKDOWN: "md",
            EXPORT_FORMAT_CSV: "csv",
            EXPORT_FORMAT_JSON: "json",
            EXPORT_FORMAT_JSONL: "jsonl",
        }[export_format]
        default_path = self.project.exports_dir / f"{self.project.name}_{selected_stage}.{suffix}"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {export_format.upper()}",
            str(default_path),
            self._export_file_filter(export_format),
        )
        if not output_path:
            return

        try:
            result = export_project_records(
                self.project,
                export_format=export_format,
                export_profile=export_profile,
                selected_stage=selected_stage,
                scope_label=scope_label,
                page_ids=page_ids,
                output_path=Path(output_path),
            )
        except Exception as exc:
            self._show_error(f"Could not export {export_format}", exc)
            return

        self.statusBar().showMessage(
            (
                f"Exported {result.record_count} pages as {export_format.upper()} "
                f"to {result.output_path.name}"
            ),
            7000,
        )

    def _choose_export_stage(self) -> str | None:
        stage_labels = [stage.title() for stage in STAGES]
        current_index = STAGES.index(self._current_stage) if self._current_stage in STAGES else 0
        choice, ok = QInputDialog.getItem(
            self,
            "Choose Export Stage",
            "Export which text stage?",
            stage_labels,
            current=current_index,
            editable=False,
        )
        if not ok:
            return None
        return choice.lower()

    def _choose_export_scope(self) -> tuple[str, list[str] | None] | None:
        if self.project is None or not self._page_records:
            return None
        if len(self._page_records) == 1:
            record = self._page_records[0]
            return f"page {record.sequence}", [record.id]

        message_box = QMessageBox(self)
        message_box.setWindowTitle("Export Scope")
        message_box.setText("Choose which pages to export.")
        current_button = message_box.addButton("Current Page", QMessageBox.ButtonRole.AcceptRole)
        range_button = message_box.addButton("Page Range...", QMessageBox.ButtonRole.ActionRole)
        all_button = message_box.addButton("All Pages", QMessageBox.ButtonRole.ActionRole)
        cancel_button = message_box.addButton(QMessageBox.StandardButton.Cancel)
        message_box.setDefaultButton(current_button)
        message_box.exec()

        clicked = message_box.clickedButton()
        if clicked == current_button:
            if self._current_page_id is None:
                return None
            record = next(
                (record for record in self._page_records if record.id == self._current_page_id),
                None,
            )
            if record is None:
                return None
            return f"page {record.sequence}", [record.id]
        if clicked == range_button:
            sequences = self._choose_page_range_sequences()
            if sequences is None:
                return None
            selected_records = [record for record in self._page_records if record.sequence in set(sequences)]
            return (
                f"pages {self._format_page_sequence_label(sequences)}",
                [record.id for record in selected_records],
            )
        if clicked == all_button:
            return "all pages", None
        if clicked == cancel_button:
            return None
        return None

    def _choose_export_profile(self) -> str | None:
        profile_names = [
            EXPORT_PROFILE_GENERIC,
            EXPORT_PROFILE_PATIENT_JOURNAL,
        ]
        labels = [EXPORT_PROFILE_LABELS[name] for name in profile_names]
        choice, ok = QInputDialog.getItem(
            self,
            "Choose JSON Profile",
            "Structured export profile:",
            labels,
            editable=False,
        )
        if not ok:
            return None
        for name in profile_names:
            if EXPORT_PROFILE_LABELS[name] == choice:
                return name
        return EXPORT_PROFILE_GENERIC

    def _export_file_filter(self, export_format: str) -> str:
        if export_format == EXPORT_FORMAT_TEXT:
            return "Text files (*.txt)"
        if export_format == EXPORT_FORMAT_MARKDOWN:
            return "Markdown files (*.md)"
        if export_format == EXPORT_FORMAT_CSV:
            return "CSV files (*.csv)"
        if export_format == EXPORT_FORMAT_JSON:
            return "JSON files (*.json)"
        if export_format == EXPORT_FORMAT_JSONL:
            return "JSONL files (*.jsonl)"
        return "All files (*)"

    def _start_task(self, *, task_type: str, output_stage: str) -> None:
        if self.project is None or self._current_page_id is None:
            return
        if not self._maybe_resolve_unsaved_changes():
            return
        if self._task_is_running:
            return

        launch = self._build_task_launch(task_type=task_type, output_stage=output_stage)
        if launch is None:
            return

        preset = self._load_launch_preset(
            launch.preset_name,
            title="Could Not Load Preset",
        )
        if preset is None:
            return
        if launch.custom_instructions:
            preset = replace(preset, custom_instructions=launch.custom_instructions)
        if task_type == TASK_TRANSCRIBE and launch.pages_per_call is not None:
            preset = replace(
                preset,
                batch_size=launch.pages_per_call,
                model_config=replace(
                    preset.model_config,
                    max_batch_pages=max(
                        preset.model_config.max_batch_pages,
                        launch.pages_per_call,
                    ),
                ),
            )

        provider = self._resolve_task_provider(preset.model_config)
        if provider is None:
            return

        if task_type == TASK_TRANSCRIBE:
            runner = lambda token: run_transcription(
                self.project,
                provider,
                preset,
                page_ids=launch.page_ids,
                progress_callback=self._background_tasks.report_progress,
                cancellation_token=token,
            )
        elif task_type == TASK_CORRECT:
            runner = lambda token: run_correction(
                self.project,
                provider,
                preset,
                page_ids=launch.page_ids,
                progress_callback=self._background_tasks.report_progress,
                cancellation_token=token,
            )
        elif task_type == TASK_TRANSLATE:
            runner = lambda token: run_translation(
                self.project,
                provider,
                preset,
                page_ids=launch.page_ids,
                progress_callback=self._background_tasks.report_progress,
                cancellation_token=token,
            )
        else:
            self._show_error("Could Not Start Task", ValueError(f"Unsupported task type: {task_type}"))
            return

        self._active_task_launch = launch
        if not self._launch_background_task(runner):
            self._active_task_launch = None
            return
        prefix = "auto-selected preset" if launch.auto_selected_preset else "preset"
        self.statusBar().showMessage(
            (
                f"Running {task_type} with {prefix} '{launch.preset_name}' "
                f"on {launch.scope_label} using {provider.provider_name}:{provider.model_id}"
                f"{self._pages_per_call_status_suffix(launch)}..."
            ),
            0,
        )

    def _start_handwritten_htr_correction_workflow(self) -> None:
        self._start_two_step_transcribe_correction_workflow(
            workflow_name=HANDWRITTEN_HTR_CORRECTION_WORKFLOW,
            preset_name="Handwritten Transcription + Correction",
            runner_factory=lambda provider, page_ids, transcription_preset, correction_preset, progress_callback, cancellation_token: run_handwritten_htr_and_correction(
                self.project,
                provider,
                page_ids=page_ids,
                transcription_preset=transcription_preset,
                correction_preset=correction_preset,
                progress_callback=progress_callback,
                cancellation_token=cancellation_token,
            ),
            status_label="handwritten transcription + correction",
            transcription_preset_name="Handwritten Transcription",
            correction_preset_name="Handwritten Correction",
        )

    def _start_printed_ocr_correction_workflow(self) -> None:
        self._start_two_step_transcribe_correction_workflow(
            workflow_name=PRINTED_OCR_CORRECTION_WORKFLOW,
            preset_name="Printed Transcription + Correction",
            runner_factory=lambda provider, page_ids, transcription_preset, correction_preset, progress_callback, cancellation_token: run_printed_ocr_and_correction(
                self.project,
                provider,
                page_ids=page_ids,
                transcription_preset=transcription_preset,
                correction_preset=correction_preset,
                progress_callback=progress_callback,
                cancellation_token=cancellation_token,
            ),
            status_label="printed transcription + correction",
            transcription_preset_name="Printed Transcription",
            correction_preset_name="Printed Correction",
        )

    def _start_two_step_transcribe_correction_workflow(
        self,
        *,
        workflow_name: str,
        preset_name: str,
        runner_factory: Callable[[object, list[str] | None, object, object, object, object], object],
        status_label: str,
        transcription_preset_name: str,
        correction_preset_name: str,
    ) -> None:
        if self.project is None or self._current_page_id is None:
            return
        if not self._maybe_resolve_unsaved_changes():
            return
        if self._task_is_running:
            return

        scope = self._choose_task_target_scope()
        if scope is None:
            return

        transcription_preset = self._load_launch_preset(
            transcription_preset_name,
            title="Could Not Load Workflow Preset",
        )
        if transcription_preset is None:
            return
        correction_preset = self._load_launch_preset(
            correction_preset_name,
            title="Could Not Load Workflow Preset",
        )
        if correction_preset is None:
            return
        selected_count = self._page_count_for_scope(scope.page_ids)
        pages_per_call: int | None = None
        if selected_count > 1:
            pages_per_call = self._choose_pages_per_api_call()
            if pages_per_call is None:
                return
            transcription_preset = replace(
                transcription_preset,
                batch_size=pages_per_call,
                model_config=replace(
                    transcription_preset.model_config,
                    max_batch_pages=max(
                        transcription_preset.model_config.max_batch_pages,
                        pages_per_call,
                    ),
                ),
            )

        provider = self._resolve_task_provider(transcription_preset.model_config)
        if provider is None:
            return

        self._active_task_launch = TaskLaunch(
            task_type=workflow_name,
            scope_label=scope.scope_label,
            page_ids=scope.page_ids,
            preset_name=preset_name,
            output_stage="corrected",
            auto_selected_preset=True,
            pages_per_call=pages_per_call,
        )
        runner = lambda token: runner_factory(
            provider,
            scope.page_ids,
            transcription_preset,
            correction_preset,
            self._background_tasks.report_progress,
            token,
        )
        if not self._launch_background_task(runner):
            self._active_task_launch = None
            return
        self.statusBar().showMessage(
            (
                f"Running {status_label} "
                f"on {scope.scope_label} using {provider.provider_name}:{provider.model_id}"
                f"{self._pages_per_call_status_suffix(self._active_task_launch)}..."
            ),
            0,
        )

    def _build_task_launch(self, *, task_type: str, output_stage: str) -> TaskLaunch | None:
        scope = self._choose_task_target_scope()
        if scope is None:
            return None

        preset_name, auto_selected = self._resolve_preset_name(
            task_type=task_type,
            page_ids=scope.page_ids,
        )
        if preset_name is None:
            return None

        custom_instructions = ""
        if preset_name.startswith("Custom "):
            custom_instructions = self._choose_custom_task_instructions(task_type=task_type)
            if custom_instructions is None:
                return None

        pages_per_call: int | None = None
        if task_type == TASK_TRANSCRIBE:
            selected_count = self._page_count_for_scope(scope.page_ids)
            if selected_count > 1:
                pages_per_call = self._choose_pages_per_api_call()
                if pages_per_call is None:
                    return None

        return TaskLaunch(
            task_type=task_type,
            scope_label=scope.scope_label,
            page_ids=scope.page_ids,
            preset_name=preset_name,
            output_stage=output_stage,
            auto_selected_preset=auto_selected,
            custom_instructions=custom_instructions,
            pages_per_call=pages_per_call,
        )

    def _load_launch_preset(self, preset_name: str, *, title: str):
        try:
            return get_preset(preset_name)
        except Exception as exc:
            self._show_error(title, exc)
            return None

    def _resolve_task_provider(self, model_config=None):
        settings = load_app_settings()
        provider_selection = create_provider_from_settings(settings, model_config=model_config)
        if provider_selection.used_fallback and provider_selection.message:
            QMessageBox.critical(
                self,
                "Model Settings Required",
                (
                    f"The configured provider '{provider_selection.requested_provider}' "
                    "could not be used.\n\n"
                    f"{provider_selection.message}\n\n"
                    "No task was run. This prevents placeholder demo output from "
                    "being saved as real transcription text."
                ),
            )
            return None
        if provider_selection.effective_provider == "demo":
            QMessageBox.critical(
                self,
                "Model Settings Required",
                (
                    "The local demo provider is not available for normal task runs.\n\n"
                    "Open Settings > Model, enable a real provider, enter its API key, "
                    "and choose it as the LLM used for tasks."
                ),
            )
            return None
        return provider_selection.provider

    def _choose_task_target_scope(self) -> TaskScopeSelection | None:
        scope = self._choose_task_scope()
        if scope is None:
            return None

        if scope == "selected":
            page_ids = self._explicitly_selected_page_ids()
            selected_records = [record for record in self._page_records if record.id in set(page_ids)]
            return TaskScopeSelection(
                page_ids=page_ids,
                scope_label=self._selected_pages_scope_label(selected_records),
            )

        if scope == "current":
            page_ids = [self._current_page_id] if self._current_page_id is not None else None
            return TaskScopeSelection(page_ids=page_ids, scope_label="current page")

        if scope == "range":
            sequences = self._choose_page_range_sequences()
            if sequences is None:
                return None
            selected_records = [record for record in self._page_records if record.sequence in set(sequences)]
            page_ids = [record.id for record in selected_records]
            return TaskScopeSelection(
                page_ids=page_ids,
                scope_label=f"pages {self._format_page_sequence_label(sequences)}",
            )

        return TaskScopeSelection(page_ids=None, scope_label="all pages")

    def _page_count_for_scope(self, page_ids: list[str] | None) -> int:
        if page_ids is None:
            return len(self._page_records)
        return len(page_ids)

    def _choose_task_scope(self) -> str | None:
        if self.project is None or self._current_page_id is None:
            return None
        if len(self._page_records) <= 1:
            return "current"

        selected_count = len(self._explicitly_selected_page_ids())
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Run Task")
        message_box.setText("Choose how broadly to run this task.")
        current_button = message_box.addButton("Current Page", QMessageBox.ButtonRole.AcceptRole)
        selected_button = None
        if selected_count > 1:
            selected_button = message_box.addButton(
                f"Selected Pages ({selected_count})",
                QMessageBox.ButtonRole.ActionRole,
            )
        range_button = message_box.addButton("Page Range...", QMessageBox.ButtonRole.ActionRole)
        all_button = message_box.addButton("All Pages", QMessageBox.ButtonRole.ActionRole)
        cancel_button = message_box.addButton(QMessageBox.StandardButton.Cancel)
        message_box.setDefaultButton(selected_button or current_button)
        message_box.exec()

        clicked = message_box.clickedButton()
        if clicked == current_button:
            return "current"
        if selected_button is not None and clicked == selected_button:
            return "selected"
        if clicked == range_button:
            return "range"
        if clicked == all_button:
            return "all"
        if clicked == cancel_button:
            return None
        return None

    def _choose_page_range_sequences(self) -> list[int] | None:
        available_sequences = [record.sequence for record in self._page_records]
        if not available_sequences:
            return None

        current_sequence = next(
            (record.sequence for record in self._page_records if record.id == self._current_page_id),
            available_sequences[0],
        )
        prompt = (
            "Enter pages or ranges to run.\n"
            "Examples: 1-5 or 2,4,7-9\n"
            f"Available pages: {self._format_page_sequence_label(available_sequences)}"
        )
        text, ok = QInputDialog.getText(
            self,
            "Page Range",
            prompt,
            text=str(current_sequence),
        )
        if not ok:
            return None

        try:
            return parse_page_range_spec(text, allowed_sequences=set(available_sequences))
        except PageRangeParseError as exc:
            QMessageBox.warning(self, "Invalid Page Range", str(exc))
            return None

    def _format_page_sequence_label(self, sequences: list[int]) -> str:
        if not sequences:
            return ""
        if len(sequences) == 1:
            return str(sequences[0])
        return ", ".join(str(sequence) for sequence in sequences)

    def _selected_pages_scope_label(self, records: list[PageRecord]) -> str:
        if not records:
            return "selected pages"
        if len(records) <= 8:
            sequences = [record.sequence for record in records]
            return f"selected pages {self._format_page_sequence_label(sequences)}"
        return f"{len(records)} selected pages"

    def _choose_pages_per_api_call(self) -> int | None:
        options = ["1", "2", "4", "8", "Custom..."]
        choice, ok = QInputDialog.getItem(
            self,
            "Pages Per API Call",
            (
                "Choose how many consecutive pages to send in each transcription API call.\n"
                "1 is safest. Higher values can improve continuity, but increase latency "
                "and the risk of page mixing."
            ),
            options,
            current=0,
            editable=False,
        )
        if not ok:
            return None
        if choice == "Custom...":
            value, custom_ok = QInputDialog.getInt(
                self,
                "Custom Pages Per API Call",
                "Pages per transcription API call:",
                value=4,
                minValue=1,
                maxValue=64,
                step=1,
            )
            if not custom_ok:
                return None
            return value
        return int(choice)

    def _pages_per_call_status_suffix(self, launch: TaskLaunch) -> str:
        if launch.task_type != TASK_TRANSCRIBE or launch.pages_per_call is None:
            return ""
        return f" (pages per call: {launch.pages_per_call})"

    def _resolve_preset_name(self, *, task_type: str, page_ids: list[str] | None) -> tuple[str | None, bool]:
        source_types = self._selected_source_types(page_ids)
        recommended = recommended_preset_for_source_types(task_type, source_types)
        if recommended is not None:
            return recommended, True

        preset_name = self._choose_preset_name(task_type, preferred_source_types=source_types)
        return preset_name, False

    def _choose_preset_name(
        self,
        task_type: str,
        *,
        preferred_source_types: set[str | None] | None = None,
    ) -> str | None:
        preset_names = [preset.name for preset in list_presets() if preset.task_type == task_type]
        if not preset_names:
            return None

        if preferred_source_types:
            preset_names = prioritize_preset_names(
                preset_names,
                task_type=task_type,
                preferred_source_types=preferred_source_types,
            )

        choice, ok = QInputDialog.getItem(
            self,
            "Choose Preset",
            "Preset:",
            preset_names,
            editable=False,
        )
        if not ok:
            return None
        return choice

    def _choose_custom_task_instructions(self, *, task_type: str) -> str | None:
        task_label = {
            TASK_TRANSCRIBE: "OCR / HTR",
            TASK_CORRECT: "Correction",
            TASK_TRANSLATE: "Translation",
        }.get(task_type, "Task")
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Custom Instructions",
            (
                f"Enter custom instructions for {task_label}.\n"
                "These instructions will be inserted into the prompt for this run."
            ),
        )
        if not ok:
            return None
        cleaned = text.strip()
        if not cleaned:
            QMessageBox.warning(
                self,
                "Missing Custom Instructions",
                "Please enter some instructions for the custom preset.",
            )
            return None
        return cleaned

    def _selected_source_types(self, page_ids: list[str] | None) -> set[str | None]:
        return selected_source_types(self._page_records, page_ids)

    def _launch_background_task(self, runner: Callable[[CancellationToken], object]) -> bool:
        token = CancellationToken()
        try:
            self._background_tasks.start(lambda: runner(token), cancellation_token=token)
        except RuntimeError as exc:
            self._show_error("Could Not Start Task", exc)
            return False
        return True

    def _cancel_background_task(self) -> None:
        if not self._task_is_running:
            return
        self._cancel_task_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling task after the current API call finishes...", 0)
        self._background_tasks.cancel()

    def _on_background_task_finished(self, summary: object) -> None:
        launch = self._active_task_launch
        if isinstance(summary, WorkflowRunSummary):
            self._set_current_stage(summary.final_stage)
            self._reload_pages(select_page_id=self._current_page_id)

            workflow_label = {
                HANDWRITTEN_HTR_CORRECTION_WORKFLOW: (
                    "Handwritten transcription + correction"
                ),
                PRINTED_OCR_CORRECTION_WORKFLOW: "Printed transcription + correction",
            }.get(summary.workflow_name, "Workflow")
            message = (
                f"{workflow_label} cancelled: "
                if summary.status == TASK_STATUS_CANCELLED
                else f"{workflow_label} finished: "
            ) + (
                f"{summary.pages_completed}/{summary.pages_requested} pages completed"
            )
            if summary.pages_failed:
                message += f", {summary.pages_failed} failed"
            self.statusBar().showMessage(message, 7000)

            if summary.errors and summary.status != TASK_STATUS_CANCELLED:
                for error_message in summary.errors:
                    log.warning("Workflow issue: %s", error_message)
                QMessageBox.warning(
                    self,
                    "Workflow Completed With Issues",
                    _format_issue_message(summary.errors),
                )
            return

        if isinstance(summary, TaskRunSummary):
            if launch is not None:
                self._set_current_stage(launch.output_stage)
            self._reload_pages(select_page_id=self._current_page_id)

            message = (
                f"{summary.task_type.title()} cancelled: "
                if summary.status == TASK_STATUS_CANCELLED
                else f"{summary.task_type.title()} finished: "
            ) + (
                f"{summary.pages_completed}/{summary.pages_requested} pages completed"
            )
            if summary.pages_failed:
                message += f", {summary.pages_failed} failed"
            self.statusBar().showMessage(message, 7000)

            if summary.errors and summary.status != TASK_STATUS_CANCELLED:
                for error_message in summary.errors:
                    log.warning("Task issue: %s", error_message)
                QMessageBox.warning(
                    self,
                    "Task Completed With Issues",
                    _format_issue_message(summary.errors),
                )

    def _on_background_task_failed(self, error: Exception) -> None:
        self._show_error("Background Task Failed", error)

    def _on_background_task_cancelled(self, error: Exception) -> None:
        report = classify_exception(error)
        log.info("Background task cancelled: %s", report.summary)
        self.statusBar().showMessage(report.summary, 7000)

    def _on_background_task_progress(self, progress: object) -> None:
        if not isinstance(progress, TaskProgress):
            return

        total = max(0, progress.pages_total)
        processed = min(total, progress.pages_processed) if total else progress.pages_processed
        if total:
            self._busy_indicator.setRange(0, total)
            self._busy_indicator.setValue(processed)
        else:
            self._busy_indicator.setRange(0, 0)

        label = self._format_task_progress_label(progress)
        self._task_progress_label.setText(label)
        self._task_progress_label.setVisible(True)

        message = label
        current = self._format_current_pages(progress.current_pages)
        if current:
            message += f" — {current}"
        if progress.message:
            message += f" ({progress.message})"
        self.statusBar().showMessage(message, 0)

    def _on_background_task_running_changed(self, is_running: bool) -> None:
        self._task_is_running = is_running
        if not is_running:
            self._active_task_launch = None
            self._busy_indicator.reset()
            self._busy_indicator.setRange(0, 0)
            self._task_progress_label.clear()
        else:
            self._busy_indicator.setRange(0, 0)
            self._busy_indicator.setValue(0)
            self._task_progress_label.setText("Starting task...")
        self._refresh_window_state()

    def _format_task_progress_label(self, progress: TaskProgress) -> str:
        task_label = {
            TASK_TRANSCRIBE: "Transcribe",
            TASK_CORRECT: "Correct",
            TASK_TRANSLATE: "Translate",
        }.get(progress.task_type, progress.task_type.title())

        if progress.pages_total:
            label = f"{task_label}: {progress.pages_completed} / {progress.pages_total}"
        else:
            label = f"{task_label}: {progress.pages_completed}"
        if progress.pages_failed:
            label += f", {progress.pages_failed} failed"
        return label

    def _format_current_pages(self, page_sequences: tuple[int, ...]) -> str:
        if not page_sequences:
            return ""
        if len(page_sequences) == 1:
            return f"page {page_sequences[0]}"
        return "pages " + ", ".join(str(sequence) for sequence in page_sequences)

    def _set_current_stage(self, stage: str) -> None:
        self._current_stage = stage
        index = self.stage_combo.findData(stage)
        if index >= 0:
            self.stage_combo.blockSignals(True)
            self.stage_combo.setCurrentIndex(index)
            self.stage_combo.blockSignals(False)
        self._load_current_stage_text()

    def _maybe_resolve_unsaved_changes(self) -> bool:
        if not self.text_editor.document().isModified():
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved text changes. Save them before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._save_current_text_version()
        if reply == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _zoom_in(self) -> None:
        self.image_viewer.zoom_in()

    def _zoom_out(self) -> None:
        self.image_viewer.zoom_out()

    def _fit_image(self) -> None:
        self.image_viewer.fit_to_view()

    def _show_error(self, title: str, error: Exception) -> None:
        report = classify_exception(error)
        log.error(
            "%s [%s]: %s\n%s",
            title,
            report.category,
            report.summary,
            report.technical_detail,
        )
        QMessageBox.critical(
            self,
            title,
            (
                f"{report.summary}\n\n"
                f"Category: {report.category}\n\n"
                f"{report.suggestion}\n\n"
                "For technical details, open Help > Activity Log."
            ),
        )
IMAGE_FILE_FILTER = (
    "Image files (*.bmp *.jpeg *.jpg *.png *.tif *.tiff *.webp)"
)


def _format_issue_message(errors: list[str]) -> str:
    shown = "\n".join(errors[:8])
    if len(errors) > 8:
        shown += f"\n... and {len(errors) - 8} more issue(s)."
    return f"{shown}\n\nFor technical details, open Help > Activity Log."


def _format_display_timestamp(value: datetime) -> str:
    """Format user-facing timestamps without changing stored database values."""
    return value.strftime("%Y-%m-%d %H:%M")
