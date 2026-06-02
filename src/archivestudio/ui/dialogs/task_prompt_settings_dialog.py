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

from archivestudio.core.config import load_app_settings
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
    "verify": "Verify",
}

PROVIDER_LABELS = {
    "configurable": "App default",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
}

MODEL_TIER_LABELS = {
    "fast": "Fast",
    "strong": "Strong",
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
        self._current_model_id = "unset"
        self._current_source_genre = "custom source"
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
            "Edit what the model should do and what it should know about this source."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll_area, 1)

        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
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
        filter_row = QWidget(preset_box)
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(QLabel("Show"))
        self.task_filter_combo = QComboBox(self)
        self.task_filter_combo.addItem("All task presets", userData="")
        for task_type, label in TASK_TYPE_LABELS.items():
            self.task_filter_combo.addItem(label, userData=task_type)
        self.task_filter_combo.currentIndexChanged.connect(self._on_task_filter_changed)
        filter_layout.addWidget(self.task_filter_combo)
        filter_layout.addStretch(1)
        preset_layout.addWidget(filter_row)
        self.preset_help_label = QLabel("")
        self.preset_help_label.setWordWrap(True)
        preset_layout.addWidget(self.preset_help_label)

        action_row = QWidget(preset_box)
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.new_preset_button = QPushButton("New Preset...", self)
        self.new_preset_button.clicked.connect(self._new_blank_preset)
        self.delete_preset_button = QPushButton("Delete Preset", self)
        self.delete_preset_button.clicked.connect(self._delete_selected_preset)
        self.reset_preset_button = QPushButton("Reset Preset to Original", self)
        self.reset_preset_button.clicked.connect(self._reset_selected_preset)
        action_layout.addWidget(self.new_preset_button)
        action_layout.addWidget(self.delete_preset_button)
        action_layout.addWidget(self.reset_preset_button)
        action_layout.addStretch(1)
        preset_layout.addWidget(action_row)
        content_layout.addWidget(preset_box)

        task_box = QGroupBox("Task instruction")
        task_layout = QVBoxLayout(task_box)
        task_intro = QLabel("What the model should do for this task.")
        task_intro.setWordWrap(True)
        task_layout.addWidget(task_intro)
        self.general_instructions_edit = QPlainTextEdit(self)
        self.general_instructions_edit.setMinimumHeight(150)
        self.general_instructions_edit.setPlaceholderText(
            "Example: Transcribe faithfully, preserve spelling and meaningful structure, and do not modernize."
        )
        task_layout.addWidget(self.general_instructions_edit)
        content_layout.addWidget(task_box)

        source_box = QGroupBox("Source instructions")
        source_layout = QVBoxLayout(source_box)
        source_intro = QLabel(
            "Describe this source and how it should be handled: language, period, document type, layout, headings, columns, entries, marginalia, abbreviations, page numbers, tables, or recurring conventions."
        )
        source_intro.setWordWrap(True)
        source_layout.addWidget(source_intro)
        self.source_notes_edit = QPlainTextEdit(self)
        self.source_notes_edit.setMinimumHeight(150)
        self.source_notes_edit.setPlaceholderText(
            "Example: Danish Lutheran parish register, 17th-18th century. "
            "Two columns. Preserve numbered entries, page headings, marginal notes, "
            "abbreviations, and uncertain readings."
        )
        source_layout.addWidget(self.source_notes_edit)

        self.source_genre_edit = QLineEdit(self)
        self.source_genre_edit.setVisible(False)
        self.structure_rules_edit = self.source_notes_edit
        self.custom_instructions_edit = QPlainTextEdit(self)
        self.custom_instructions_edit.setVisible(False)
        self.preserve_line_breaks_checkbox = QCheckBox("Preserve line breaks", self)
        self.preserve_line_breaks_checkbox.setVisible(False)
        self.preserve_marginalia_checkbox = QCheckBox("Preserve marginalia", self)
        self.preserve_marginalia_checkbox.setVisible(False)
        self.normalize_whitespace_checkbox = QCheckBox("Normalize whitespace", self)
        self.normalize_whitespace_checkbox.setVisible(False)
        content_layout.addWidget(source_box)

        details_box = QGroupBox("Model")
        details_layout = QVBoxLayout(details_box)
        self.details_help_label = QLabel("")
        self.details_help_label.setWordWrap(True)
        details_layout.addWidget(self.details_help_label)

        metadata_form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.task_type_combo = QComboBox(self)
        for task_type, label in TASK_TYPE_LABELS.items():
            self.task_type_combo.addItem(label, userData=task_type)
        self.batch_size_spin = QSpinBox(self)
        self.batch_size_spin.setRange(1, 20)
        self.provider_combo = QComboBox(self)
        for provider, label in PROVIDER_LABELS.items():
            self.provider_combo.addItem(label, userData=provider)
        self.model_tier_combo = QComboBox(self)
        for tier, label in MODEL_TIER_LABELS.items():
            self.model_tier_combo.addItem(label, userData=tier)
        self.resolved_model_label = QLabel("")
        self.resolved_model_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.provider_resolution_label = QLabel("")
        self.provider_resolution_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.temperature_edit = QLineEdit(self)
        self.temperature_edit.setPlaceholderText("Blank = model default")
        self.name_edit.setVisible(False)
        self.task_type_combo.setVisible(False)
        metadata_form.addRow("Batch size", self.batch_size_spin)
        metadata_form.addRow("Provider", self.provider_combo)
        metadata_form.addRow("Model tier", self.model_tier_combo)
        metadata_form.addRow("", self.provider_resolution_label)
        metadata_form.addRow("Resolved model", self.resolved_model_label)
        metadata_form.addRow("Temperature", self.temperature_edit)
        details_layout.addLayout(metadata_form)
        temperature_hint = QLabel(
            "Leave blank unless you need to control randomness. For transcription, blank or 0 is usually best.\n"
            "Some models do not support temperature. If unsupported, ArchiveStudio will omit it automatically."
        )
        temperature_hint.setWordWrap(True)
        details_layout.addWidget(temperature_hint)

        content_layout.addWidget(details_box)
        content_layout.addStretch(1)

        # Internal prompt assembly fields. They stay hidden so existing preset
        # storage remains compatible without exposing template mechanics.
        self.detailed_instructions_edit = QPlainTextEdit(self)
        self.detailed_instructions_edit.setVisible(False)
        self.response_prefix_edit = QPlainTextEdit(self)
        self.response_prefix_edit.setVisible(False)

        bottom_row = QWidget(self)
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addStretch(1)
        self.save_button = QPushButton("Save Changes", self)
        self.save_button.clicked.connect(self._save_current)
        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.close)
        bottom_layout.addWidget(self.save_button)
        bottom_layout.addWidget(self.close_button)
        layout.addWidget(bottom_row)

    def _connect_dirty_tracking(self) -> None:
        self.name_edit.textChanged.connect(self._on_form_changed)
        self.task_type_combo.currentIndexChanged.connect(self._on_form_changed)
        self.source_genre_edit.textChanged.connect(self._on_form_changed)
        self.structure_rules_edit.textChanged.connect(self._on_form_changed)
        self.custom_instructions_edit.textChanged.connect(self._on_form_changed)
        self.batch_size_spin.valueChanged.connect(self._on_form_changed)
        self.provider_combo.currentIndexChanged.connect(self._on_form_changed)
        self.provider_combo.currentIndexChanged.connect(self._refresh_resolved_model_label)
        self.model_tier_combo.currentIndexChanged.connect(self._on_form_changed)
        self.model_tier_combo.currentIndexChanged.connect(self._refresh_resolved_model_label)
        self.temperature_edit.textChanged.connect(self._on_form_changed)
        self.preserve_line_breaks_checkbox.toggled.connect(self._on_form_changed)
        self.preserve_marginalia_checkbox.toggled.connect(self._on_form_changed)
        self.normalize_whitespace_checkbox.toggled.connect(self._on_form_changed)
        self.general_instructions_edit.textChanged.connect(self._on_form_changed)
        self.detailed_instructions_edit.textChanged.connect(self._on_form_changed)
        self.response_prefix_edit.textChanged.connect(self._on_form_changed)

    def _load_preset_names(self, *, select_name: str | None = None) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        task_filter = str(self.task_filter_combo.currentData() or "")
        for preset in list_presets():
            if preset.task_type not in TASK_TYPE_LABELS:
                continue
            if task_filter and preset.task_type != task_filter:
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

    def _on_task_filter_changed(self) -> None:
        self._load_preset_names(select_name=self.current_preset_name())

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
        self._current_source_genre = preset.source_genre
        self.source_genre_edit.setText(preset.source_genre)
        self.source_notes_edit.setPlainText(self._source_notes_from_preset(preset))
        self.custom_instructions_edit.setPlainText("")
        self.batch_size_spin.setValue(max(1, preset.batch_size))
        self._set_provider(preset.model_config.provider)
        self._set_model_tier(preset.model_config.model_tier)
        self._current_model_id = preset.model_config.model_id or "unset"
        self.temperature_edit.setText(
            "" if preset.model_config.temperature is None else str(preset.model_config.temperature)
        )
        self.preserve_line_breaks_checkbox.setChecked(preset.preserve_line_breaks)
        self.preserve_marginalia_checkbox.setChecked(preset.preserve_marginalia)
        self.normalize_whitespace_checkbox.setChecked(preset.normalize_whitespace)
        self.general_instructions_edit.setPlainText(preset.prompt_template.system_prompt)
        self.detailed_instructions_edit.setPlainText(preset.prompt_template.user_prompt_template)
        self.response_prefix_edit.setPlainText(preset.response_prefix)

        self._apply_editability_state()
        self._refresh_resolved_model_label()
        self._loaded_form_state = self._capture_form_state()
        self._loading_form = False
        self._set_form_dirty(False)

    def _source_notes_from_preset(self, preset) -> str:
        """Fold older source-specific fields into the single visible notes field."""
        notes: list[str] = []
        default_source_genres = {
            "handwritten text",
            "printed text",
            "catalogue / structured listings",
            "custom / other source",
            "general historical text",
            "custom source",
        }
        source_genre = preset.source_genre.strip()
        if source_genre and source_genre not in default_source_genres:
            notes.append(f"Source type: {source_genre}")
        structure_rules = preset.structure_rules.strip()
        if structure_rules:
            notes.append(structure_rules)
        custom_instructions = preset.custom_instructions.strip()
        if custom_instructions:
            notes.append(custom_instructions)
        return "\n\n".join(notes)

    def _apply_editability_state(self) -> None:
        is_user = not self._current_is_builtin
        self.preset_type_label.setText("User preset" if is_user else "Built-in preset")
        if is_user:
            self.preset_help_label.setText(
                "This is your own preset. Edit task instruction, source instructions, or model settings below."
            )
            self.details_help_label.setText(
                "Model and runtime details affect how this preset behaves when a task runs."
            )
            self.save_button.setText("Save Changes")
        else:
            self.preset_help_label.setText(
                "This is a built-in preset. You can edit task instruction, source instructions, and model settings below; "
                "ArchiveStudio will save your changes as an override."
            )
            self.details_help_label.setText(
                "Built-in preset names and task types stay fixed, but you can adjust batch size and model settings."
            )
            self.save_button.setText("Save Changes")
        self.name_edit.setEnabled(is_user)
        self.task_type_combo.setEnabled(is_user)
        self.source_genre_edit.setEnabled(True)
        self.structure_rules_edit.setEnabled(True)
        self.custom_instructions_edit.setEnabled(True)
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
        self._show_saved_usage_message()
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
                and stored.structure_rules == builtin.structure_rules
                and stored.custom_instructions == builtin.custom_instructions
                and stored.provider == builtin.model_config.provider
                and stored.model_tier == builtin.model_config.model_tier
                and stored.model_id == builtin.model_config.model_id
                and stored.temperature == builtin.model_config.temperature
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
                    structure_rules=stored.structure_rules,
                    custom_instructions=stored.custom_instructions,
                    provider=stored.provider,
                    model_tier=stored.model_tier,
                    model_id=stored.model_id,
                    temperature=stored.temperature,
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
        source_genre = self.source_genre_edit.text().strip() or self._current_source_genre
        source_notes = self.source_notes_edit.toPlainText().strip()
        task_type = str(self.task_type_combo.currentData())

        if not name:
            QMessageBox.warning(self, "Missing Preset Name", "Preset name is required.")
            return None
        if not system_prompt or not user_prompt_template:
            if not system_prompt:
                QMessageBox.warning(
                    self,
                    "Missing Task Instruction",
                    "Task instruction is required.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Missing Internal Template",
                    "The internal prompt template is missing. Reset this preset to original or create a new preset.",
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
        try:
            temperature = self._temperature_from_form()
        except ValueError:
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
            structure_rules=source_notes,
            custom_instructions="",
            provider=str(self.provider_combo.currentData() or "configurable"),
            model_tier=str(self.model_tier_combo.currentData() or "strong"),
            model_id=self._current_model_id or "unset",
            temperature=temperature,
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
            structure_rules="",
            custom_instructions="",
            provider="configurable",
            model_tier="strong",
            model_id="unset",
            temperature=None,
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
                    "Transcribe the page shown in the image.\n"
                    "Internal app page sequence: {page_sequence}.\n"
                    "\n"
                    "Source instructions:\n{structure_rules}\n\n"
                    "Return only the transcription."
                ),
            )
        if task_type == "correct":
            return (
                system_prompt,
                (
                    "Correct page {page_sequence}.\n"
                    "\n"
                    "Source instructions:\n{structure_rules}\n\n"
                    "Source text:\n{source_text}\n\n"
                    "Return only the corrected text."
                ),
            )
        return (
            system_prompt,
            (
                "Translate page {page_sequence}.\n"
                "Input stage: {source_stage}.\n"
                "Translate from [source language] to [target language].\n"
                "\n"
                "Source instructions:\n{structure_rules}\n\n"
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

    def _show_saved_usage_message(self) -> None:
        task_type = str(self.task_type_combo.currentData() or "")
        preset_name = self.current_preset_name() or self.name_edit.text().strip()
        panel_label = {
            "transcribe": "Transcribe",
            "correct": "Correct",
            "translate": "Translate",
            "verify": "Verify Transcription",
        }.get(task_type, "the matching task")
        QMessageBox.information(
            self,
            "Preset Saved",
            (
                f"'{preset_name}' was saved.\n\n"
                f"Use it from Tasks > {panel_label}. The preset list for each task "
                "only shows presets that match that task type."
            ),
        )

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

    def _set_provider(self, provider: str) -> None:
        index = self.provider_combo.findData(provider or "configurable")
        self.provider_combo.setCurrentIndex(max(0, index))

    def _set_model_tier(self, tier: str) -> None:
        normalized = tier if tier in MODEL_TIER_LABELS else "strong"
        index = self.model_tier_combo.findData(normalized)
        self.model_tier_combo.setCurrentIndex(max(0, index))

    def _refresh_resolved_model_label(self, *_args: object) -> None:
        if not hasattr(self, "resolved_model_label"):
            return
        provider = str(self.provider_combo.currentData() or "configurable")
        tier = str(self.model_tier_combo.currentData() or "strong")
        resolved_provider, model_id = self._resolved_provider_model(provider, tier)
        if provider == "configurable":
            self.provider_resolution_label.setText(f"Using: {resolved_provider} / {tier}")
            self.provider_resolution_label.setVisible(True)
        else:
            self.provider_resolution_label.clear()
            self.provider_resolution_label.setVisible(False)
        self.resolved_model_label.setText(f"{resolved_provider}: {model_id}")

    def _resolved_provider_model(self, provider: str, tier: str) -> tuple[str, str]:
        settings = load_app_settings()
        provider_name = settings.default_provider if provider == "configurable" else provider
        provider_settings = {
            "openai": settings.openai,
            "anthropic": settings.anthropic,
            "google": settings.google,
        }.get(provider_name)
        if provider_settings is None:
            return provider_name, "not configured"
        return provider_name, provider_settings.model_for_tier(tier)

    def _temperature_from_form(self) -> float | None:
        value = self.temperature_edit.text().strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Temperature",
                "Temperature must be blank or a number, for example 0.2.",
            )
            raise

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
            self.source_notes_edit.toPlainText(),
            self.batch_size_spin.value(),
            self.provider_combo.currentData(),
            self.model_tier_combo.currentData(),
            self.temperature_edit.text(),
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
