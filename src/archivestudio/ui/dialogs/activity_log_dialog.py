"""In-app viewer for the persistent ArchiveStudio activity log."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from archivestudio.core.config.paths import user_log_file


class ActivityLogDialog(QDialog):
    """Show recent log output so users can inspect failures without Terminal."""

    def __init__(self, parent=None, *, log_file: Path | None = None) -> None:
        super().__init__(parent)
        self._log_file = log_file or user_log_file()

        self.setWindowTitle("Activity Log")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Recent ArchiveStudio activity and errors. API keys and common secret "
            "patterns are redacted before they are written to this log."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        path_label = QLabel(f"Log file: {self._log_file}")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)

        self.log_text = QPlainTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_text, 1)

        utility_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.refresh)
        utility_row.addWidget(self.refresh_button)

        self.copy_path_button = QPushButton("Copy Log Path", self)
        self.copy_path_button.clicked.connect(self._copy_log_path)
        utility_row.addWidget(self.copy_path_button)
        utility_row.addStretch(1)
        layout.addLayout(utility_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh()

    def refresh(self) -> None:
        """Load a tail of the current log file."""
        if not self._log_file.exists():
            self.log_text.setPlainText("No log file has been written yet.")
            return

        try:
            text = _read_log_tail(self._log_file)
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Read Log", str(exc))
            return

        self.log_text.setPlainText(text or "The log file is empty.")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def _copy_log_path(self) -> None:
        QApplication.clipboard().setText(str(self._log_file))


def _read_log_tail(path: Path, *, max_chars: int = 200_000) -> str:
    data = path.read_text(encoding="utf-8", errors="replace")
    if len(data) <= max_chars:
        return data
    return "... showing the most recent log entries ...\n\n" + data[-max_chars:]
