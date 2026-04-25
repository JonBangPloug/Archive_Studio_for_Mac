"""Built-in task definitions and presets for v1."""

from __future__ import annotations

from dataclasses import replace

from archivestudio.core.models import STAGE_ORIGINAL, STAGE_TRANSLATED
from archivestudio.core.tasks.preset_overrides import load_preset_overrides
from archivestudio.core.tasks.types import (
    TASK_CORRECT,
    TASK_TRANSLATE,
    TASK_TRANSCRIBE,
    ModelConfig,
    PromptTemplate,
    TaskDefinition,
    TaskPreset,
)
from archivestudio.core.tasks.user_presets import load_user_presets


_TRANSCRIPTION_DEFINITION = TaskDefinition(
    task_type=TASK_TRANSCRIBE,
    display_name="Transcribe Page Images",
    description=(
        "Create an original text version from page images while preserving "
        "historically meaningful structure."
    ),
    output_stage=STAGE_ORIGINAL,
    supports_batching=True,
)

_CORRECTION_DEFINITION = TaskDefinition(
    task_type=TASK_CORRECT,
    display_name="Correct OCR / HTR",
    description=(
        "Improve an existing transcription by comparing it back to the page image "
        "while preserving historically meaningful structure."
    ),
    output_stage="corrected",
    supports_batching=True,
)

_TRANSLATION_DEFINITION = TaskDefinition(
    task_type=TASK_TRANSLATE,
    display_name="Translate Text",
    description=(
        "Translate original or corrected text into a separate "
        "translated stage while preserving scholarly provenance."
    ),
    output_stage=STAGE_TRANSLATED,
    supports_batching=True,
)


_TRANSCRIPTION_BASE_MODEL = ModelConfig(
    provider="configurable",
    model_id="unset",
    temperature=0.0,
    max_batch_pages=8,
)


_HANDWRITTEN_PROMPT = PromptTemplate(
    name="handwritten_transcription",
    system_prompt=(
        "You are transcribing historical handwritten text from an image. Preserve "
        "original spelling, abbreviations, punctuation, capitalization, and line "
        "breaks when they are meaningful. Do not translate, summarize, modernize, "
        "or silently expand abbreviations. If something is unclear, keep the "
        "reading conservative."
    ),
    user_prompt_template=(
        "Transcribe page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Return only the transcription."
    ),
)

_PRINTED_PROMPT = PromptTemplate(
    name="printed_transcription",
    system_prompt=(
        "You are transcribing historical printed text from an image. Preserve "
        "original wording, spelling, punctuation, capitalization, and meaningful "
        "layout cues. Do not modernize, summarize, or normalize unless explicitly "
        "instructed."
    ),
    user_prompt_template=(
        "Transcribe page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Return only the transcription."
    ),
)

_CATALOGUE_PROMPT = PromptTemplate(
    name="catalogue_transcription",
    system_prompt=(
        "You are transcribing structured historical material from an image. Preserve "
        "rows, headings, numbering, field boundaries, and list structure. Do not "
        "collapse entries into prose or invent missing structure."
    ),
    user_prompt_template=(
        "Transcribe page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Return only the transcription."
    ),
)

_CUSTOM_TRANSCRIPTION_PROMPT = PromptTemplate(
    name="custom_transcription",
    system_prompt=(
        "You are transcribing historical source material from an image. Preserve "
        "historically meaningful wording and structure, and follow the additional "
        "user instructions closely. Do not add information that is not supported "
        "by the source."
    ),
    user_prompt_template=(
        "Transcribe page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Additional user instructions:\n"
        "{custom_instructions}\n"
        "\n"
        "Return only the transcription."
    ),
)

_HANDWRITTEN_CORRECTION_PROMPT = PromptTemplate(
    name="handwritten_correction",
    system_prompt=(
        "You are correcting an existing transcription against the page image. Make "
        "only corrections supported by the image. Preserve original spelling, "
        "abbreviations, punctuation, capitalization, line breaks, page numbers, "
        "and meaningful marginalia. Do not rewrite for style."
    ),
    user_prompt_template=(
        "Correct the existing transcription for page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Existing transcription:\n"
        "{source_text}\n"
        "\n"
        "Return only the corrected transcription."
    ),
)

