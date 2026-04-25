"""Provider selection based on user settings."""

from __future__ import annotations

from dataclasses import dataclass

from archivestudio.core.ai.base import AIProvider
from archivestudio.core.ai.demo import DemoAIProvider
from archivestudio.core.ai.openai_provider import OpenAIProvider
from archivestudio.core.ai.anthropic_provider import AnthropicProvider
from archivestudio.core.ai.google_provider import GoogleGenAIProvider
from archivestudio.core.config.settings import AppSettings, ProviderSettings


@dataclass(frozen=True)
class ProviderSelection:
    provider: AIProvider
    requested_provider: str
    effective_provider: str
    message: str | None = None

    @property
    def used_fallback(self) -> bool:
        return self.requested_provider != self.effective_provider


def create_provider_from_settings(settings: AppSettings) -> ProviderSelection:
    """Create the configured provider or a clearly explained demo fallback."""
    requested = settings.default_provider.strip().lower() or "demo"

    if requested == "demo":
        provider = DemoAIProvider()
        return ProviderSelection(
            provider=provider,
            requested_provider="demo",
            effective_provider=provider.provider_name,
            message=None,
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
        provider = _build_provider(requested, provider_settings)
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


def _build_provider(name: str, provider_settings: ProviderSettings) -> AIProvider:
    if name == "openai":
        return OpenAIProvider(
            api_key=provider_settings.api_key,
            model_id=provider_settings.model,
        )
    if name == "anthropic":
        return AnthropicProvider(
            api_key=provider_settings.api_key,
            model_id=provider_settings.model,
        )
    if name == "google":
        return GoogleGenAIProvider(
            api_key=provider_settings.api_key,
            model_id=provider_settings.model,
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
