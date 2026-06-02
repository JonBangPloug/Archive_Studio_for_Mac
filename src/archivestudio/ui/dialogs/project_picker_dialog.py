"""Project picker dialog that hides project folder implementation details."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from archivestudio.core.project import ProjectSummary


class ProjectPickerDialog(QDialog):
    """Let users choose an Archive Studio project by name."""

    def __init__(
        self,
        projects: list[ProjectSummary],
        *,
        default_location: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._projects = projects
        self._choose_other = False

        self.setWindowTitle("Open Project")
        self.resize(760, 420)
        self._build_ui(default_location)
        self._load_projects(projects)

    @property
    def choose_other_requested(self) -> bool:
        return self._choose_other

    def selected_project_root(self) -> Path | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        value = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return Path(str(value)) if value else None

    def _build_ui(self, default_location: Path) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choose an Archive Studio project. Projects are shown by name; "
            "their project.db, images, exports, and task history stay hidden."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        location = QLabel(f"Default projects location: {default_location}")
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setWordWrap(True)
        layout.addWidget(location)

        self.empty_label = QLabel(
            "No Archive Studio projects were found in the default projects location."
        )
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Project", "Last Modified", "Location"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        self.table.itemSelectionChanged.connect(self._refresh_open_button)
        layout.addWidget(self.table, 1)

        self.buttons = QDialogButtonBox(self)
        self.open_button = self.buttons.addButton(
            "Open",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.choose_other_button = self.buttons.addButton(
            "Choose Other Project Folder...",
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.open_button.clicked.connect(self._accept_selected)
        self.choose_other_button.clicked.connect(self._choose_other_project)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_projects(self, projects: list[ProjectSummary]) -> None:
        self.table.setRowCount(len(projects))
        for row, project in enumerate(projects):
            name_item = QTableWidgetItem(project.name)
            name_item.setData(Qt.ItemDataRole.UserRole, str(project.root))
            modified_item = QTableWidgetItem(_format_modified(project))
            path_item = QTableWidgetItem(str(project.root))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, modified_item)
            self.table.setItem(row, 2, path_item)

        self.empty_label.setVisible(not projects)
        self.table.setVisible(bool(projects))
        self.table.resizeColumnsToContents()
        if projects:
            self.table.selectRow(0)
        self._refresh_open_button()

    def _refresh_open_button(self) -> None:
        self.open_button.setEnabled(self.selected_project_root() is not None)

    def _accept_selected(self) -> None:
        if self.selected_project_root() is not None:
            self.accept()

    def _choose_other_project(self) -> None:
        self._choose_other = True
        self.accept()


def _format_modified(project: ProjectSummary) -> str:
    if project.modified_at is None:
        return ""
    return project.modified_at.strftime("%Y-%m-%d %H:%M")
