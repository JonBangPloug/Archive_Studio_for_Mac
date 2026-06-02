"""Independent transcription verification diff tests."""

from archivestudio.core.models import (
    VERIFICATION_FLAG_ALIGNMENT_WARNING,
    VERIFICATION_FLAG_INSERT,
    VERIFICATION_FLAG_REPLACE,
)
from archivestudio.core.verification import diff_transcriptions


def test_diff_transcriptions_ignores_whitespace_only_changes() -> None:
    result = diff_transcriptions("In principio\nerat verbum.", "In principio erat verbum.")

    assert result.status == "ok"
    assert result.flags == []


def test_diff_transcriptions_flags_replacement_with_primary_offsets() -> None:
    primary = "In principio erat verbum."
    result = diff_transcriptions(primary, "In principio fuit verbum.")

    assert result.status == "ok"
    assert len(result.flags) == 1
    flag = result.flags[0]
    assert flag.flag_type == VERIFICATION_FLAG_REPLACE
    assert flag.primary_text == "erat"
    assert flag.alternative_text == "fuit"
    assert primary[flag.primary_start:flag.primary_end] == "erat"


def test_diff_transcriptions_flags_insertions_at_zero_width_offsets() -> None:
    result = diff_transcriptions("Alpha beta.", "Alpha et beta.")

    assert len(result.flags) == 1
    flag = result.flags[0]
    assert flag.flag_type == VERIFICATION_FLAG_INSERT
    assert flag.primary_start == flag.primary_end
    assert flag.alternative_text == "et"


def test_diff_transcriptions_warns_when_alignment_is_unreliable() -> None:
    result = diff_transcriptions(
        "Alpha beta gamma delta epsilon.",
        "Completely unrelated verifier text with nothing aligned.",
    )

    assert result.status == "warning"
    assert len(result.flags) == 1
    assert result.flags[0].flag_type == VERIFICATION_FLAG_ALIGNMENT_WARNING
