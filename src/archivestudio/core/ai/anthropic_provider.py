"""Anthropic-backed OCR/HTR provider."""

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
    image_base64_payload,
    parse_batched_transcription_response,
)


_REQUEST_TIMEOUT_SECONDS = 120.0


class AnthropicProvider(AIProvider):
    """Provider adapter using the Anthropic Messages API."""

    provider_name = "anthropic"
    supports_batching = True

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        client: Any | None = None,
        model_slots: dict[str, str] | None = None,
    ) -> None:
        self.model_id = model_id
        self._model_slots = model_slots or {}
        if client is not None:
            self._client = client
            return

        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=_REQUEST_TIMEOUT_SECONDS)

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
        temperature: float | None,
    ) -> tuple[str, str | None]:
        resolved_image_paths = list(image_paths or [])
        if image_path is not None:
            resolved_image_paths.append(image_path)
        content: list[dict[str, Any]] = []
        for path in resolved_image_paths:
            media_type, base64_data = image_base64_payload(path)
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_data,
                    },
                }
            )
        content.append({"type": "text", "text": user})

        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": 4096,
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        response = self._client.messages.create(**payload)
        text = self._extract_text(response)
        return text, text

    def _resolve_model_id(self, model_config) -> str:
        configured = getattr(model_config, "model_id", "")
        if configured and configured != "unset":
            return configured
        tier = getattr(model_config, "model_tier", "strong")
        if tier in self._model_slots and self._model_slots[tier]:
            return self._model_slots[tier]
        return self.model_id

    def _extract_text(self, response: Any) -> str:
        text_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
        if text_parts:
            return "\n".join(text_parts).strip()
        raise ValueError("Anthropic response did not contain any text output")
