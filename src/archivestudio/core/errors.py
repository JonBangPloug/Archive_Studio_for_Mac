"""User-facing error summaries and secret redaction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import traceback


_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_ -]?key|authorization|bearer|token)(['\"=: ]+)([^\s,'\"]{8,})"),
]


@dataclass(frozen=True)
class ErrorReport:
    """A safe, user-readable explanation plus technical detail for logs."""

    category: str
    summary: str
    suggestion: str
    technical_detail: str


def redact_secrets(value: object) -> str:
    """Return ``value`` as text with common API key shapes removed."""
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1\2[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text


def classify_exception(error: BaseException) -> ErrorReport:
    """Classify common user-actionable failures without provider-specific imports."""
    message = redact_secrets(error)
    lowered = message.lower()
    class_name = error.__class__.__name__.lower()

    if class_name == "taskcancelled" or "task cancelled by user" in lowered:
        return _report(
            error,
            category="Task cancelled",
            summary="Task cancelled by user.",
            suggestion="Already completed pages were kept. Run the task again to continue.",
        )

    if class_name == "prompttemplatevalidationerror" or _contains_any(
        lowered,
        "unsupported placeholder",
        "missing required placeholder",
        "unmatched braces",
        "replacement index",
        "keyerror",
    ):
        return _report(
            error,
            category="Prompt/template problem",
            summary="The task prompt could not be rendered safely.",
            suggestion="Open Settings > Prompts and check the placeholders in the preset.",
        )

    if _contains_any(lowered, "unsupported parameter", "unsupported value", "invalid_request_error"):
        return _report(
            error,
            category="Provider request setting",
            summary="The selected AI model rejected one of the request settings.",
            suggestion=(
                "Choose a different model in Settings > Model, or remove unsupported "
                "optional settings from the preset."
            ),
        )

    if _contains_any(
        lowered,
        "invalid api key",
        "incorrect api key",
        "unauthorized",
        "authentication",
        "permission denied",
        "401",
    ) or _contains_any(class_name, "auth", "permissiondenied"):
        return _report(
            error,
            category="API key / authentication",
            summary="The selected AI service rejected the API key or credentials.",
            suggestion="Open Settings > Model and re-enter the provider API key.",
        )

    if _contains_any(lowered, "billing", "quota", "insufficient_quota", "credit", "payment"):
        return _report(
            error,
            category="Billing or quota",
            summary="The AI service reported a billing, credit, or quota problem.",
            suggestion="Check the provider account billing/quota page, then try again.",
        )

    if _contains_any(lowered, "rate limit", "ratelimit", "too many requests", "429"):
        return _report(
            error,
            category="Rate limit",
            summary="The AI service is rate limiting the request.",
            suggestion="Wait a little, reduce pages per API call, or use a model/account with higher limits.",
        )

    if _contains_any(
        lowered,
        "timeout",
        "timed out",
        "connection",
        "network",
        "dns",
        "temporary failure",
        "name resolution",
        "ssl",
    ) or _contains_any(class_name, "timeout", "connection", "network"):
        return _report(
            error,
            category="Network problem",
            summary="ArchiveStudio could not reach the AI service reliably.",
            suggestion="Check your internet connection or provider status, then try again.",
        )

    if _contains_any(lowered, "no pages matched", "no preset", "unknown provider", "disabled"):
        if "no pages matched the translation request" in lowered:
            return _report(
                error,
                category="No translatable text",
                summary=(
                    "No selected pages have text to translate."
                ),
                suggestion=(
                    "Run Transcribe first, or select pages that already have Original, "
                    "or Corrected text. Translation will write to the separate "
                    "Translated stage and will not overwrite those source stages."
                ),
            )
        return _report(
            error,
            category="Configuration problem",
            summary=message or "The task could not start because something is not configured.",
            suggestion="Check the selected project, preset, and model settings.",
        )

    return _report(
        error,
        category="Internal program error",
        summary="ArchiveStudio hit an unexpected program error.",
        suggestion="Open Help > Activity Log for details that can help debug the issue.",
    )


def technical_traceback(error: BaseException) -> str:
    """Return a redacted traceback for persistent logs or debug views."""
    return redact_secrets("".join(traceback.format_exception(error)))


def _report(
    error: BaseException,
    *,
    category: str,
    summary: str,
    suggestion: str,
) -> ErrorReport:
    return ErrorReport(
        category=category,
        summary=redact_secrets(summary),
        suggestion=redact_secrets(suggestion),
        technical_detail=technical_traceback(error),
    )


def _contains_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)
