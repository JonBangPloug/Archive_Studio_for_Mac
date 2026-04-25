"""Google Gemini-backed OCR/HTR provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from archivestudio.core.ai.base import (
    AIProvider,
    CorrectionRequest,
    CorrectionResult,
    TranslationRequest,
    TranslationResult,
    TranscriptionRequest,
    TranscriptionResult,
)
from archivestudio.core.ai.common import (
    build_batched_transcription_prompt,
    guess_image_mime_type,
    parse_batched_transcription_response,
    read_image_bytes,
)


class GoogleGenAIProvider(AIProvider):
    """Provider adapter using the Google Gen AI SDK."""

    provider_name = "google"
    supports_batching = True

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        client: Any | None = None,
        types_module: Any | None = None,
    ) -> None:
        self.model_id = model_id
        self._types = types_module
        if client is not None:
            self._client = client
            return

        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=api_key)
        self._types = types

    def transcribe_pages(
        self,
        requests: Sequence[TranscriptionRequest],
        *,
        model_config,
    ) -> Sequence[TranscriptionResult]:
        if len(requests) > 1:
            return self._transcribe_batched(requests, model_config=model_config)
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription=text,
                raw_response=raw,
            )
            for request, (text, raw) in (
                (
                    request,
                    self._request_text(
                        system=request.prompt.system,
                        user=request.prompt.user,
                        image_path=request.image_path,
                        model_id=self._resolve_model_id(model_config),
                        temperature=model_config.temperature,
                    ),
                )
                for request in requests
            )
        ]

    def _transcribe_batched(
        self,
        requests: Sequence[TranscriptionRequest],
        *,
        model_config,
    ) -> Sequence[TranscriptionResult]:
        prompt = build_batched_transcription_prompt(requests)
        text, raw = self._request_text(
            system=prompt.system,
            user=prompt.user,
            image_paths=[request.image_path for request in requests],
            model_id=self._resolve_model_id(model_config),
            temperature=model_config.temperature,
        )
        transcriptions = parse_batched_transcription_response(
            text,
            expected_page_ids=[request.page_id for request in requests],
        )
        return [
            TranscriptionResult(
                page_id=request.page_id,
                transcription=transcriptions[request.page_id],
                raw_response=raw,
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
                corrected_text=text,
                raw_response=raw,
            )
            for request, (text, raw) in (
                (
                    request,
                    self._request_text(
                        system=request.prompt.system,
                        user=request.prompt.user,
                        image_path=request.image_path,
                        model_id=self._resolve_model_id(model_config),
                        temperature=model_config.temperature,
                    ),
                )
                for request in requests
            )
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
                translated_text=text,
                raw_response=raw,
            )
            for request, (text, raw) in (
                (
                    request,
                    self._request_text(
                        system=request.prompt.system,
                        user=request.prompt.user,
                        model_id=self._resolve_model_id(model_config),
                        temperature=model_config.temperature,
                    ),
                )
                for request in requests
            )
        ]

    def _request_text(
        self,
        *,
        system: str,
        user: str,
        image_path=None,
        image_paths: Sequence[Any] | None = None,
        model_id: str,
        temperature: float,
    ) -> tuple[str, str | None]:
        types = self._load_types()
        resolved_image_paths = list(image_paths or [])
        if image_path is not None:
            resolved_image_paths.append(image_path)
        contents = [types.Part.from_text(text=user)]
        for path in resolved_image_paths:
            contents.append(
                types.Part.from_bytes(
                    data=read_image_bytes(path),
                    mime_type=guess_image_mime_type(path),
                )
            )
        response = self._client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
            ),
        )
        text = self._extract_text(response)
        return text, getattr(response, "text", None)

    def _load_types(self):
        if self._types is not None:
            return self._types
        from google.genai import types

        self._types = types
        return types

    def _resolve_model_id(self, model_config) -> str:
        configured = getattr(model_config, "model_id", "")
        if configured and configured != "unset":
            return configured
        return self.model_id

    def _extract_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        raise ValueError("Google response did not contain any text output")
