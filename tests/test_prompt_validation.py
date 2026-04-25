"""Prompt template validation tests."""

from __future__ import annotations

import pytest

from archivestudio.core.tasks.prompt_validation import (
    PromptTemplateValidationError,
    validate_prompt_template,
)
from archivestudio.core.tasks.types import (
    TASK_CORRECT,
    TASK_TRANSLATE,
    TASK_TRANSCRIBE,
)


def test_validate_prompt_template_accepts_task_placeholders() -> None:
    validate_prompt_template(
        "Transcribe {page_sequence}\n{structure_rules}\n{text_to_process}",
        task_type=TASK_TRANSCRIBE,
    )
    validate_prompt_template(
        "Correct {source_text}\n{text_to_process}",
        task_type=TASK_CORRECT,
    )


def test_validate_prompt_template_rejects_unknown_placeholder() -> None:
    with pytest.raises(PromptTemplateValidationError, match="Unsupported placeholder"):
        validate_prompt_template("Correct this: {text}", task_type=TASK_CORRECT)


def test_validate_prompt_template_rejects_unmatched_braces() -> None:
    with pytest.raises(PromptTemplateValidationError, match="unmatched braces"):
        validate_prompt_template("Return JSON like {pages", task_type=TASK_TRANSCRIBE)


def test_validate_prompt_template_requires_source_text_for_correction() -> None:
    with pytest.raises(PromptTemplateValidationError, match="source_text"):
        validate_prompt_template("Correct page {page_sequence}", task_type=TASK_CORRECT)


def test_validate_prompt_template_accepts_translation_placeholders() -> None:
    validate_prompt_template(
        (
            "Translate {page_sequence} from Latin to English.\n"
            "Input stage: {source_stage}\n"
            "{source_text}"
        ),
        task_type=TASK_TRANSLATE,
    )


def test_validate_prompt_template_requires_translation_context() -> None:
    with pytest.raises(PromptTemplateValidationError, match="source_stage"):
        validate_prompt_template(
            "Translate this source text to English:\n{source_text}",
            task_type=TASK_TRANSLATE,
        )
