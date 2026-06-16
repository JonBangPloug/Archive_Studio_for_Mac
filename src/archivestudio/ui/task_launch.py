"""Task launch value objects and source-type preset policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from archivestudio.core.models import (
    SOURCE_TYPE_CATALOGUE,
    SOURCE_TYPE_CUSTOM,
    SOURCE_TYPE_HANDWRITTEN,
    SOURCE_TYPE_PRINTED,
)
from archivestudio.core.tasks import TASK_CORRECT, TASK_TRANSLATE, TASK_TRANSCRIBE, TASK_VERIFY


@dataclass(frozen=True)
class TaskLaunch:
    task_type: str
    scope_label: str
    page_ids: list[str] | None
    preset_name: str
    output_stage: str
    auto_selected_preset: bool = False
    custom_instructions: str = ""
    pages_per_call: int | None = None
    write_checkpoints: bool = True


@dataclass(frozen=True)
class TaskScopeSelection:
    page_ids: list[str] | None
    scope_label: str


class SourceTypedRecord(Protocol):
    id: str
    source_type: str | None


SOURCE_TYPE_PRESET_NAMES = {
    TASK_TRANSCRIBE: {
        SOURCE_TYPE_HANDWRITTEN: "Handwritten Transcription",
        SOURCE_TYPE_PRINTED: "Printed Transcription",
        SOURCE_TYPE_CATALOGUE: "Structured / Catalogue Transcription",
        SOURCE_TYPE_CUSTOM: "Custom Transcription",
    },
    TASK_CORRECT: {
        SOURCE_TYPE_HANDWRITTEN: "Handwritten Correction",
        SOURCE_TYPE_PRINTED: "Printed Correction",
        SOURCE_TYPE_CATALOGUE: "Structured / Catalogue Correction",
        SOURCE_TYPE_CUSTOM: "Custom Correction",
    },
    TASK_TRANSLATE: {
        SOURCE_TYPE_HANDWRITTEN: "Scholarly Translation to English",
        SOURCE_TYPE_PRINTED: "Scholarly Translation to English",
        SOURCE_TYPE_CATALOGUE: "Scholarly Translation to English",
        SOURCE_TYPE_CUSTOM: "Scholarly Translation to English",
    },
    TASK_VERIFY: {
        SOURCE_TYPE_HANDWRITTEN: "Independent Transcription Verification",
        SOURCE_TYPE_PRINTED: "Independent Transcription Verification",
        SOURCE_TYPE_CATALOGUE: "Independent Transcription Verification",
        SOURCE_TYPE_CUSTOM: "Independent Transcription Verification",
    },
}

SOURCE_TYPE_PRIORITY = (
    SOURCE_TYPE_HANDWRITTEN,
    SOURCE_TYPE_PRINTED,
    SOURCE_TYPE_CATALOGUE,
    SOURCE_TYPE_CUSTOM,
)


def preset_name_for_source_type(task_type: str, source_type: str) -> str | None:
    """Return the built-in preset name that best matches a source type."""
    return SOURCE_TYPE_PRESET_NAMES.get(task_type, {}).get(source_type)


def selected_source_types(
    records: Iterable[SourceTypedRecord],
    page_ids: list[str] | None,
) -> set[str | None]:
    """Return source types represented by a selected page set."""
    if page_ids is None:
        selected_records = list(records)
    else:
        allowed_ids = set(page_ids)
        selected_records = [record for record in records if record.id in allowed_ids]
    return {record.source_type for record in selected_records}


def recommended_preset_for_source_types(
    task_type: str,
    source_types: set[str | None],
) -> str | None:
    """Return an auto-selectable preset when all selected pages share one known type."""
    if len(source_types) != 1:
        return None
    source_type = next(iter(source_types))
    if source_type is None:
        return None
    return preset_name_for_source_type(task_type, source_type)


def prioritize_preset_names(
    preset_names: list[str],
    *,
    task_type: str,
    preferred_source_types: set[str | None],
) -> list[str]:
    """Move source-type recommendations to the front of a preset list."""
    ordered = list(preset_names)
    recommendations = [
        preset_name_for_source_type(task_type, source_type)
        for source_type in SOURCE_TYPE_PRIORITY
        if source_type in preferred_source_types
    ]
    for recommended in reversed([name for name in recommendations if name is not None]):
        if recommended in ordered:
            ordered.remove(recommended)
            ordered.insert(0, recommended)
    return ordered
