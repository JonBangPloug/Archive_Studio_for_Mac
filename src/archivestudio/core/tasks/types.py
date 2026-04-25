"""Explicit task, prompt, and model configuration types."""

from __future__ import annotations

from dataclasses import dataclass


TASK_TRANSCRIBE = "transcribe"
TASK_CORRECT = "correct"
TASK_TRANSLATE = "translate"


@dataclass(frozen=True)
class TaskDefinition:
    """Code-defined task contract."""

    task_type: str
    display_name: str
    description: str
    output_stage: str
    supports_batching: bool = False


@dataclass(frozen=True)
class PromptTemplate:
    """Reusable prompt template with simple named placeholders."""

    name: str
    system_prompt: str
    user_prompt_template: str


@dataclass(frozen=True)
class ModelConfig:
    """Reusable model settings for a provider call."""

    provider: str
    model_id: str
    temperature: float = 0.0
    max_batch_pages: int = 1


@dataclass(frozen=True)
class TaskPreset:
    """User-facing preset composition for one task."""

    name: str
    task_type: str
    source_genre: str
    prompt_template: PromptTemplate
    model_config: ModelConfig
    batch_size: int = 1
    preserve_line_breaks: bool = True
    preserve_marginalia: bool = False
    normalize_whitespace: bool = False
    custom_instructions: str = ""
    response_prefix: str = ""
    source_language: str = "auto-detect"
    target_language: str = "English"
    translation_rules: str = ""
