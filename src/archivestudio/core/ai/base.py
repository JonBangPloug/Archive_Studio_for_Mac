"""Provider-facing data contracts.

The first implemented task is transcription, so the provider surface is kept
focused on image + prompt input and page-keyed text output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence


if TYPE_CHECKING:
    from archivestudio.core.tasks.types import ModelConfig


@dataclass(frozen=True)
class PromptMessages:
    """Rendered prompt messages for one page request."""

    system: str
    user: str


@dataclass(frozen=True)
class TranscriptionRequest:
    """One page sent to a provider for OCR/HTR."""

    page_id: str
    page_sequence: int
    image_path: Path
    source_type: str | None
    prompt: PromptMessages


@dataclass(frozen=True)
class TranscriptionResult:
    """One transcribed page returned from a provider."""

    page_id: str
    transcription: str
    raw_response: str | None = None


@dataclass(frozen=True)
class CorrectionRequest:
    """One page sent to a provider for correction against an existing text."""

    page_id: str
    page_sequence: int
    image_path: Path
    source_text: str
    source_text_version_id: str
    source_type: str | None
    prompt: PromptMessages


@dataclass(frozen=True)
class CorrectionResult:
    """One corrected page returned from a provider."""

    page_id: str
    corrected_text: str
    raw_response: str | None = None


@dataclass(frozen=True)
class TranslationRequest:
    """One page text sent to a provider for translation."""

    page_id: str
    page_sequence: int
    source_text: str
    source_text_stage: str
    source_text_version_id: str
    source_type: str | None
    source_language: str
    target_language: str
    prompt: PromptMessages


@dataclass(frozen=True)
class TranslationResult:
    """One translated page returned from a provider."""

    page_id: str
    translated_text: str
    raw_response: str | None = None


class AIProvider(ABC):
    """Abstract base class for provider implementations."""

    provider_name = "unknown"
    model_id = "unknown"
    supports_batching = True

    @abstractmethod
    def transcribe_pages(
        self,
        requests: Sequence[TranscriptionRequest],
        *,
        model_config: "ModelConfig",
    ) -> Sequence[TranscriptionResult]:
        """Return one transcription result per requested page."""

    def correct_pages(
        self,
        requests: Sequence[CorrectionRequest],
        *,
        model_config: "ModelConfig",
    ) -> Sequence[CorrectionResult]:
        """Return one corrected text result per requested page."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement correction")

    def translate_pages(
        self,
        requests: Sequence[TranslationRequest],
        *,
        model_config: "ModelConfig",
    ) -> Sequence[TranslationResult]:
        """Return one translated text result per requested page."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement translation")