_PRINTED_CORRECTION_PROMPT = PromptTemplate(
    name="printed_correction",
    system_prompt=(
        "You are correcting an existing transcription against the page image. Fix "
        "recognition errors only where the image supports the correction. Preserve "
        "original wording and meaningful layout cues. Do not rewrite for style or "
        "modernize the text."
    ),
    user_prompt_template=(
        "Correct the existing transcription for page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Existing transcription:\n"
        "{source_text}\n"
        "\n"
        "Return only the corrected transcription."
    ),
)

_CATALOGUE_CORRECTION_PROMPT = PromptTemplate(
    name="catalogue_correction",
    system_prompt=(
        "You are correcting structured historical transcription against the page "
        "image. Preserve rows, headings, numbering, field boundaries, and list "
        "structure. Correct only what the image supports."
    ),
    user_prompt_template=(
        "Correct the existing transcription for page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Existing transcription:\n"
        "{source_text}\n"
        "\n"
        "Return only the corrected transcription."
    ),
)

_CUSTOM_CORRECTION_PROMPT = PromptTemplate(
    name="custom_correction",
    system_prompt=(
        "You are correcting an existing transcription against the page image. Follow "
        "the additional user instructions closely while preserving historically "
        "meaningful wording and structure. Make only corrections supported by the "
        "image."
    ),
    user_prompt_template=(
        "Correct the existing transcription for page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "\n"
        "Structure rules:\n"
        "{structure_rules}\n"
        "\n"
        "Additional user instructions:\n"
        "{custom_instructions}\n"
        "\n"
        "Existing transcription:\n"
        "{source_text}\n"
        "\n"
        "Return only the corrected transcription."
    ),
)

_SCHOLARLY_TRANSLATION_PROMPT = PromptTemplate(
    name="scholarly_translation",
    system_prompt=(
        "You are translating historical source text for scholarly research. Translate "
        "faithfully into the target language while preserving names, dates, uncertain "
        "readings, page markers, headings, and meaningful structure. Do not summarize "
        "or add information not present in the source."
    ),
    user_prompt_template=(
        "Translate page {page_sequence}.\n"
        "Source genre: {source_genre}.\n"
        "Input stage: {source_stage}.\n"
        "\n"
        "Translate from the source language to English.\n"
        "Preserve proper names, place names, dates, page markers, uncertain "
        "readings, marginalia markers, and paragraph structure. Translate meaning "
        "rather than word order, but do not modernize technical or historically "
        "significant terms unnecessarily.\n"
        "\n"
        "Source text:\n"
        "{source_text}\n"
        "\n"
        "Return only the translation."
    ),
)


_BUILTIN_PRESETS = {
    "Handwritten Transcription": TaskPreset(
        name="Handwritten Transcription",
        task_type=TASK_TRANSCRIBE,
        source_genre="handwritten text",
        prompt_template=_HANDWRITTEN_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=1,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
    ),
    "Printed Transcription": TaskPreset(
        name="Printed Transcription",
        task_type=TASK_TRANSCRIBE,
        source_genre="printed text",
        prompt_template=_PRINTED_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=1,
        preserve_line_breaks=True,
        preserve_marginalia=False,
        normalize_whitespace=False,
    ),
    "Structured / Catalogue Transcription": TaskPreset(
        name="Structured / Catalogue Transcription",
        task_type=TASK_TRANSCRIBE,
        source_genre="catalogue / structured listings",
        prompt_template=_CATALOGUE_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=1,
        preserve_line_breaks=True,
        preserve_marginalia=False,
        normalize_whitespace=False,
    ),
    "Custom Transcription": TaskPreset(
        name="Custom Transcription",
        task_type=TASK_TRANSCRIBE,
        source_genre="custom / other source",
        prompt_template=_CUSTOM_TRANSCRIPTION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=1,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
    ),
    "Handwritten Correction": TaskPreset(
        name="Handwritten Correction",
        task_type=TASK_CORRECT,
        source_genre="handwritten text",
        prompt_template=_HANDWRITTEN_CORRECTION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=2,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
    ),
    "Printed Correction": TaskPreset(
        name="Printed Correction",
        task_type=TASK_CORRECT,
        source_genre="printed text",
        prompt_template=_PRINTED_CORRECTION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=3,
        preserve_line_breaks=True,
        preserve_marginalia=False,
        normalize_whitespace=False,
    ),
    "Structured / Catalogue Correction": TaskPreset(
        name="Structured / Catalogue Correction",
        task_type=TASK_CORRECT,
        source_genre="catalogue / structured listings",
        prompt_template=_CATALOGUE_CORRECTION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=2,
        preserve_line_breaks=True,
        preserve_marginalia=False,
        normalize_whitespace=False,
    ),
    "Custom Correction": TaskPreset(
        name="Custom Correction",
        task_type=TASK_CORRECT,
        source_genre="custom / other source",
        prompt_template=_CUSTOM_CORRECTION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=2,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
    ),
    "Scholarly Translation to English": TaskPreset(
        name="Scholarly Translation to English",
        task_type=TASK_TRANSLATE,
        source_genre="general historical text",
        prompt_template=_SCHOLARLY_TRANSLATION_PROMPT,
        model_config=_TRANSCRIPTION_BASE_MODEL,
        batch_size=2,
        preserve_line_breaks=True,
        preserve_marginalia=True,
        normalize_whitespace=False,
        source_language="auto-detect",
        target_language="English",
        translation_rules="",
    ),
}


