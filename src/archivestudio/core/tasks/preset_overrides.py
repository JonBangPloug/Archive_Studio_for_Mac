"""User-editable prompt overrides for task presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from archivestudio.core.config.paths import user_library_dir


@dataclass(frozen=True)
class PresetOverride:
    system_prompt: str
    user_prompt_template: str
    response_prefix: str = ""
    source_genre: str | None = None
    batch_size: int | None = None
    preserve_line_breaks: bool | None = None
    preserve_marginalia: bool | None = None
    normalize_whitespace: bool | None = None
    provider: str | None = None
    model_tier: str | None = None
    model_id: str | None = None
    temperature: float | None = None
    source_language: str | None = None
    target_language: str | None = None
    translation_rules: str | None = None


def preset_overrides_path() -> Path:
    """Canonical JSON file for user prompt overrides."""
    return user_library_dir() / "preset_overrides.json"


def load_preset_overrides() -> dict[str, PresetOverride]:
    """Load all stored preset overrides keyed by preset name."""
    path = preset_overrides_path()
    if not path.exists():
        return {}

    raw = _load_json_or_quarantine(path)
    if not isinstance(raw, dict):
        return {}
    loaded: dict[str, PresetOverride] = {}
    for name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        loaded[str(name)] = PresetOverride(
            system_prompt=str(payload.get("system_prompt", "")),
            user_prompt_template=str(payload.get("user_prompt_template", "")),
            response_prefix=str(payload.get("response_prefix", "")),
            source_genre=(
                str(payload.get("source_genre", "")).strip()
                if payload.get("source_genre") is not None
                else None
            ),
            batch_size=(
                max(1, int(payload.get("batch_size", 1)))
                if payload.get("batch_size") is not None
                else None
            ),
            preserve_line_breaks=(
                bool(payload.get("preserve_line_breaks"))
                if payload.get("preserve_line_breaks") is not None
                else None
            ),
            preserve_marginalia=(
                bool(payload.get("preserve_marginalia"))
                if payload.get("preserve_marginalia") is not None
                else None
            ),
            normalize_whitespace=(
                bool(payload.get("normalize_whitespace"))
                if payload.get("normalize_whitespace") is not None
                else None
            ),
            provider=(
                str(payload.get("provider", "")).strip()
                if payload.get("provider") is not None
                else None
            ),
            model_tier=(
                str(payload.get("model_tier", "")).strip()
                if payload.get("model_tier") is not None
                else None
            ),
            model_id=(
                str(payload.get("model_id", "")).strip()
                if payload.get("model_id") is not None
                else None
            ),
            temperature=_optional_float(payload.get("temperature")),
            source_language=(
                str(payload.get("source_language", "")).strip()
                if payload.get("source_language") is not None
                else None
            ),
            target_language=(
                str(payload.get("target_language", "")).strip()
                if payload.get("target_language") is not None
                else None
            ),
            translation_rules=(
                str(payload.get("translation_rules", ""))
                if payload.get("translation_rules") is not None
                else None
            ),
        )
    return loaded


def save_preset_overrides(overrides: dict[str, PresetOverride]) -> Path:
    """Persist all overrides to disk."""
    path = preset_overrides_path()
    serializable = {
        name: asdict(override)
        for name, override in sorted(overrides.items())
    }
    _atomic_write_text(path, json.dumps(serializable, indent=2, ensure_ascii=False) + "\n")
    return path


def _load_json_or_quarantine(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _quarantine_corrupt_file(path)
        return {}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
