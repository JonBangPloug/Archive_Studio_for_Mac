"""Local demo provider for exercising the UI and task pipeline.

This provider is intentionally transparent: it does not perform real OCR/HTR.
Instead it returns clearly labelled placeholder content so the desktop app can
run end-to-end while the real provider layer is still being integrated.
"""

from __future__ import annotations

from typing import Sequence

from archivestudio.core.ai.base import (
    AIProvider,
    CorrectionRequest,
    CorrectionResult,
    TranslationRequest,
    TranslationResult,
    TranscriptionRequest,
    TranscriptionResult,
)


class DemoAIProvider(AIProvider):
    """Deterministic local provider used for UI integration and testing."""

    provider_name = "demo"
    model_id = "local-preview"
    supports_batching = True

    def transcribe_pages(
        self,
        requests: Sequence[TranscriptionRequest],
        *,
        model_config,
    ) -> Sequence[TranscriptionResult]:
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription="\n".join(
                    [
                        "[DEMO TRANSCRIPTION]",
                        f"Page {request.page_sequence}",
                        f"Image: {request.image_path.name}",
                        f"Source type: {request.source_type or 'unspecified'}",
                        "This is placeholder output from the local demo provider.",
                    ]
                ),
                raw_response="demo:transcribe",
            )
            for request in requests
        ]

    def correct_pages(
        self,
        requests: Sequence[CorrectionRequest],
        *,
        model_config,
    ) -> Sequence[CorrectionResult]:
        return [
            CorrectionResult(
                page_id=request.page_id,
                corrected_text="\n".join(
                    [
                        "[DEMO CORRECTION]",
                        f"Page {request.page_sequence}",
                        request.source_text.strip(),
                    ]
                ).strip(),
                raw_response="demo:correct",
            )
            for request in requests
        ]

    def translate_pages(
        self,
        requests: Sequence[TranslationRequest],
        *,
        model_config,
    ) -> Sequence[TranslationResult]:
        return [
            TranslationResult(
                page_id=request.page_id,
                translated_text="\n".join(
                    [
                        "[DEMO TRANSLATION]",
                        (
                            f"{request.source_language} -> "
                            f"{request.target_language}"
                        ),
                        f"Input stage: {request.source_text_stage}",
                        "",
                        request.source_text.strip(),
                    ]
                ).strip(),
                raw_response="demo:translate",
            )
            for request in requests
        ]
