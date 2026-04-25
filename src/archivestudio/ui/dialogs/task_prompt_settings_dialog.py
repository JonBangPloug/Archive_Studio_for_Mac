"""Dialog for editing and managing task prompt presets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from archivestudio.core.tasks import (
    StoredPreset,
    get_builtin_preset,
    get_preset,
    list_presets,
    load_user_presets,
    save_user_presets,
)
from archivestudio.core.tasks.preset_overrides import (
    PresetOverride,
    load_preset_overrides,
    save_preset_overrides,
)
from archivestudio.core.tasks.prompt_validation import (
    PromptTemplateValidationError,
    validate_prompt_template,
)


TASK_TYPE_LABELS = {
    "transcribe": "Transcribe",
    "correct": "Correct",
    "translate": "Translate",
}


class TaskPromptSettingsDialog(QDialog):
    """Edit prompt instructions and manage a small user preset library."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt Settings")
        self.resize(980, 820)

        self._overrides = load_preset_overrides()
        self._user_presets = load_user_presets()
        self._current_original_name: str | None = None
        self._current_is_builtin = True
        self._loading_form = False
        self._loaded_form_state: tuple[object, ...] | None = None

        self._build_ui()
        self._connect_dirty_tracking()
        self._load_preset_names()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._maybe_resolve_unsaved_changes():
            event.accept()
            return
        event.ignore()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choose a preset, edit the prompt text, and save. "
            "Built-in presets are safe defaults; your changes are saved as overrides."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll_area, 1)

        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        scroll_area.setWidget(content)

        preset_box = QGroupBox("Preset")
        preset_layout = QVBoxLayout(preset_box)
        preset_row = QWidget(preset_box)
        top_layout = QHBoxLayout(preset_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel("Current preset"))
        self.preset_combo = QComboBox(self)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        top_layout.addWidget(self.preset_combo, 1)
        self.preset_type_label = QLabel("")
        top_layout.addWidget(self.preset_type_label)
        preset_layout.addWidget(preset_row)
        self.preset_help_label = QLabel("")
        self.preset_help_label.setWordWrap(True)
        preset_layout.addWidget(self.preset_help_label)
        content_layout.addWidget(preset_box)

        actions_box = QGroupBox("Manage Presets")
        action_layout = QGridLayout(actions_box)
        self.new_preset_button = QPushButton("New Preset...", self)
        self.new_preset_button.clicked.connect(self._new_blank_preset)
        self.delete_preset_button = QPushButton("Delete Preset", self)
        self.delete_preset_button.clicked.connect(self._delete_selected_preset)
        self.reset_preset_button = QPushButton("Reset Preset to Original", self)
        self.reset_preset_button.clicked.connect(self._reset_selected_preset)
        action_buttons = [
            self.new_preset_button,
            self.delete_preset_button,
            self.reset_preset_button,
        ]
        for index, button in enumerate(action_buttons):
            row = index // 2
            column = index % 2
            action_layout.addWidget(button, row, column)
        content_layout.addWidget(actions_box)

        editor_box = QGroupBox("Prompt Editor")
        editor_layout = QVBoxLayout(editor_box)
        editor_intro = QLabel(
            "General instructions describe the overall job. "
            "Detailed instructions are the concrete prompt template sent to the model. "
            "For translation presets, change the output language by editing the detailed "
            "instructions, for example: 'Translate from Latin to English.'"
        )
        editor_intro.setWordWrap(True)
        editor_layout.addWidget(editor_intro)

        self.general_instructions_edit = QPlainTextEdit(self)
        self.general_instructions_edit.setMinimumHeight(170)
        self.general_instructions_edit.setPlaceholderText(
            "Describe the overall goal, accuracy rules, and what should be preserved."
        )
        self.detailed_instructions_edit = QPlainTextEdit(self)
        self.detailed_instructions_edit.setMinimumHeight(250)
        self.detailed_instructions_edit.setPlaceholderText(
            "Write the actual task prompt here. You can use placeholders listed below."
        )
        self.response_prefix_edit = QPlainTextEdit(self)
        self.response_prefix_edit.setMaximumHeight(70)
        self.response_prefix_edit.setPlaceholderText(
            "Optional. Example: Corrected Transcript:"
        )

        editor_layout.addWidget(QLabel("General instructions"))
        editor_layout.addWidget(self.general_instructions_edit)
        editor_layout.addWidget(QLabel("Detailed instructions"))
        editor_layout.addWidget(self.detailed_instructions_edit)
        prefix_label = QLabel("Remove this leading label from saved text")
        prefix_label.setToolTip(
            "If the model starts its reply with a label like 'Corrected Transcript:', "
            "enter that label here and ArchiveStudio will remove it before saving the text."
        )
        editor_layout.addWidget(prefix_label)
        editor_layout.addWidget(self.response_prefix_edit)
        prefix_help = QLabel(
            "Example: if the AI replies with 'Corrected Transcript: ...', enter "
            "'Corrected Transcript:' here so only the actual text is saved."
        )
        prefix_help.setWordWrap(True)
        editor_layout.addWidget(prefix_help)
        content_layout.addWidget(editor_box)

        placeholders_box = QGroupBox("Available Placeholders")
        placeholders_layout = QVBoxLayout(placeholders_box)
        help_text = QLabel(self._placeholder_help_html())
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.TextFormat.RichText)
        placeholders_layout.addWidget(help_text)
        content_layout.addWidget(placeholders_box)

        details_box = QGroupBox("Preset Details")
        details_layout = QVBoxLayout(details_box)
        self.details_help_label = QLabel("")
        self.details_help_label.setWordWrap(True)
        details_layout.addWidget(self.details_help_label)

        metadata_form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.task_type_combo = QComboBox(self)
        for task_type, label in TASK_TYPE_LABELS.items():
            self.task_type_combo.addItem(label, userData=task_type)
        self.source_genre_edit = QLineEdit(self)
        self.batch_size_spin = QSpinBox(self)
        self.batch_size_spin.setRange(1, 20)
        self.preserve_line_breaks_checkbox = QCheckBox("Preserve line breaks", self)
        self.preserve_marginalia_checkbox = QCheckBox("Preserve marginalia", self)
        self.normalize_whitespace_checkbox = QCheckBox("Normalize whitespace", self)
        metadata_form.addRow("Preset name", self.name_edit)
        metadata_form.addRow("Task type", self.task_type_combo)
        metadata_form.addRow("Source genre", self.source_genre_edit)
        metadata_form.addRow("Batch size", self.batch_size_spin)
        details_layout.addLayout(metadata_form)

        options_row = QWidget(details_box)
        options_layout = QHBoxLayout(options_row)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.addWidget(self.preserve_line_breaks_checkbox)
        options_layout.addWidget(self.preserve_marginalia_checkbox)
        options_layout.addWidget(self.normalize_whitespace_checkbox)
        options_layout.addStretch(1)
        details_layout.addWidget(options_row)
        content_layout.addWidget(details_box)
        content_layout.addStretch(1)

        bottom_row = QWidget(self)
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addStretch(1)
        self.save_button = QPushButton("Save Current", self)
        self.save_button.clicked.connect(self._save_current)
        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.close)
        bottom_layout.addWidget(self.save_button)
        bottom_layout.addWidget(self.close_button)
        layout.addWidget(bottom_row)

    def _placeholder_help_html(self) -> str:
        return (
            "<b>Most useful</b><br>"
            "<code>{text_to_process}</code> current source text for Correct and Translate<br>"
            "<code>{source_text}</code> current source text<br><br>"
            "<b>Context</b><br>"
            "<code>{page_sequence}</code>, <code>{source_genre}</code>, "
            "<code>{structure_rules}</code>, <code>{custom_instructions}</code><br>"
            "<code>{source_stage}</code> is available in Translate<br><br>"
            "<b>Translation language</b><br>"
            "Change the language pair by editing the translation prompt text itself."
        )

    def _connect_dirty_tracking(self) -> None:
        self.name_edit.textChanged.connect(self._on_form_changed)
        self.task_type_combo.currentIndexChanged.connect(self._on_form_changed)
        self.source_genre_edit.textChanged.connect(self._on_form_changed)
        self.batch_size_spin.valueChanged.connect(self._on_form_changed)
        self.preserve_line_breaks_checkbox.toggled.connect(self._on_form_changed)
        self.preserve_marginalia_checkbox.toggled.connect(self._on_form_changed)
        self.normalize_whitespace_checkbox.toggled.connect(self._on_form_changed)
        self.general_instructions_edit.textChanged.connect(self._on_form_changed)
        self.detailed_instructions_edit.textChanged.connect(self._on_form_changed)
        self.response_prefix_edit.textChanged.connect(self._on_form_changed)

    def _load_preset_names(self, *, select_name: str | None = None) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for preset in list_presets():
            if preset.task_type not in TASK_TYPE_LABELS:
                continue
            origin = "user" if preset.name in self._user_presets else "built-in"
            self.preset_combo.addItem(preset.name, userData=(preset.name, origin))
        self.preset_combo.blockSignals(False)
        if self.preset_combo.count():
            target = select_name or self.current_preset_name() or self.preset_combo.itemData(0)[0]
            index = self._find_preset_index(target)
            self.preset_combo.setCurrentIndex(max(0, index))
            self._load_selected_preset()
        self._refresh_export_buttons()

    def _find_preset_index(self, preset_name: str) -> int:
        for index in range(self.preset_combo.count()):
            data = self.preset_combo.itemData(index)
            if data and data[0] == preset_name:
                return index
        return -1

    def _on_preset_changed(self) -> None:
        if self._loading_form:
            return
        selected_name = self.current_preset_name()
        if selected_name is None:
            return
        if self._current_original_name and selected_name != self._current_original_name:
            if not self._maybe_resolve_unsaved_changes():
                self._restore_preset_selection(self._current_original_name)
                return
        self._load_selected_preset()

    def _load_selected_preset(self) -> None:
        preset_name = self.current_preset_name()
        if not preset_name:
            return

        self._loading_form = True
        self._current_original_name = preset_name
        self._current_is_builtin = preset_name not in self._user_presets
        preset = get_preset(preset_name)

        self.name_edit.setText(preset.name)
        self._set_task_type(preset.task_type)
        self.source_genre_edit.setText(preset.source_genre)
        self.batch_size_spin.setValue(max(1, preset.batch_size))
        self.preserve_line_breaks_checkbox.setChecked(preset.preserve_line_breaks)
        self.preserve_marginalia_checkbox.setChecked(preset.preserve_marginalia)
        self.normalize_whitespace_checkbox.setChecked(preset.normalize_whitespace)
        self.general_instructions_edit.setPlainText(preset.prompt_template.system_prompt)
        self.detailed_instructions_edit.setPlainText(preset.prompt_template.user_prompt_template)
        self.response_prefix_edit.setPlainText(preset.response_prefix)

        self._apply_editability_state()
        self._loaded_form_state = self._capture_form_state()
        self._loading_form = False
        self._set_form_dirty(False)

    def _apply_editability_state(self) -> None:
        is_user = not self._current_is_builtin
        self.preset_type_label.setText("User preset" if is_user else "Built-in preset")
        if is_user:
            self.preset_help_label.setText(
                "This is your own preset. You can edit both the prompt text and the preset details below."
            )
            self.details_help_label.setText(
                "Preset details affect how this preset behaves at runtime."
            )
            self.save_button.setText("Save Changes")
        else:
            self.preset_help_label.setText(
                "This is a built-in preset. You can edit the prompt text and runtime details below; "
                "ArchiveStudio will save your changes as an override."
            )
            self.details_help_label.setText(
                "Built-in preset names and task types stay fixed, but you can adjust source genre, "
                "batch size, and the structure options."
            )
            self.save_button.setText("Save Changes")
        self.name_edit.setEnabled(is_user)
        self.task_type_combo.setEnabled(is_user)
        self.source_genre_edit.setEnabled(True)
        self.batch_size_spin.setEnabled(True)
        self.preserve_line_breaks_checkbox.setEnabled(True)
        self.preserve_marginalia_checkbox.setEnabled(True)
        self.normalize_whitespace_checkbox.setEnabled(True)
        self._refresh_export_buttons()

    def _refresh_export_buttons(self) -> None:
        preset_name = self.current_preset_name()
        self.delete_preset_button.setEnabled(
            bool(preset_name) and not self._current_is_builtin
        )
        self.reset_preset_button.setEnabled(
            bool(preset_name)
            and self._current_is_builtin
            and preset_name in self._overrides
        )

    def _save_current(self) -> None:
        if not self._save_current_preset():
            return
        self.accept()

    def _save_current_preset(self) -> bool:
        stored = self._build_stored_preset_from_form()
        if stored is None:
            return False

        if self._current_is_builtin:
            builtin = get_builtin_preset(self._current_original_name or stored.name)
            if (
                stored.system_prompt == builtin.prompt_template.system_prompt
                and stored.user_prompt_template == builtin.prompt_template.user_prompt_template
                and stored.response_prefix == builtin.response_prefix
                and stored.source_genre == builtin.source_genre
                and stored.batch_size == builtin.batch_size
                and stored.preserve_line_breaks == builtin.preserve_line_breaks
                and stored.preserve_marginalia == builtin.preserve_marginalia
                and stored.normalize_whitespace == builtin.normalize_whitespace
            ):
                self._overrides.pop(builtin.name, None)
            else:
                self._overrides[builtin.name] = PresetOverride(
                    system_prompt=stored.system_prompt,
                    user_prompt_template=stored.user_prompt_template,
                    response_prefix=stored.response_prefix,
                    source_genre=stored.source_genre,
                    batch_size=stored.batch_size,
                    preserve_line_breaks=stored.preserve_line_breaks,
                    preserve_marginalia=stored.preserve_marginalia,
                    normalize_whitespace=stored.normalize_whitespace,
                )
            save_preset_overrides(self._overrides)
            self._loaded_form_state = self._capture_form_state()
            self._set_form_dirty(False)
            return True

        old_name = self._current_original_name
        if old_name and old_name != stored.name:
            self._user_presets.pop(old_name, None)
        self._user_presets[stored.name] = stored
        save_user_presets(self._user_presets)
        self._current_original_name = stored.name
        self._load_preset_names(select_name=stored.name)
        return True

    def _build_stored_preset_from_form(self) -> StoredPreset | None:
        name = self.name_edit.text().strip()
        system_prompt = self.general_instructions_edit.toPlainText().strip()
        user_prompt_template = self.detailed_instructions_edit.toPlainText().strip()
        response_prefix = self.response_prefix_edit.toPlainText().strip()
        source_genre = self.source_genre_edit.text().strip()
        task_type = str(self.task_type_combo.currentData())

        if not name:
            QMessageBox.warning(self, "Missing Preset Name", "Preset name is required.")
            return None
        if not system_prompt or not user_prompt_template:
            QMessageBox.warning(
                self,
                "Missing Prompt Text",
                "General instructions and detailed instructions must both be filled in.",
            )
            return None
        if self._current_is_builtin and name != (self._current_original_name or name):
            QMessageBox.warning(
                self,
                "Built-in Preset Name",
                "Built-in preset names cannot be changed. Use New Preset if you want a separate custom preset.",
            )
            return None
        if (name in self._user_presets or self._find_preset_index(name) >= 0) and (
            self._current_original_name != name
        ):
            QMessageBox.warning(
                self,
                "Preset Name Already Exists",
                "Choose a different name for this preset.",
            )
            return None
        try:
            validate_prompt_template(user_prompt_template, task_type=task_type)
        except PromptTemplateValidationError as exc:
            QMessageBox.warning(
                self,
                "Invalid Prompt Placeholder",
                str(exc),
            )
            return None

        return StoredPreset(
            name=name,
            task_type=task_type,
            source_genre=source_genre or "custom source",
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            response_prefix=response_prefix,
            batch_size=self.batch_size_spin.value(),
            preserve_line_breaks=self.preserve_line_breaks_checkbox.isChecked(),
            preserve_marginalia=self.preserve_marginalia_checkbox.isChecked(),
            normalize_whitespace=self.normalize_whitespace_checkbox.isChecked(),
        )

    def _new_blank_preset(self) -> None:
        if not self._maybe_resolve_unsaved_changes():
            return
        task_type = self._choose_task_type(default="correct")
        if task_type is None:
            return
        name = self._prompt_for_new_name("New Prompt Preset", "My Custom Preset")
        if name is None:
            return
        system_prompt, user_prompt_template = self._default_new_preset_prompts(task_type)
        preset = StoredPreset(
            name=name,
            task_type=task_type,
            source_genre="custom source",
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            batch_size=1,
            preserve_line_breaks=True,
            preserve_marginalia=False,
            normalize_whitespace=False,
        )
        self._user_presets[preset.name] = preset
        save_user_presets(self._user_presets)
        self._load_preset_names(select_name=preset.name)

    def _default_new_preset_prompts(self, task_type: str) -> tuple[str, str]:
        system_prompt = "Describe the task clearly and the historical constraints to preserve."
        if task_type == "transcribe":
            return (
                system_prompt,
                (
                    "Transcribe page {page_sequence}.\n"
                    "Source genre: {source_genre}.\n\n"
                    "Structure rules:\n{structure_rules}\n\n"
                    "Return only the transcription."
                ),
            )
        if task_type == "correct":
            return (
                system_prompt,
                (
                    "Correct page {page_sequence}.\n"
                    "Source genre: {source_genre}.\n\n"
                    "Structure rules:\n{structure_rules}\n\n"
                    "Source text:\n{source_text}\n\n"
                    "Return only the corrected text."
                ),
            )
        return (
            system_prompt,
            (
                "Translate page {page_sequence}.\n"
                "Source genre: {source_genre}.\n"
                "Input stage: {source_stage}.\n"
                "Translate from [source language] to [target language].\n"
                "Preserve names, dates, uncertain readings, and meaningful structure.\n\n"
                "Source text:\n{source_text}\n\n"
                "Return only the translation."
            ),
        )

    def _delete_selected_preset(self) -> None:
        if not self._maybe_resolve_unsaved_changes():
            return
        if self._current_is_builtin:
            QMessageBox.information(
                self,
                "Built-in Preset",
                "Built-in presets cannot be deleted. Use 'Reset Preset to Original' to remove your override, or create a new preset if you want a separate custom version.",
            )
            return

        preset_name = self.current_preset_name()
        if not preset_name:
            return
        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete user preset '{preset_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._user_presets.pop(preset_name, None)
        save_user_presets(self._user_presets)
        self._load_preset_names()

    def _reset_selected_preset(self) -> None:
        if not self._maybe_resolve_unsaved_changes():
            return
        preset_name = self.current_preset_name()
        if not preset_name or not self._current_is_builtin:
            QMessageBox.information(
                self,
                "Reset Not Available",
                "Reset Preset to Original is only available for built-in presets.",
            )
            return
        if preset_name not in self._overrides:
            QMessageBox.information(
                self,
                "Already Original",
                f"'{preset_name}' is already using the original built-in settings.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Reset Preset to Original",
            f"Remove your saved override for built-in preset '{preset_name}' and restore the original built-in settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._overrides.pop(preset_name, None)
        save_preset_overrides(self._overrides)
        self._load_selected_preset()

    def _choose_task_type(self, *, default: str) -> str | None:
        labels = [TASK_TYPE_LABELS[key] for key in TASK_TYPE_LABELS]
        current_index = list(TASK_TYPE_LABELS).index(default)
        choice, ok = QInputDialog.getItem(
            self,
            "Choose Task Type",
            "Task type:",
            labels,
            current=current_index,
            editable=False,
        )
        if not ok:
            return None
        for task_type, label in TASK_TYPE_LABELS.items():
            if label == choice:
                return task_type
        return None

    def _prompt_for_new_name(self, title: str, suggested: str) -> str | None:
        while True:
            name, ok = QInputDialog.getText(self, title, "Preset name:", text=suggested)
            if not ok:
                return None
            cleaned = name.strip()
            if not cleaned:
                QMessageBox.warning(self, "Missing Name", "Preset name is required.")
                continue
            if cleaned in self._user_presets or self._find_preset_index(cleaned) >= 0:
                QMessageBox.warning(
                    self,
                    "Preset Exists",
                    "That preset name already exists. Choose a different one.",
                )
                suggested = f"{cleaned} Copy"
                continue
            return cleaned

    def _set_task_type(self, task_type: str) -> None:
        index = self.task_type_combo.findData(task_type)
        if index >= 0:
            self.task_type_combo.setCurrentIndex(index)

    def current_preset_name(self) -> str | None:
        data = self.preset_combo.currentData()
        if data is None:
            return None
        return str(data[0])

    def _restore_preset_selection(self, preset_name: str) -> None:
        index = self._find_preset_index(preset_name)
        if index < 0:
            return
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def _capture_form_state(self) -> tuple[object, ...]:
        return (
            self.name_edit.text(),
            self.task_type_combo.currentData(),
            self.source_genre_edit.text(),
            self.batch_size_spin.value(),
            self.preserve_line_breaks_checkbox.isChecked(),
            self.preserve_marginalia_checkbox.isChecked(),
            self.normalize_whitespace_checkbox.isChecked(),
            self.general_instructions_edit.toPlainText(),
            self.detailed_instructions_edit.toPlainText(),
            self.response_prefix_edit.toPlainText(),
        )

    def _has_unsaved_changes(self) -> bool:
        if self._loaded_form_state is None:
            return False
        return self._capture_form_state() != self._loaded_form_state

    def _set_form_dirty(self, dirty: bool) -> None:
        self.setWindowModified(dirty)

    def _on_form_changed(self, *_args: object) -> None:
        if self._loading_form:
            return
        self._set_form_dirty(self._has_unsaved_changes())

    def _maybe_resolve_unsaved_changes(self) -> bool:
        if not self._has_unsaved_changes():
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Prompt Changes",
            "You have unsaved preset changes. Save them before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._save_current_preset()
        if reply == QMessageBox.StandardButton.Discard:
            return True
        return False
