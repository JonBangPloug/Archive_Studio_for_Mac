"""Provider payload and extraction tests without live network calls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from archivestudio.core.ai.anthropic_provider import AnthropicProvider
from archivestudio.core.ai.base import (
    CorrectionRequest,
    PromptMessages,
    TranscriptionRequest,
)
from archivestudio.core.ai.google_provider import GoogleGenAIProvider
from archivestudio.core.ai.openai_provider import OpenAIProvider
from archivestudio.core.tasks.types import ModelConfig


def _build_image(path: Path) -> Path:
    Image.new("RGB", (32, 24), color="maroon").save(path)
    return path


def test_openai_provider_builds_multimodal_request(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=" transcribed text ", output=[])

    client = SimpleNamespace(responses=FakeResponsesAPI())
    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4.1-mini", client=client)
    image_path = _build_image(tmp_path / "page.png")
    request = TranscriptionRequest(
        page_id="page-1",
        page_sequence=1,
        image_path=image_path,
        source_type="printed",
        prompt=PromptMessages(system="system prompt", user="user prompt"),
    )

    results = provider.transcribe_pages(
        [request],
        model_config=ModelConfig(provider="openai", model_id="unset", temperature=0.2),
    )

    assert results[0].transcription == "transcribed text"
    assert captured["instructions"] == "system prompt"
    assert captured["model"] == "gpt-4.1-mini"
    assert captured["temperature"] == 0.2
    input_payload = captured["input"][0]["content"]  # type: ignore[index]
    assert input_payload[0]["type"] == "input_text"
    assert input_payload[0]["text"] == "user prompt"
    assert input_payload[1]["type"] == "input_image"
    assert input_payload[1]["image_url"].startswith("data:image/png;base64,")


def test_openai_provider_omits_temperature_when_unset(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=" transcribed text ", output=[])

    client = SimpleNamespace(responses=FakeResponsesAPI())
    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4.1-mini", client=client)
    image_path = _build_image(tmp_path / "page.png")
    request = TranscriptionRequest(
        page_id="page-1",
        page_sequence=1,
        image_path=image_path,
        source_type="printed",
        prompt=PromptMessages(system="system prompt", user="user prompt"),
    )

    provider.transcribe_pages(
        [request],
        model_config=ModelConfig(provider="openai", model_id="unset", temperature=None),
    )

    assert "temperature" not in captured


def test_openai_provider_batches_multiple_transcription_pages(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=(
                    '{"pages":['
                    '{"page_id":"page-1","page_sequence":1,"transcription":"first page"},'
                    '{"page_id":"page-2","page_sequence":2,"transcription":"second page"}'
                    "]}"
                ),
                output=[],
            )

    client = SimpleNamespace(responses=FakeResponsesAPI())
    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4.1-mini", client=client)
    image_one = _build_image(tmp_path / "page1.png")
    image_two = _build_image(tmp_path / "page2.png")
    requests = [
        TranscriptionRequest(
            page_id="page-1",
            page_sequence=1,
            image_path=image_one,
            source_type="printed",
            prompt=PromptMessages(system="shared system", user="first user prompt"),
        ),
        TranscriptionRequest(
            page_id="page-2",
            page_sequence=2,
            image_path=image_two,
            source_type="printed",
            prompt=PromptMessages(system="shared system", user="second user prompt"),
        ),
    ]

    results = provider.transcribe_pages(
        requests,
        model_config=ModelConfig(provider="openai", model_id="unset", temperature=0.2),
    )

    assert [result.transcription for result in results] == ["first page", "second page"]
    input_payload = captured["input"][0]["content"]  # type: ignore[index]
    assert input_payload[0]["type"] == "input_text"
    assert input_payload[1]["type"] == "input_image"
    assert input_payload[2]["type"] == "input_image"
    assert "exact page_id values" in input_payload[0]["text"]


def test_openai_provider_omits_temperature_for_models_that_do_not_support_it(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=" text ", output=[])

    client = SimpleNamespace(responses=FakeResponsesAPI())
    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-5-mini", client=client)
    image_path = _build_image(tmp_path / "page.png")
    request = TranscriptionRequest(
        page_id="page-1",
        page_sequence=1,
        image_path=image_path,
        source_type="printed",
        prompt=PromptMessages(system="system", user="user"),
    )

    provider.transcribe_pages(
        [request],
        model_config=ModelConfig(provider="openai", model_id="unset", temperature=0.8),
    )

    assert captured["model"] == "gpt-5-mini"
    assert "temperature" not in captured


def test_openai_provider_retries_without_temperature_when_model_rejects_it(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponsesAPI:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if "temperature" in kwargs:
                raise ValueError("Unsupported parameter: 'temperature' is not supported with this model.")
            return SimpleNamespace(output_text=" recovered text ", output=[])

    client = SimpleNamespace(responses=FakeResponsesAPI())
    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4.1-mini", client=client)
    image_path = _build_image(tmp_path / "page.png")
    request = TranscriptionRequest(
        page_id="page-1",
        page_sequence=1,
        image_path=image_path,
        source_type="printed",
        prompt=PromptMessages(system="system", user="user"),
    )

    results = provider.transcribe_pages(
        [request],
        model_config=ModelConfig(provider="openai", model_id="unset", temperature=0.8),
    )

    assert results[0].transcription == "recovered text"
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_anthropic_provider_builds_vision_message(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeMessagesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=" corrected text ")]
            )

    client = SimpleNamespace(messages=FakeMessagesAPI())
    provider = AnthropicProvider(api_key="sk-test", model_id="claude-test", client=client)
    image_path = _build_image(tmp_path / "page.png")
    request = CorrectionRequest(
        page_id="page-1",
        page_sequence=1,
        image_path=image_path,
        source_text="raw text",
        source_text_version_id="version-1",
        source_type="handwritten",
        prompt=PromptMessages(system="system prompt", user="user prompt"),
    )

    results = provider.correct_pages(
        [request],
        model_config=ModelConfig(provider="anthropic", model_id="unset", temperature=0.1),
    )

    assert results[0].corrected_text == "corrected text"
    assert captured["system"] == "system prompt"
    assert captured["model"] == "claude-test"
    assert captured["temperature"] == 0.1
    content = captured["messages"][0]["content"]  # type: ignore[index]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"]
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "user prompt"


def test_anthropic_provider_batches_multiple_transcription_pages(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeMessagesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=(
                            '{"pages":['
                            '{"page_id":"page-1","page_sequence":1,"transcription":"alpha"},'
                            '{"page_id":"page-2","page_sequence":2,"transcription":"beta"}'
                            "]}"
                        ),
                    )
                ]
            )

    client = SimpleNamespace(messages=FakeMessagesAPI())
    provider = AnthropicProvider(api_key="sk-test", model_id="claude-test", client=client)
    requests = [
        TranscriptionRequest(
            page_id="page-1",
            page_sequence=1,
            image_path=_build_image(tmp_path / "page1.png"),
            source_type="handwritten",
            prompt=PromptMessages(system="shared system", user="prompt one"),
        ),
        TranscriptionRequest(
            page_id="page-2",
            page_sequence=2,
            image_path=_build_image(tmp_path / "page2.png"),
            source_type="handwritten",
            prompt=PromptMessages(system="shared system", user="prompt two"),
        ),
    ]

    results = provider.transcribe_pages(
        requests,
        model_config=ModelConfig(provider="anthropic", model_id="unset", temperature=0.1),
    )

    assert [result.transcription for result in results] == ["alpha", "beta"]
    content = captured["messages"][0]["content"]  # type: ignore[index]
    assert content[0]["type"] == "image"
    assert content[1]["type"] == "image"
    assert content[2]["type"] == "text"
    assert "Page-specific instructions" in content[2]["text"]


def test_google_provider_batches_multiple_transcription_pages(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakePart:
        @staticmethod
        def from_text(*, text: str):
            return {"kind": "text", "text": text}

        @staticmethod
        def from_bytes(*, data: bytes, mime_type: str):
            return {"kind": "bytes", "data": data, "mime_type": mime_type}

    fake_types = SimpleNamespace(
        Part=FakePart,
        GenerateContentConfig=FakeGenerateContentConfig,
    )

    class FakeModelsAPI:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text=(
                    '{"pages":['
                    '{"page_id":"page-1","page_sequence":1,"transcription":"gamma"},'
                    '{"page_id":"page-2","page_sequence":2,"transcription":"delta"}'
                    "]}"
                )
            )

    client = SimpleNamespace(models=FakeModelsAPI())
    provider = GoogleGenAIProvider(
        api_key="sk-test",
        model_id="gemini-test",
        client=client,
        types_module=fake_types,
    )
    requests = [
        TranscriptionRequest(
            page_id="page-1",
            page_sequence=1,
            image_path=_build_image(tmp_path / "page1.png"),
            source_type="printed",
            prompt=PromptMessages(system="shared system", user="prompt one"),
        ),
        TranscriptionRequest(
            page_id="page-2",
            page_sequence=2,
            image_path=_build_image(tmp_path / "page2.png"),
            source_type="printed",
            prompt=PromptMessages(system="shared system", user="prompt two"),
        ),
    ]

    results = provider.transcribe_pages(
        requests,
        model_config=ModelConfig(provider="google", model_id="unset", temperature=0.3),
    )

    assert [result.transcription for result in results] == ["gamma", "delta"]
    assert captured["contents"][0]["kind"] == "text"
    assert captured["contents"][1]["kind"] == "bytes"
    assert captured["contents"][2]["kind"] == "bytes"
    assert "Page-specific instructions" in captured["contents"][0]["text"]
