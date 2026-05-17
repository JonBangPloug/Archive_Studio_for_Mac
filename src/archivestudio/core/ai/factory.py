"""Provider selection based on user settings."""

from __future__ import annotations

from dataclasses import dataclass

from archivestudio.core.ai.base import AIProvider
from archivestudio.core.ai.demo import DemoAIProvider
from archivestudio.core.ai.openai_provider import OpenAIProvider
from archivestudio.core.ai.anthropic_provider import AnthropicProvider
from archivestudio.core.ai.google_provider import GoogleGenAIProvider
from archivestudio.core.config.settings import AppSettings, ProviderSettings
from archivestudio.core.tasks.types import ModelConfig


@dataclass(frozen=True)
class ProviderSelection:
    provider: AIProvider
    requested_provider: str
    effective_provider: str
    message: str | None = None

    @property
    def used_fallback(self) -> bool:
        return self.message is not None or self.requested_provider != self.effective_provider


def create_provider_from_settings(
    settings: AppSettings,
    *,
    model_config: ModelConfig | None = None,
) -> ProviderSelection:
    """Create the configured provider or a clearly explained demo fallback."""
    requested = _requested_provider(settings, model_config)

    if requested == "demo":
        return _demo_fallback(
            requested=requested,
            reason=(
                "No real LLM is configured yet. Open Settings > Model, enable a "
                "provider, enter its API key, and choose it as the LLM used for tasks."
            ),
        )

    provider_settings = _provider_settings_for_name(settings, requested)
    if provider_settings is None:
        return _demo_fallback(
            requested=requested,
            reason=f"Unknown provider {requested!r} in settings.toml.",
        )
    if not provider_settings.enabled:
        return _demo_fallback(
            requested=requested,
            reason=f"Provider {requested!r} is disabled in settings.toml.",
        )
    if not provider_settings.api_key.strip():
        credential_note = (
            f" {provider_settings.credential_error}"
            if provider_settings.credential_error
            else ""
        )
        return _demo_fallback(
            requested=requested,
            reason=(
                f"Provider {requested!r} is enabled but has no API key configured."
                f"{credential_note}"
            ),
        )

    try:
        provider = _build_provider(requested, provider_settings, model_config=model_config)
    except Exception as exc:  # pragma: no cover - exercised via monkeypatched tests
        return _demo_fallback(
            requested=requested,
            reason=f"Could not initialize provider {requested!r}: {exc}",
        )

    return ProviderSelection(
        provider=provider,
        requested_provider=requested,
        effective_provider=provider.provider_name,
        message=None,
    )


def _provider_settings_for_name(settings: AppSettings, name: str) -> ProviderSettings | None:
    if name == "openai":
        return settings.openai
    if name == "anthropic":
        return settings.anthropic
    if name == "google":
        return settings.google
    return None


def _requested_provider(settings: AppSettings, model_config: ModelConfig | None) -> str:
    configured = settings.default_provider.strip().lower() or "demo"
    if model_config is None:
        return configured
    preset_provider = model_config.provider.strip().lower()
    if preset_provider and preset_provider != "configurable":
        return preset_provider
    return configured


def _build_provider(
    name: str,
    provider_settings: ProviderSettings,
    *,
    model_config: ModelConfig | None = None,
) -> AIProvider:
    model_tier = getattr(model_config, "model_tier", "strong") if model_config is not None else "strong"
    configured_model_id = getattr(model_config, "model_id", "") if model_config is not None else ""
    model_id = (
        configured_model_id
        if configured_model_id and configured_model_id != "unset"
        else provider_settings.model_for_tier(model_tier)
    )
    model_slots = {
        "fast": provider_settings.fast_model,
        "strong": provider_settings.strong_model,
    }
    if name == "openai":
        return OpenAIProvider(
            api_key=provider_settings.api_key,
            model_id=model_id,
            model_slots=model_slots,
        )
    if name == "anthropic":
        return AnthropicProvider(
            api_key=provider_settings.api_key,
            model_id=model_id,
            model_slots=model_slots,
        )
    if name == "google":
        return GoogleGenAIProvider(
            api_key=provider_settings.api_key,
            model_id=model_id,
            model_slots=model_slots,
        )
    raise ValueError(f"Unsupported provider: {name}")


def _demo_fallback(*, requested: str, reason: str) -> ProviderSelection:
    provider = DemoAIProvider()
    return ProviderSelection(
        provider=provider,
        requested_provider=requested,
        effective_provider=provider.provider_name,
        message=reason,
    )
