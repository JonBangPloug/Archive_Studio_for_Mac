"""Compact review panel for transcription verification flags."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class VerificationFlagView:
    id: str
    primary_start: int
    primary_end: int
    primary_text: str
    alternative_text: str
    flag_type: str


class VerificationPanel(QWidget):
    """Show open verifier disagreements and expose human review actions."""

    flag_selected = Signal(str)
    keep_requested = Signal(str)
    use_alternative_requested = Signal(str)
    manual_edit_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._flags: dict[str, VerificationFlagView] = {}
        self._text_offsets_current = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        self.title_label = QLabel("Verification flags")
        layout.addWidget(self.title_label)

        self.flag_list = QListWidget(self)
        self.flag_list.setMaximumHeight(120)
        self.flag_list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.flag_list)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.keep_button = QPushButton("Keep Current", self)
        self.keep_button.clicked.connect(self._request_keep)
        self.use_alternative_button = QPushButton("Use Alternative", self)
        self.use_alternative_button.clicked.connect(self._request_use_alternative)
        self.manual_edit_button = QPushButton("Resolved After Edit", self)
        self.manual_edit_button.clicked.connect(self._request_manual_edit)
        button_layout.addWidget(self.keep_button)
        button_layout.addWidget(self.use_alternative_button)
        button_layout.addWidget(self.manual_edit_button)
        button_layout.addStretch(1)
        layout.addWidget(button_row)

        self.note_label = QLabel(
            "Verifier alternatives are suggestions only. Save Changes is still required after editing."
        )
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        self._refresh_action_state()

    def set_flags(self, flags: list[VerificationFlagView]) -> None:
        self._flags = {flag.id: flag for flag in flags}
        self.flag_list.clear()
        for flag in flags:
            item = QListWidgetItem(self._format_flag_label(flag))
            item.setData(Qt.ItemDataRole.UserRole, flag.id)
            self.flag_list.addItem(item)
        if flags:
            self.flag_list.setCurrentRow(0)
        self.setVisible(bool(flags))
        self._refresh_action_state()

    def set_text_offsets_current(self, current: bool) -> None:
        self._text_offsets_current = current
        self._refresh_action_state()

    def selected_flag(self) -> VerificationFlagView | None:
        flag_id = self._selected_flag_id()
        if flag_id is None:
            return None
        return self._flags.get(flag_id)

    def _selected_flag_id(self) -> str | None:
        item = self.flag_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _format_flag_label(self, flag: VerificationFlagView) -> str:
        primary = flag.primary_text or "[missing in current text]"
        alternative = flag.alternative_text or "[delete]"
        return f"{primary}  ->  {alternative}"

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self._refresh_action_state()
        if current is None:
            return
        flag_id = current.data(Qt.ItemDataRole.UserRole)
        if flag_id:
            self.flag_selected.emit(str(flag_id))

    def _refresh_action_state(self) -> None:
        has_selection = self._selected_flag_id() is not None
        self.keep_button.setEnabled(has_selection)
        self.use_alternative_button.setEnabled(has_selection and self._text_offsets_current)
        self.manual_edit_button.setEnabled(has_selection)

    def _request_keep(self) -> None:
        flag_id = self._selected_flag_id()
        if flag_id is not None:
            self.keep_requested.emit(flag_id)

    def _request_use_alternative(self) -> None:
        flag_id = self._selected_flag_id()
        if flag_id is not None:
            self.use_alternative_requested.emit(flag_id)

    def _request_manual_edit(self) -> None:
        flag_id = self._selected_flag_id()
        if flag_id is not None:
            self.manual_edit_requested.emit(flag_id)
