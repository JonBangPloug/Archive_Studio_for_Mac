"""Task prompt override tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import select

from archivestudio.core import tasks as tasks_module
from archivestudio.core.tasks import get_preset, run_correction
from archivestudio.core.tasks.preset_overrides import (
    PresetOverride,
    load_preset_overrides,
    save_preset_overrides,
)
from archivestudio.core.tasks import preset_overrides as preset_overrides_module
from archivestudio.core.ai.base import AIProvider, CorrectionResult, TranscriptionResult
from archivestudio.core.ingest import import_image_folder
from archivestudio.core.models import STAGE_CORRECTED, TextVersion
from archivestudio.core.project import create_project
from archivestudio.core.tasks import get_builtin_preset, run_transcription
from archivestudio.ui.dialogs.task_prompt_settings_dialog import TaskPromptSettingsDialog


class PrefixProvider(AIProvider):
    provider_name = "fake"
    model_id = "prefix-test"
    supports_batching = True

    def __init__(self) -> None:
        self.last_correction_prompt: str | None = None

    def transcribe_pages(self, requests, *, model_config):
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription="Original OCR text",
            )
            for request in requests
        ]

    def correct_pages(self, requests, *, model_config):
        self.last_correction_prompt = requests[0].prompt.user
        return [
            CorrectionResult(
                page_id=request.page_id,
                corrected_text="Corrected Transcript:\nGallia est omnis divisa",
            )
            for request in requests
        ]


def test_preset_override_loads_and_applies(monkeypatch, tmp_path: Path) -> None:
    overrides_path = tmp_path / "preset_overrides.json"
    monkeypatch.setattr(
        preset_overrides_module,
        "preset_overrides_path",
        lambda: overrides_path,
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_preset_overrides",
        load_preset_overrides,
    )

    save_preset_overrides(
        {
            "Printed Correction": PresetOverride(
                system_prompt="General instructions here",
                user_prompt_template="Detailed instructions here\n{text_to_process}",
                response_prefix="Corrected Transcript:",
                source_genre="Latin printed text",
                batch_size=4,
                preserve_line_breaks=False,
                preserve_marginalia=True,
                normalize_whitespace=True,
            )
        }
    )

    preset = get_preset("Printed Correction")

    assert preset.prompt_template.system_prompt == "General instructions here"
    assert preset.prompt_template.user_prompt_template.endswith("{text_to_process}")
    assert preset.response_prefix == "Corrected Transcript:"
    assert preset.source_genre == "Latin printed text"
    assert preset.batch_size == 4
    assert preset.preserve_line_breaks is False
    assert preset.preserve_marginalia is True
    assert preset.normalize_whitespace is True


def test_preset_override_load_quarantines_corrupt_json(monkeypatch, tmp_path: Path) -> None:
    overrides_path = tmp_path / "preset_overrides.json"
    overrides_path.write_text("{broken json", encoding="utf-8")
    monkeypatch.setattr(
        preset_overrides_module,
        "preset_overrides_path",
        lambda: overrides_path,
    )

    assert load_preset_overrides() == {}
    assert not overrides_path.exists()
    assert list(tmp_path.glob("preset_overrides.json.corrupt-*"))


def test_correction_uses_override_and_strips_prefix(monkeypatch, tmp_path: Path) -> None:
    overrides_path = tmp_path / "preset_overrides.json"
    monkeypatch.setattr(
        preset_overrides_module,
        "preset_overrides_path",
        lambda: overrides_path,
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_preset_overrides",
        load_preset_overrides,
    )

    save_preset_overrides(
        {
            "Printed Correction": PresetOverride(
                system_prompt="Compare Latin image and OCR",
                user_prompt_template=(
                    "Detailed instructions:\n{text_to_process}\n"
                    "Return Corrected Transcript: followed by the cleaned text."
                ),
                response_prefix="Corrected Transcript:",
            )
        }
    )

    project = create_project(tmp_path / "project", name="Prompt Overrides")
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    Image.new("RGB", (80, 60), color="black").save(source_dir / "page1.png")
    import_image_folder(project, source_dir, source_type="printed")

    provider = PrefixProvider()

    try:
        run_transcription(
            project,
            provider,
            replace(get_builtin_preset("Printed Transcription"), batch_size=1),
        )
        summary = run_correction(project, provider, get_preset("Printed Correction"))

        assert summary.pages_completed == 1
        assert provider.last_correction_prompt is not None
        assert "Original OCR text" in provider.last_correction_prompt

        with project.session() as session:
            corrected = session.execute(
                select(TextVersion).where(TextVersion.stage == STAGE_CORRECTED)
            ).scalar_one()

        assert corrected.content == "Gallia est omnis divisa"
    finally:
        project.close()


def test_prompt_dialog_preserves_unsaved_text_when_preset_switch_is_cancelled(
    monkeypatch, qtbot
) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.preset_combo.count() >= 2
    original_name = dialog.current_preset_name()
    assert original_name is not None

    dialog.general_instructions_edit.setPlainText("Unsaved custom instructions")

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    dialog.preset_combo.setCurrentIndex(1)

    assert dialog.current_preset_name() == original_name
    assert dialog.general_instructions_edit.toPlainText() == "Unsaved custom instructions"


def test_prompt_dialog_discard_allows_close(monkeypatch, qtbot) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.general_instructions_edit.setPlainText("Unsaved custom instructions")

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    dialog.close()

    assert dialog.isVisible() is False


def test_prompt_dialog_can_reset_builtin_override(monkeypatch, qtbot, tmp_path: Path) -> None:
    overrides_path = tmp_path / "preset_overrides.json"
    monkeypatch.setattr(
        preset_overrides_module,
        "preset_overrides_path",
        lambda: overrides_path,
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_preset_overrides",
        load_preset_overrides,
    )

    save_preset_overrides(
        {
            "Handwritten Transcription": PresetOverride(
                system_prompt="Overridden prompt text",
                user_prompt_template="Overridden detail",
                response_prefix="",
                batch_size=4,
            )
        }
    )

    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    index = dialog._find_preset_index("Handwritten Transcription")
    dialog.preset_combo.setCurrentIndex(index)
    assert dialog.reset_preset_button.isEnabled() is True

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog._reset_selected_preset()

    assert "Handwritten Transcription" not in load_preset_overrides()


def test_prompt_dialog_builtin_details_can_be_saved_as_override(monkeypatch, qtbot, tmp_path: Path) -> None:
    overrides_path = tmp_path / "preset_overrides.json"
    monkeypatch.setattr(
        preset_overrides_module,
        "preset_overrides_path",
        lambda: overrides_path,
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_preset_overrides",
        load_preset_overrides,
    )

    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    index = dialog._find_preset_index("Handwritten Transcription")
    dialog.preset_combo.setCurrentIndex(index)

    assert dialog.batch_size_spin.isEnabled() is True
    assert dialog.general_instructions_edit.isEnabled() is True
    assert dialog.source_notes_edit.isEnabled() is True

    dialog.batch_size_spin.setValue(4)
    task_instruction = "Correct Latin manuscript text conservatively against the image."
    dialog.general_instructions_edit.setPlainText(task_instruction)
    source_notes = (
        "Latin manuscript.\n"
        "Two columns; preserve rubric headings.\n"
        "Mark uncertain expansions with [?]."
    )
    dialog.source_notes_edit.setPlainText(source_notes)
    dialog.preserve_line_breaks_checkbox.setChecked(False)
    dialog.model_tier_combo.setCurrentIndex(dialog.model_tier_combo.findData("fast"))
    dialog.temperature_edit.setText("0.2")

    assert dialog._save_current_preset() is True

    saved = load_preset_overrides()["Handwritten Transcription"]
    assert saved.batch_size == 4
    assert saved.system_prompt == task_instruction
    assert saved.structure_rules == source_notes
    assert saved.custom_instructions == ""
    assert saved.preserve_line_breaks is False
    assert saved.model_tier == "fast"
    assert saved.temperature == 0.2


def test_prompt_dialog_exposes_only_fast_and_strong_model_tiers(qtbot) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    tiers = {
        dialog.model_tier_combo.itemData(index)
        for index in range(dialog.model_tier_combo.count())
    }

    assert tiers == {"fast", "strong"}
    assert not hasattr(dialog, "concrete_model_edit")


def test_prompt_dialog_exposes_only_user_facing_prompt_fields(qtbot) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "prompt_tabs")
    assert dialog.general_instructions_edit.isHidden() is False
    assert dialog.source_notes_edit.isHidden() is False
    assert dialog.detailed_instructions_edit.isHidden() is True
    assert dialog.response_prefix_edit.isHidden() is True


def test_prompt_dialog_rejects_unknown_placeholder(monkeypatch, qtbot) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    index = dialog._find_preset_index("Printed Correction")
    dialog.preset_combo.setCurrentIndex(index)
    dialog.detailed_instructions_edit.setPlainText("Correct this text: {text}")

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    assert dialog._save_current_preset() is False
    assert warnings
    assert warnings[0][0] == "Invalid Prompt Placeholder"
    assert "{text}" in warnings[0][1]


def test_prompt_dialog_disables_delete_for_builtin_presets(qtbot) -> None:
    dialog = TaskPromptSettingsDialog()
    qtbot.addWidget(dialog)

    index = dialog._find_preset_index("Handwritten Transcription")
    dialog.preset_combo.setCurrentIndex(index)

    assert dialog.delete_preset_button.isEnabled() is False
