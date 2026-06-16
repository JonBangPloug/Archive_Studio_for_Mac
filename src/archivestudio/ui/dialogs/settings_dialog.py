"""In-app settings dialog for provider configuration."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from archivestudio.core.config import AppSettings, ProviderSettings


class SettingsDialog(QDialog):
    """Edit user provider settings inside the desktop app."""

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Model Settings")
        self.resize(680, 420)

        self._build_ui()
        self._load_settings(settings)

    def settings_value(self) -> AppSettings:
        default_provider = self.default_provider_combo.currentData()
        return AppSettings(
            openai=self._provider_settings_from_row(self.openai_row),
            anthropic=self._provider_settings_from_row(self.anthropic_row),
            google=self._provider_settings_from_row(self.google_row),
            default_provider=str(default_provider),
            auto_open_last_work=self.auto_open_last_work_checkbox.isChecked(),
            path=self._settings.path,
            last_import_dir=self._settings.last_import_dir,
            workspace_layout=self._settings.workspace_layout,
            pages_pane_visible=self._settings.pages_pane_visible,
            write_task_checkpoints=self.write_task_checkpoints_checkbox.isChecked(),
            main_splitter_sizes=self._settings.main_splitter_sizes,
            stacked_workspace_sizes=self._settings.stacked_workspace_sizes,
            side_by_side_workspace_sizes=self._settings.side_by_side_workspace_sizes,
        )

    def accept(self) -> None:
        settings = self.settings_value()
        selected = {
            "openai": settings.openai,
            "anthropic": settings.anthropic,
            "google": settings.google,
        }[settings.default_provider]
        if not selected.enabled:
            QMessageBox.warning(
                self,
                "Task LLM Disabled",
                "The selected LLM is disabled. Enable it before saving, or choose another enabled provider.",
            )
            return
        self._settings = settings
        super().accept()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choose which LLM ArchiveStudio should use for Transcribe, Correct, "
            "and Translate. Each provider has Fast and Strong model slots; "
            "prompt presets can choose one of those tiers. "
            "API keys are saved in macOS Keychain when possible. Changes take effect on the next task run."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        path_label = QLabel(
            f"Settings file: {self._settings.path}\n"
            "This file stores provider choices and model names, not API keys. "
            "Model names change over time; use the names shown in your provider documentation or dashboard."
        )
        path_label.setTextInteractionFlags(path_label.textInteractionFlags())
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        app_box = QGroupBox("Task Model")
        app_form = QFormLayout(app_box)
        self.default_provider_combo = QComboBox(self)
        self.default_provider_combo.addItem("OpenAI", userData="openai")
        self.default_provider_combo.addItem("Anthropic", userData="anthropic")
        self.default_provider_combo.addItem("Google Gemini", userData="google")
        self.auto_open_last_work_checkbox = QCheckBox("Auto-open last work on launch", self)
        self.write_task_checkpoints_checkbox = QCheckBox(
            "Write per-page checkpoint files during text tasks", self
        )
        self.write_task_checkpoints_checkbox.setToolTip(
            "Stores one .txt file per completed page in exports/checkpoints for recovery."
        )
        app_form.addRow("LLM used for tasks", self.default_provider_combo)
        app_form.addRow("", self.auto_open_last_work_checkbox)
        app_form.addRow("", self.write_task_checkpoints_checkbox)
        layout.addWidget(app_box)

        providers_box = QGroupBox("Providers")
        providers_layout = QGridLayout(providers_box)
        self.openai_row = _ProviderRow("OpenAI")
        self.anthropic_row = _ProviderRow("Anthropic")
        self.google_row = _ProviderRow("Google Gemini")
        for row_index, row in enumerate(
            [self.openai_row, self.anthropic_row, self.google_row]
        ):
            providers_layout.addWidget(row.widget, row_index, 0)
        layout.addWidget(providers_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_settings(self, settings: AppSettings) -> None:
        index = self.default_provider_combo.findData(settings.default_provider)
        if index < 0:
            index = self._first_enabled_provider_index(settings)
        self.default_provider_combo.setCurrentIndex(max(0, index))
        self.auto_open_last_work_checkbox.setChecked(settings.auto_open_last_work)
        self.write_task_checkpoints_checkbox.setChecked(settings.write_task_checkpoints)
        self._load_provider_row(self.openai_row, settings.openai)
        self._load_provider_row(self.anthropic_row, settings.anthropic)
        self._load_provider_row(self.google_row, settings.google)

    def _first_enabled_provider_index(self, settings: AppSettings) -> int:
        enabled_by_provider = {
            "openai": settings.openai.enabled,
            "anthropic": settings.anthropic.enabled,
            "google": settings.google.enabled,
        }
        for index in range(self.default_provider_combo.count()):
            provider_name = str(self.default_provider_combo.itemData(index))
            if enabled_by_provider.get(provider_name, False):
                return index
        return 0

    def _load_provider_row(self, row: "_ProviderRow", settings: ProviderSettings) -> None:
        row.enabled_checkbox.setChecked(settings.enabled)
        row.api_key_edit.setText(settings.api_key)
        row.fast_model_edit.setText(settings.fast_model or settings.model)
        row.strong_model_edit.setText(settings.strong_model or settings.model)

    def _provider_settings_from_row(self, row: "_ProviderRow") -> ProviderSettings:
        strong_model = row.strong_model_edit.text().strip()
        return ProviderSettings(
            enabled=row.enabled_checkbox.isChecked(),
            api_key=row.api_key_edit.text().strip(),
            model=strong_model,
            fast_model=row.fast_model_edit.text().strip(),
            strong_model=strong_model,
        )


class _ProviderRow:
    def __init__(self, label: str) -> None:
        self.widget = QGroupBox(label)
        layout = QFormLayout(self.widget)

        self.enabled_checkbox = QCheckBox("Enabled")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.fast_model_edit = QLineEdit()
        self.strong_model_edit = QLineEdit()

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key_edit)
        self.show_key_checkbox = QCheckBox("Show")
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.show_key_checkbox)

        layout.addRow("", self.enabled_checkbox)
        layout.addRow("API key (Keychain)", key_row)
        layout.addRow("Fast model", self.fast_model_edit)
        layout.addRow("Strong model", self.strong_model_edit)

    def _toggle_key_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.api_key_edit.setEchoMode(mode)
