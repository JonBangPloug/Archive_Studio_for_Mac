"""Shared helpers for provider-backed multimodal requests."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
import re
from typing import Sequence

from archivestudio.core.ai.base import PromptMessages, TranscriptionRequest


def read_image_bytes(path: Path) -> bytes:
    """Return raw bytes for an on-disk image."""
    return path.read_bytes()


def guess_image_mime_type(path: Path) -> str:
    """Best-effort image mime-type detection from filename."""
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type:
        return mime_type
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    if path.suffix.lower() == ".gif":
        return "image/gif"
    return "image/png"


def image_data_url(path: Path) -> str:
    """Return a base64 data URL suitable for OpenAI image input."""
    data = read_image_bytes(path)
    mime_type = guess_image_mime_type(path)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def image_base64_payload(path: Path) -> tuple[str, str]:
    """Return Anthropic-style image payload parts: (media_type, base64_data)."""
    data = read_image_bytes(path)
    mime_type = guess_image_mime_type(path)
    encoded = base64.b64encode(data).decode("ascii")
    return mime_type, encoded


def build_batched_transcription_prompt(
    requests: Sequence[TranscriptionRequest],
) -> PromptMessages:
    """Build one prompt asking for per-page JSON transcriptions."""
    if not requests:
        raise ValueError("Cannot build a batched transcription prompt with no requests")

    system_prompts = {request.prompt.system.strip() for request in requests}
    if len(system_prompts) != 1:
        raise ValueError("Batched transcription requires matching system prompts across pages")

    page_sections = []
    for request in requests:
        page_sections.append(
            "\n".join(
                [
                    f"Page {request.page_sequence}",
                    f"page_id: {request.page_id}",
                    "page_instructions:",
                    request.prompt.user,
                ]
            )
        )

    user = (
        "You will transcribe multiple page images in one request.\n"
        "Return ONLY valid JSON in this exact shape:\n"
        '{"pages":[{"page_id":"<exact page_id>","page_sequence":123,"transcription":"<text>"}]}\n'
        "Requirements:\n"
        "- Include exactly one item for every page image provided.\n"
        "- Use the exact page_id values shown below.\n"
        "- Keep each page's transcription separate; do not merge pages.\n"
        "- Preserve the order of pages.\n"
        "- Put only the transcription text in the transcription field.\n\n"
        "Page-specific instructions:\n\n"
        + "\n\n".join(page_sections)
    )
    return PromptMessages(system=requests[0].prompt.system, user=user)


def parse_batched_transcription_response(
    text: str,
    *,
    expected_page_ids: Sequence[str],
) -> dict[str, str]:
    """Parse page-keyed JSON returned from a batched transcription call."""
    payload = _loads_embedded_json(text)
    if isinstance(payload, dict):
        pages_payload = payload.get("pages")
    else:
        pages_payload = payload
    if not isinstance(pages_payload, list):
        raise ValueError("Batched transcription response did not contain a 'pages' list")

    parsed: dict[str, str] = {}
    for item in pages_payload:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id", "")).strip()
        transcription = str(item.get("transcription", "")).strip()
        if page_id:
            parsed[page_id] = transcription

    missing = [page_id for page_id in expected_page_ids if page_id not in parsed]
    if missing:
        raise ValueError(
            "Batched transcription response was missing page ids: "
            + ", ".join(missing)
        )
    return parsed


def _loads_embedded_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            cleaned = "\n".join(lines[1:-1]).strip()

    for candidate in (cleaned, *_json_substrings(cleaned)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("Response did not contain valid JSON")


def _json_substrings(text: str) -> list[str]:
    matches: list[str] = []
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            matches.append(match.group(0))
    return matches
