"""AI provider abstractions."""

from archivestudio.core.ai.anthropic_provider import AnthropicProvider
from archivestudio.core.ai.base import (
    AIProvider,
    CorrectionRequest,
    CorrectionResult,
    PromptMessages,
    TranslationRequest,
    TranslationResult,
    TranscriptionRequest,
    TranscriptionResult,
)
from archivestudio.core.ai.demo import DemoAIProvider
from archivestudio.core.ai.factory import ProviderSelection, create_provider_from_settings
from archivestudio.core.ai.google_provider import GoogleGenAIProvider
from archivestudio.core.ai.openai_provider import OpenAIProvider

__all__ = [
    "AIProvider",
    "AnthropicProvider",
    "CorrectionRequest",
    "CorrectionResult",
    "DemoAIProvider",
    "GoogleGenAIProvider",
    "OpenAIProvider",
    "PromptMessages",
    "ProviderSelection",
    "TranslationRequest",
    "TranslationResult",
    "TranscriptionRequest",
    "TranscriptionResult",
    "create_provider_from_settings",
]
