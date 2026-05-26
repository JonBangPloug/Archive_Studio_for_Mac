"""Validation for user-editable task prompt templates."""

from __future__ import annotations

from string import Formatter

from archivestudio.core.tasks.types import (
    TASK_CORRECT,
    TASK_TRANSLATE,
    TASK_TRANSCRIBE,
)


class PromptTemplateValidationError(ValueError):
    """Raised when a prompt template cannot be rendered safely for a task."""


_ALLOWED_PLACEHOLDERS = {
    TASK_TRANSCRIBE: {
        "custom_instructions",
        "page_sequence",
        "source_genre",
        "structure_rules",
        "text_to_process",
    },
    TASK_CORRECT: {
        "custom_instructions",
        "page_sequence",
        "source_genre",
        "source_text",
        "structure_rules",
        "text_to_process",
    },
    TASK_TRANSLATE: {
        "custom_instructions",
        "page_sequence",
        "source_genre",
        "source_language",
        "source_stage",
        "source_text",
        "structure_rules",
        "target_language",
        "text_to_process",
        "translation_rules",
    },
}

_REQUIRED_PLACEHOLDERS = {
    TASK_CORRECT: {"source_text"},
    TASK_TRANSLATE: {
        "source_stage",
        "source_text",
    },
}


def validate_prompt_template(template: str, *, task_type: str) -> None:
    """Validate that ``template`` only uses placeholders supported by a task."""
    allowed = _ALLOWED_PLACEHOLDERS.get(task_type)
    if allowed is None:
        raise PromptTemplateValidationError(f"Unknown task type: {task_type}")

    try:
        field_names = [
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name is not None
        ]
    except ValueError as exc:
        raise PromptTemplateValidationError(
            "The detailed instructions contain unmatched braces. "
            "Use '{{' and '}}' for literal braces."
        ) from exc

    invalid = sorted(
        field_name
        for field_name in field_names
        if not _is_allowed_field(field_name, allowed)
    )
    if invalid:
        allowed_list = ", ".join(f"{{{name}}}" for name in sorted(allowed))
        invalid_list = ", ".join(f"{{{name}}}" for name in invalid)
        raise PromptTemplateValidationError(
            f"Unsupported placeholder(s): {invalid_list}.\n\n"
            f"Allowed placeholders for this task: {allowed_list}."
        )

    present = {
        field_name
        for field_name in field_names
        if _is_allowed_field(field_name, allowed)
    }
    missing = sorted(_REQUIRED_PLACEHOLDERS.get(task_type, set()) - present)
    if missing:
        missing_list = ", ".join(f"{{{name}}}" for name in missing)
        raise PromptTemplateValidationError(
            f"Missing required placeholder(s): {missing_list}."
        )


def _is_allowed_field(field_name: str, allowed: set[str]) -> bool:
    # Keep templates deliberately simple: no indexing, attributes, or conversion
    # tricks. This makes user errors easier to explain and safer to render.
    if "." in field_name or "[" in field_name or "]" in field_name:
        return False
    return field_name in allowed
