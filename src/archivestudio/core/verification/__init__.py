"""Verification helpers for independent transcription review."""

from archivestudio.core.verification.diff import (
    AlignmentResult,
    VerificationDiff,
    diff_transcriptions,
)
from archivestudio.core.verification.flags import (
    apply_pending_verification_decisions,
    link_decided_flags_to_text_version,
    load_open_verification_flags,
    mark_open_verification_flags_stale,
    mark_verification_flag_decision,
)

__all__ = [
    "AlignmentResult",
    "VerificationDiff",
    "diff_transcriptions",
    "apply_pending_verification_decisions",
    "link_decided_flags_to_text_version",
    "load_open_verification_flags",
    "mark_open_verification_flags_stale",
    "mark_verification_flag_decision",
]
