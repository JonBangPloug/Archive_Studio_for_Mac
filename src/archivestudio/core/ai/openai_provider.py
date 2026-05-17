"""OpenAI-backed OCR/HTR provider."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    image_data_url,
    parse_batched_transcription_response,
)


_REQUEST_TIMEOUT_SECONDS = 120.0
_TEMPERATURE_UNSUPPORTED_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


class OpenAIRequestParameterError(ValueError):
    """Raised when an OpenAI model rejects request parameters."""


class OpenAIProvider(AIProvider):
    """Provider adapter using the OpenAI Responses API."""

    provider_name = "openai"
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

        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=_REQUEST_TIMEOUT_SECONDS)

    def transcribe_pages(
        self,
        requests: Sequence[TranscriptionRequest],
        *,
        model_config,
    ) -> Sequence[TranscriptionResult]:
        if len(requests) > 1:
            return self._transcribe_batched(requests, model_config=model_config)
        return self._run_requests(
            requests,
            model_config=model_config,
            text_getter=lambda request: self._request_text(
                system=request.prompt.system,
                user=request.prompt.user,
                image_path=request.image_path,
                model_id=self._resolve_model_id(model_config),
                temperature=model_config.temperature,
            ),
            build_result=lambda request, text, raw: TranscriptionResult(
                page_id=request.page_id,
                transcription=text,
                raw_response=raw,
            ),
        )

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
        return self._run_requests(
            requests,
            model_config=model_config,
            text_getter=lambda request: self._request_text(
                system=request.prompt.system,
                user=request.prompt.user,
                image_path=request.image_path,
                model_id=self._resolve_model_id(model_config),
                temperature=model_config.temperature,
            ),
            build_result=lambda request, text, raw: CorrectionResult(
                page_id=request.page_id,
                corrected_text=text,
                raw_response=raw,
            ),
        )

    def translate_pages(
        self,
        requests: Sequence[TranslationRequest],
        *,
        model_config,
    ) -> Sequence[TranslationResult]:
        return self._run_requests(
            requests,
            model_config=model_config,
            text_getter=lambda request: self._request_text(
                system=request.prompt.system,
                user=request.prompt.user,
                model_id=self._resolve_model_id(model_config),
                temperature=model_config.temperature,
            ),
            build_result=lambda request, text, raw: TranslationResult(
                page_id=request.page_id,
                translated_text=text,
                raw_response=raw,
            ),
        )

    def _run_requests(
        self,
        requests: Sequence[Any],
        *,
        model_config,
        text_getter: Callable[[Any], tuple[str, str | None]],
        build_result: Callable[[Any, str, str | None], Any],
    ) -> list[Any]:
        results: list[Any] = []
        for request in requests:
            text, raw = text_getter(request)
            results.append(build_result(request, text, raw))
        return results

    def _request_text(
        self,
        *,
        system: str,
        user: str,
        image_path: Any | None = None,
        image_paths: Sequence[Any] | None = None,
        model_id: str,
        temperature: float | None,
    ) -> tuple[str, str | None]:
        resolved_image_paths = list(image_paths or [])
        if image_path is not None:
            resolved_image_paths.append(image_path)
        content = [{"type": "input_text", "text": user}]
        for path in resolved_image_paths:
            content.append(
                {
                    "type": "input_image",
                    "image_url": image_data_url(path),
                    "detail": "high",
                }
            )

        payload: dict[str, Any] = {
            "model": model_id,
            "instructions": system,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }
        if temperature is not None and _supports_temperature(model_id):
            payload["temperature"] = temperature

        response = self._create_response(payload)
        text = self._extract_text(response)
        return text, getattr(response, "output_text", None)

    def _resolve_model_id(self, model_config) -> str:
        configured = getattr(model_config, "model_id", "")
        if configured and configured != "unset":
            return configured
        tier = getattr(model_config, "model_tier", "strong")
        if tier in self._model_slots and self._model_slots[tier]:
            return self._model_slots[tier]
        return self.model_id

    def _create_response(self, payload: dict[str, Any]) -> Any:
        try:
            return self._client.responses.create(**payload)
        except Exception as exc:
            if "temperature" in payload and _is_unsupported_parameter_error(exc, "temperature"):
                retry_payload = dict(payload)
                retry_payload.pop("temperature", None)
                try:
                    return self._client.responses.create(**retry_payload)
                except Exception as retry_exc:
                    if _is_unsupported_parameter_error(retry_exc):
                        raise OpenAIRequestParameterError(
                            "OpenAI rejected a request parameter even after omitting temperature. "
                            "Choose another model or update the OpenAI model settings."
                        ) from retry_exc
                    raise
            if _is_unsupported_parameter_error(exc):
                raise OpenAIRequestParameterError(
                    "OpenAI rejected a request parameter for the selected model. "
                    "Choose another model or update the OpenAI model settings."
                ) from exc
            raise

    def _extract_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output_items = getattr(response, "output", None) or []
        text_parts: list[str] = []
        for item in output_items:
            for content in getattr(item, "content", []) or []:
                text_value = getattr(content, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    text_parts.append(text_value.strip())
        if text_parts:
            return "\n".join(text_parts).strip()
        raise ValueError("OpenAI response did not contain any text output")


def _supports_temperature(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    return not normalized.startswith(_TEMPERATURE_UNSUPPORTED_MODEL_PREFIXES)


def _is_unsupported_parameter_error(error: BaseException, parameter: str | None = None) -> bool:
    message = str(error).lower()
    if "unsupported parameter" not in message:
        return False
    if parameter is None:
        return True
    return parameter.lower() in message
