"""Task launch policy tests."""

from __future__ import annotations

from dataclasses import dataclass

from archivestudio.core.models import SOURCE_TYPE_HANDWRITTEN, SOURCE_TYPE_PRINTED
from archivestudio.core.tasks import TASK_CORRECT, TASK_TRANSCRIBE
from archivestudio.ui.task_launch import (
    preset_name_for_source_type,
    prioritize_preset_names,
    recommended_preset_for_source_types,
    selected_source_types,
)


@dataclass(frozen=True)
class Record:
    id: str
    source_type: str | None


def test_recommended_preset_for_single_source_type() -> None:
    source_types = {SOURCE_TYPE_HANDWRITTEN}

    assert (
        recommended_preset_for_source_types(TASK_TRANSCRIBE, source_types)
        == "Handwritten Transcription"
    )


def test_recommended_preset_is_not_auto_selected_for_mixed_source_types() -> None:
    source_types = {SOURCE_TYPE_HANDWRITTEN, SOURCE_TYPE_PRINTED}

    assert recommended_preset_for_source_types(TASK_CORRECT, source_types) is None


def test_selected_source_types_filters_by_page_ids() -> None:
    records = [
        Record(id="page-1", source_type=SOURCE_TYPE_HANDWRITTEN),
        Record(id="page-2", source_type=SOURCE_TYPE_PRINTED),
    ]

    assert selected_source_types(records, ["page-2"]) == {SOURCE_TYPE_PRINTED}


def test_prioritize_preset_names_moves_relevant_options_first() -> None:
    names = [
        "Custom Transcription",
        "Printed Transcription",
        "Handwritten Transcription",
    ]

    assert prioritize_preset_names(
        names,
        task_type=TASK_TRANSCRIBE,
        preferred_source_types={SOURCE_TYPE_PRINTED},
    ) == [
        "Printed Transcription",
        "Custom Transcription",
        "Handwritten Transcription",
    ]


def test_preset_name_for_source_type_handles_unknown_task() -> None:
    assert preset_name_for_source_type("unknown", SOURCE_TYPE_PRINTED) is None
