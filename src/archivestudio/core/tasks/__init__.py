"""Task services and registry."""

from archivestudio.core.tasks.registry import (
    TASK_CORRECT,
    TASK_TRANSLATE,
    TASK_TRANSCRIBE,
    get_builtin_preset,
    get_preset,
    get_task_definition,
    list_presets,
    list_builtin_presets,
)
from archivestudio.core.tasks.user_presets import (
    PresetTemplate,
    StoredPreset,
    export_user_presets,
    import_user_presets,
    list_preset_templates,
    load_user_presets,
    save_user_presets,
)
from archivestudio.core.tasks.correct import run_correction
from archivestudio.core.tasks.runs import TaskRunSummary
from archivestudio.core.tasks.translate import run_translation
from archivestudio.core.tasks.transcribe import run_transcription
from archivestudio.core.tasks.workflows import (
    HANDWRITTEN_HTR_CORRECTION_WORKFLOW,
    PRINTED_OCR_CORRECTION_WORKFLOW,
    WorkflowRunSummary,
    run_handwritten_htr_and_correction,
    run_printed_ocr_and_correction,
)

__all__ = [
    "TASK_CORRECT",
    "TASK_TRANSLATE",
    "TASK_TRANSCRIBE",
    "HANDWRITTEN_HTR_CORRECTION_WORKFLOW",
    "PRINTED_OCR_CORRECTION_WORKFLOW",
    "TaskRunSummary",
    "WorkflowRunSummary",
    "get_builtin_preset",
    "get_preset",
    "get_task_definition",
    "list_presets",
    "list_builtin_presets",
    "PresetTemplate",
    "StoredPreset",
    "export_user_presets",
    "import_user_presets",
    "list_preset_templates",
    "load_user_presets",
    "run_correction",
    "run_handwritten_htr_and_correction",
    "run_printed_ocr_and_correction",
    "run_transcription",
    "run_translation",
    "save_user_presets",
]
