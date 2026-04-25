"""User-created task presets and template library."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from archivestudio.core.config.paths import user_library_dir
from archivestudio.core.tasks.types import ModelConfig, PromptTemplate, TaskPreset


@dataclass(frozen=True)
class StoredPreset:
    name: str
    task_type: str
    source_genre: str
    system_prompt: str
    user_prompt_template: str
    response_prefix: str = ""
    batch_size: int = 1
    preserve_line_breaks: bool = True
    preserve_marginalia: bool = False
    normalize_whitespace: bool = False
    source_language: str = "auto-detect"
    target_language: str = "English"
    translation_rules: str = ""

    def to_task_preset(self) -> TaskPreset:
        return TaskPreset(
            name=self.name,
            task_type=self.task_type,
            source_genre=self.source_genre,
            prompt_template=PromptTemplate(
                name=_slugify(self.name),
                system_prompt=self.system_prompt,
                user_prompt_template=self.user_prompt_template,
            ),
            model_config=ModelConfig(
                provider="configurable",
                model_id="unset",
                temperature=0.0,
                max_batch_pages=max(1, self.batch_size),
            ),
            batch_size=max(1, self.batch_size),
            preserve_line_breaks=self.preserve_line_breaks,
            preserve_marginalia=self.preserve_marginalia,
            normalize_whitespace=self.normalize_whitespace,
            response_prefix=self.response_prefix,
            source_language=self.source_language,
            target_language=self.target_language,
            translation_rules=self.translation_rules,
        )

    @classmethod
    def from_task_preset(cls, preset: TaskPreset) -> "StoredPreset":
        return cls(
            name=preset.name,
            task_type=preset.task_type,
            source_genre=preset.source_genre,
            system_prompt=preset.prompt_template.system_prompt,
            user_prompt_template=preset.prompt_template.user_prompt_template,
            response_prefix=preset.response_prefix,
            batch_size=max(1, preset.batch_size),
            preserve_line_breaks=preset.preserve_line_breaks,
            preserve_marginalia=preset.preserve_marginalia,
            normalize_whitespace=preset.normalize_whitespace,
            source_language=preset.source_language,
            target_language=preset.target_language,
            translation_rules=preset.translation_rules,
        )


@dataclass(frozen=True)
class PresetTemplate:
    key: str
    label: str
    preset: StoredPreset


def user_presets_path() -> Path:
    return user_library_dir() / "user_presets.json"


def load_user_presets() -> dict[str, StoredPreset]:
    path = user_presets_path()
    if not path.exists():
        return {}

    raw = _load_json_or_quarantine(path)
    if not isinstance(raw, dict):
        return {}
    loaded: dict[str, StoredPreset] = {}
    for payload in raw.get("presets", []):
        if not isinstance(payload, dict):
            continue
        preset = StoredPreset(
            name=str(payload.get("name", "")).strip(),
            task_type=str(payload.get("task_type", "")).strip(),
            source_genre=str(payload.get("source_genre", "")).strip(),
            system_prompt=str(payload.get("system_prompt", "")),
            user_prompt_template=str(payload.get("user_prompt_template", "")),
            response_prefix=str(payload.get("response_prefix", "")),
            batch_size=max(1, int(payload.get("batch_size", 1))),
            preserve_line_breaks=bool(payload.get("preserve_line_breaks", True)),
            preserve_marginalia=bool(payload.get("preserve_marginalia", False)),
            normalize_whitespace=bool(payload.get("normalize_whitespace", False)),
            source_language=str(payload.get("source_language", "auto-detect")).strip() or "auto-detect",
            target_language=str(payload.get("target_language", "English")).strip() or "English",
            translation_rules=str(payload.get("translation_rules", "")),
        )
        if preset.name:
            loaded[preset.name] = preset
    return loaded


def save_user_presets(presets: dict[str, StoredPreset]) -> Path:
    path = user_presets_path()
    payload = {
        "version": 1,
        "presets": [
            asdict(preset)
            for _, preset in sorted(presets.items())
        ],
    }
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def import_user_presets(import_path: Path) -> dict[str, StoredPreset]:
    raw = json.loads(import_path.read_text(encoding="utf-8"))
    loaded: dict[str, StoredPreset] = {}

    presets_payload = raw.get("presets", raw)
    if isinstance(presets_payload, dict):
        presets_payload = list(presets_payload.values())

    for payload in presets_payload:
        if not isinstance(payload, dict):
            continue
        preset = StoredPreset(
            name=str(payload.get("name", "")).strip(),
            task_type=str(payload.get("task_type", "")).strip(),
            source_genre=str(payload.get("source_genre", "")).strip(),
            system_prompt=str(payload.get("system_prompt", "")),
            user_prompt_template=str(payload.get("user_prompt_template", "")),
            response_prefix=str(payload.get("response_prefix", "")),
            batch_size=max(1, int(payload.get("batch_size", 1))),
            preserve_line_breaks=bool(payload.get("preserve_line_breaks", True)),
            preserve_marginalia=bool(payload.get("preserve_marginalia", False)),
            normalize_whitespace=bool(payload.get("normalize_whitespace", False)),
            source_language=str(payload.get("source_language", "auto-detect")).strip() or "auto-detect",
            target_language=str(payload.get("target_language", "English")).strip() or "English",
            translation_rules=str(payload.get("translation_rules", "")),
        )
        if preset.name:
            loaded[preset.name] = preset
    return loaded


def export_user_presets(export_path: Path, presets: dict[str, StoredPreset]) -> Path:
    payload = {
        "version": 1,
        "presets": [
            asdict(preset)
            for _, preset in sorted(presets.items())
        ],
    }
    _atomic_write_text(export_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return export_path


def list_preset_templates() -> list[PresetTemplate]:
    return [
        PresetTemplate(
            key="latin_manuscript_correction",
            label="Latin Manuscript Correction (Marginalia Inline)",
            preset=StoredPreset(
                name="Latin Manuscript Correction",
                task_type="correct",
                source_genre="Latin manuscript",
                system_prompt=(
                    "Your task is to compare pages of Latin text with corresponding optical "
                    "character recognition, correcting the transcription to produce a clean, "
                    "readable transcript. Work systematically through the text, comparing "
                    "each word with the handwritten original.\n\n"
                    "Your primary tasks are:\n"
                    "1. Join all hyphenated words by removing hyphen markers and connecting the word parts into complete words\n"
                    "2. Fix character displacement errors where letters appear in wrong positions\n"
                    "3. Place marginal notes immediately after their relevant text passages using the format [MARGIN: note text]\n"
                    "4. Correct obvious OCR errors while preserving historical Latin spelling"
                ),
                user_prompt_template=(
                    "Your task is to use the handwritten Latin page image to create a clean transcript "
                    "by joining all hyphenated words, fixing character errors, and placing marginal notes "
                    "inline with [MARGIN: note] format in the following text:\n"
                    "{text_to_process}"
                ),
                response_prefix="Corrected Transcript:",
                batch_size=1,
                preserve_line_breaks=False,
                preserve_marginalia=True,
                normalize_whitespace=False,
            ),
        ),
        PresetTemplate(
            key="marginalia_preserving_transcription",
            label="Marginalia-Preserving Transcription",
            preset=StoredPreset(
                name="Marginalia-Preserving Transcription",
                task_type="transcribe",
                source_genre="annotated manuscript",
                system_prompt=(
                    "You are transcribing historical manuscripts with meaningful marginalia. "
                    "Preserve main text faithfully and mark marginal notes inline using "
                    "[MARGIN: ...] near the relevant passage."
                ),
                user_prompt_template=(
                    "Transcribe this manuscript page.\n"
                    "Preserve page numbers, line structure where useful, and insert marginalia inline.\n"
                    "Structure rules:\n{structure_rules}\n"
                    "Return only the transcription."
                ),
                batch_size=1,
                preserve_line_breaks=True,
                preserve_marginalia=True,
                normalize_whitespace=False,
            ),
        ),
    ]


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _load_json_or_quarantine(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _quarantine_corrupt_file(path)
        return {}


def _quarantine_corrupt_file(path: Path) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.corrupt-{timestamp}")
    try:
        path.replace(backup_path)
    except OSError:
        pass


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise
