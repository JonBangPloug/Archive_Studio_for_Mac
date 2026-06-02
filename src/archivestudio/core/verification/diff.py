"""Text-only alignment for independent transcription verification.

The v1 verifier deliberately stays modest: compare token sequences, ignore
whitespace-only differences, and produce phrase-level flags with offsets in the
primary text. A low-confidence alignment produces one page-level warning rather
than a flood of misleading micro-flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from archivestudio.core.models import (
    VERIFICATION_FLAG_ALIGNMENT_WARNING,
    VERIFICATION_FLAG_DELETE,
    VERIFICATION_FLAG_INSERT,
    VERIFICATION_FLAG_REPLACE,
)


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_MIN_ALIGNMENT_RATIO = 0.35
_MAX_FLAGS = 200


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int

    @property
    def normalized(self) -> str:
        return self.text.casefold()


@dataclass(frozen=True)
class VerificationDiff:
    """One text disagreement between primary and verifier transcriptions."""

    primary_start: int
    primary_end: int
    primary_text: str
    alternative_text: str
    flag_type: str


@dataclass(frozen=True)
class AlignmentResult:
    """Result of comparing primary and verifier transcriptions."""

    status: str
    message: str
    flags: list[VerificationDiff]


def diff_transcriptions(primary_text: str, verifier_text: str) -> AlignmentResult:
    """Compare two transcriptions and return human-reviewable differences."""
    primary_tokens = _tokenize(primary_text)
    verifier_tokens = _tokenize(verifier_text)

    if not primary_tokens and not verifier_tokens:
        return AlignmentResult(status="ok", message="No text to compare.", flags=[])
    if not primary_tokens or not verifier_tokens:
        return _warning(
            primary_text=primary_text,
            alternative_text=verifier_text,
            message="Could not align transcriptions because one side is empty.",
        )

    primary_norm = [token.normalized for token in primary_tokens]
    verifier_norm = [token.normalized for token in verifier_tokens]
    matcher = SequenceMatcher(a=primary_norm, b=verifier_norm, autojunk=False)
    ratio = matcher.ratio()
    if ratio < _MIN_ALIGNMENT_RATIO:
        return _warning(
            primary_text=primary_text,
            alternative_text=verifier_text,
            message=(
                "The primary and verifier transcriptions were too different "
                "to align reliably."
            ),
        )

    flags: list[VerificationDiff] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            flags.append(
                VerificationDiff(
                    primary_start=primary_tokens[i1].start,
                    primary_end=primary_tokens[i2 - 1].end,
                    primary_text=_span_text(primary_text, primary_tokens, i1, i2),
                    alternative_text=_span_text(verifier_text, verifier_tokens, j1, j2),
                    flag_type=VERIFICATION_FLAG_REPLACE,
                )
            )
        elif tag == "delete":
            flags.append(
                VerificationDiff(
                    primary_start=primary_tokens[i1].start,
                    primary_end=primary_tokens[i2 - 1].end,
                    primary_text=_span_text(primary_text, primary_tokens, i1, i2),
                    alternative_text="",
                    flag_type=VERIFICATION_FLAG_DELETE,
                )
            )
        elif tag == "insert":
            insert_at = (
                primary_tokens[i1].start
                if i1 < len(primary_tokens)
                else len(primary_text)
            )
            flags.append(
                VerificationDiff(
                    primary_start=insert_at,
                    primary_end=insert_at,
                    primary_text="",
                    alternative_text=_span_text(verifier_text, verifier_tokens, j1, j2),
                    flag_type=VERIFICATION_FLAG_INSERT,
                )
            )

    if len(flags) > _MAX_FLAGS:
        return _warning(
            primary_text=primary_text,
            alternative_text=verifier_text,
            message=(
                "The comparison produced too many differences to present "
                "safely as individual flags."
            ),
        )

    return AlignmentResult(
        status="ok",
        message=f"Found {len(flags)} possible transcription difference(s).",
        flags=flags,
    )


def _tokenize(text: str) -> list[_Token]:
    return [
        _Token(match.group(0), match.start(), match.end())
        for match in _TOKEN_RE.finditer(text)
    ]


def _span_text(text: str, tokens: list[_Token], start_index: int, end_index: int) -> str:
    if start_index >= end_index:
        return ""
    return text[tokens[start_index].start : tokens[end_index - 1].end]


def _warning(
    *,
    primary_text: str,
    alternative_text: str,
    message: str,
) -> AlignmentResult:
    return AlignmentResult(
        status="warning",
        message=message,
        flags=[
            VerificationDiff(
                primary_start=0,
                primary_end=len(primary_text),
                primary_text=primary_text,
                alternative_text=alternative_text,
                flag_type=VERIFICATION_FLAG_ALIGNMENT_WARNING,
            )
        ],
    )