_TASK_DEFINITIONS = {
    TASK_TRANSCRIBE: _TRANSCRIPTION_DEFINITION,
    TASK_CORRECT: _CORRECTION_DEFINITION,
    TASK_TRANSLATE: _TRANSLATION_DEFINITION,
}


def get_task_definition(task_type: str) -> TaskDefinition:
    return _TASK_DEFINITIONS[task_type]


def get_builtin_preset(name: str) -> TaskPreset:
    return _BUILTIN_PRESETS[name]


def list_builtin_presets() -> list[TaskPreset]:
    return list(_BUILTIN_PRESETS.values())


def get_preset(name: str) -> TaskPreset:
    """Return a preset with any user prompt override applied."""
    user_preset = load_user_presets().get(name)
    if user_preset is not None:
        return user_preset.to_task_preset()

    preset = get_builtin_preset(name)
    override = load_preset_overrides().get(name)
    if override is None:
        return preset
    return replace(
        preset,
        source_genre=override.source_genre or preset.source_genre,
        prompt_template=replace(
            preset.prompt_template,
            system_prompt=override.system_prompt,
            user_prompt_template=override.user_prompt_template,
        ),
        batch_size=override.batch_size or preset.batch_size,
        preserve_line_breaks=(
            override.preserve_line_breaks
            if override.preserve_line_breaks is not None
            else preset.preserve_line_breaks
        ),
        preserve_marginalia=(
            override.preserve_marginalia
            if override.preserve_marginalia is not None
            else preset.preserve_marginalia
        ),
        normalize_whitespace=(
            override.normalize_whitespace
            if override.normalize_whitespace is not None
            else preset.normalize_whitespace
        ),
        response_prefix=override.response_prefix,
        source_language=override.source_language or preset.source_language,
        target_language=override.target_language or preset.target_language,
        translation_rules=(
            override.translation_rules
            if override.translation_rules is not None
            else preset.translation_rules
        ),
    )


def list_presets() -> list[TaskPreset]:
    """Return all presets with user overrides applied."""
    user_presets = load_user_presets()
    overrides = load_preset_overrides()
    presets: list[TaskPreset] = []
    for preset in _BUILTIN_PRESETS.values():
        override = overrides.get(preset.name)
        if override is None:
            presets.append(preset)
            continue
        presets.append(
            replace(
                preset,
                source_genre=override.source_genre or preset.source_genre,
                prompt_template=replace(
                    preset.prompt_template,
                    system_prompt=override.system_prompt,
                    user_prompt_template=override.user_prompt_template,
                ),
                batch_size=override.batch_size or preset.batch_size,
                preserve_line_breaks=(
                    override.preserve_line_breaks
                    if override.preserve_line_breaks is not None
                    else preset.preserve_line_breaks
                ),
                preserve_marginalia=(
                    override.preserve_marginalia
                    if override.preserve_marginalia is not None
                    else preset.preserve_marginalia
                ),
                normalize_whitespace=(
                    override.normalize_whitespace
                    if override.normalize_whitespace is not None
                    else preset.normalize_whitespace
                ),
                response_prefix=override.response_prefix,
                source_language=override.source_language or preset.source_language,
                target_language=override.target_language or preset.target_language,
                translation_rules=(
                    override.translation_rules
                    if override.translation_rules is not None
                    else preset.translation_rules
                ),
            )
        )
    for user_preset in user_presets.values():
        presets.append(user_preset.to_task_preset())
    return presets
