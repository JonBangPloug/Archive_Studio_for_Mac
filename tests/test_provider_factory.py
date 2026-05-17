"""Provider selection tests."""

from __future__ import annotations

from dataclasses import replace

from archivestudio.core.ai.demo import DemoAIProvider
from archivestudio.core.ai.factory import create_provider_from_settings
from archivestudio.core.config.settings import AppSettings, ProviderSettings
from archivestudio.core.tasks.types import ModelConfig


def _settings(*, default_provider: str = "demo") -> AppSettings:
    disabled = ProviderSettings(enabled=False, api_key="", model="unset")
    return AppSettings(
        openai=disabled,
        anthropic=disabled,
        google=disabled,
        default_provider=default_provider,
        auto_open_last_work=False,
        path=None,  # type: ignore[arg-type]
    )


def test_provider_factory_flags_demo_as_not_configured_for_task_use() -> None:
    selection = create_provider_from_settings(_settings(default_provider="demo"))

    assert isinstance(selection.provider, DemoAIProvider)
    assert selection.requested_provider == "demo"
    assert selection.effective_provider == "demo"
    assert selection.used_fallback is True
    assert "No real LLM" in (selection.message or "")


def test_provider_factory_falls_back_when_provider_is_disabled() -> None:
    settings = replace(
        _settings(default_provider="openai"),
        openai=ProviderSettings(enabled=False, api_key="sk-test", model="gpt-test"),
    )

    selection = create_provider_from_settings(settings)

    assert isinstance(selection.provider, DemoAIProvider)
    assert selection.used_fallback is True
    assert "disabled" in (selection.message or "")


def test_provider_factory_builds_configured_provider(monkeypatch) -> None:
    class FakeProvider:
        provider_name = "openai"
        model_id = "gpt-test"

        def __init__(self, *, api_key: str, model_id: str, model_slots=None) -> None:
            self.api_key = api_key
            self.model_id = model_id
            self.model_slots = model_slots or {}

    monkeypatch.setattr("archivestudio.core.ai.factory.OpenAIProvider", FakeProvider)

    settings = replace(
        _settings(default_provider="openai"),
        openai=ProviderSettings(enabled=True, api_key="sk-live", model="gpt-test"),
    )

    selection = create_provider_from_settings(settings)

    assert selection.used_fallback is False
    assert selection.effective_provider == "openai"
    assert selection.provider.api_key == "sk-live"
    assert selection.provider.model_id == "gpt-test"


def test_provider_factory_uses_fast_and_strong_model_tiers(monkeypatch) -> None:
    class FakeProvider:
        provider_name = "openai"

        def __init__(self, *, api_key: str, model_id: str, model_slots=None) -> None:
            self.api_key = api_key
            self.model_id = model_id
            self.model_slots = model_slots or {}

    monkeypatch.setattr("archivestudio.core.ai.factory.OpenAIProvider", FakeProvider)

    settings = replace(
        _settings(default_provider="openai"),
        openai=ProviderSettings(
            enabled=True,
            api_key="sk-live",
            model="gpt-strong",
            fast_model="gpt-fast",
            strong_model="gpt-strong",
        ),
    )

    fast_selection = create_provider_from_settings(
        settings,
        model_config=ModelConfig(
            provider="configurable",
            model_id="unset",
            model_tier="fast",
        ),
    )
    strong_selection = create_provider_from_settings(
        settings,
        model_config=ModelConfig(
            provider="configurable",
            model_id="unset",
            model_tier="strong",
        ),
    )

    assert fast_selection.used_fallback is False
    assert fast_selection.provider.model_id == "gpt-fast"
    assert strong_selection.used_fallback is False
    assert strong_selection.provider.model_id == "gpt-strong"


def test_provider_factory_keeps_legacy_concrete_model_id(monkeypatch) -> None:
    class FakeProvider:
        provider_name = "openai"

        def __init__(self, *, api_key: str, model_id: str, model_slots=None) -> None:
            self.api_key = api_key
            self.model_id = model_id
            self.model_slots = model_slots or {}

    monkeypatch.setattr("archivestudio.core.ai.factory.OpenAIProvider", FakeProvider)

    settings = replace(
        _settings(default_provider="openai"),
        openai=ProviderSettings(
            enabled=True,
            api_key="sk-live",
            model="gpt-strong",
            fast_model="gpt-fast",
            strong_model="gpt-strong",
        ),
    )

    selection = create_provider_from_settings(
        settings,
        model_config=ModelConfig(
            provider="configurable",
            model_id="legacy-exact-model",
            model_tier="fast",
        ),
    )

    assert selection.used_fallback is False
    assert selection.provider.model_id == "legacy-exact-model"
