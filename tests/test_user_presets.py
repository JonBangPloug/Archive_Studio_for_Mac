"""User preset library tests."""

from __future__ import annotations

from pathlib import Path

from archivestudio.core.tasks import get_preset, list_presets
from archivestudio.core.tasks import user_presets as user_presets_module
from archivestudio.core.tasks.user_presets import (
    StoredPreset,
    export_user_presets,
    import_user_presets,
    load_user_presets,
    save_user_presets,
)


def test_save_and_load_user_presets_round_trip(tmp_path: Path, monkeypatch) -> None:
    storage_path = tmp_path / "user_presets.json"
    monkeypatch.setattr(user_presets_module, "user_presets_path", lambda: storage_path)

    original = {
        "Latin Manuscript Correction": StoredPreset(
            name="Latin Manuscript Correction",
            task_type="correct",
            source_genre="Latin manuscript",
            system_prompt="Compare image and OCR",
            user_prompt_template="Correct the text:\n{text_to_process}",
            response_prefix="Corrected Transcript:",
            batch_size=1,
            preserve_line_breaks=False,
            preserve_marginalia=True,
            normalize_whitespace=False,
        )
    }

    save_user_presets(original)
    loaded = load_user_presets()

    assert loaded == original


def test_load_user_presets_quarantines_corrupt_json(tmp_path: Path, monkeypatch) -> None:
    storage_path = tmp_path / "user_presets.json"
    storage_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(user_presets_module, "user_presets_path", lambda: storage_path)

    loaded = load_user_presets()

    assert loaded == {}
    assert not storage_path.exists()
    assert list(tmp_path.glob("user_presets.json.corrupt-*"))


def test_import_and_export_user_presets(tmp_path: Path) -> None:
    export_path = tmp_path / "export.json"
    presets = {
        "Scholarly Latin Correction": StoredPreset(
            name="Scholarly Latin Correction",
            task_type="correct",
            source_genre="Latin text",
            system_prompt="Correct carefully",
            user_prompt_template="Correct this text:\n{text_to_process}",
            batch_size=1,
            preserve_line_breaks=False,
            preserve_marginalia=True,
            normalize_whitespace=True,
        )
    }

    export_user_presets(export_path, presets)
    loaded = import_user_presets(export_path)

    assert loaded == presets


def test_registry_exposes_user_preset(monkeypatch) -> None:
    custom = StoredPreset(
        name="My Imported Preset",
        task_type="transcribe",
        source_genre="special source",
        system_prompt="Special transcription rules",
        user_prompt_template="Transcribe this page",
        batch_size=2,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
    )

    monkeypatch.setattr(
        "archivestudio.core.tasks.user_presets.load_user_presets",
        lambda: {custom.name: custom},
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_user_presets",
        lambda: {custom.name: custom},
    )

    preset = get_preset(custom.name)
    preset_names = {preset.name for preset in list_presets()}

    assert preset.name == custom.name
    assert preset.task_type == "transcribe"
    assert preset.batch_size == 1
    assert preset.model_config.max_batch_pages == 1
    assert custom.name in preset_names


def test_user_preset_preserves_legacy_concrete_model_id(monkeypatch) -> None:
    custom = StoredPreset(
        name="Legacy Exact Model Preset",
        task_type="transcribe",
        source_genre="special source",
        system_prompt="Special transcription rules",
        user_prompt_template="Transcribe this page",
        model_id="legacy-exact-model",
        model_tier="fast",
    )

    monkeypatch.setattr(
        "archivestudio.core.tasks.user_presets.load_user_presets",
        lambda: {custom.name: custom},
    )
    monkeypatch.setattr(
        "archivestudio.core.tasks.registry.load_user_presets",
        lambda: {custom.name: custom},
    )

    preset = get_preset(custom.name)

    assert preset.model_config.model_id == "legacy-exact-model"
    assert preset.model_config.model_tier == "fast"
