"""Built-in structured export profiles."""

from __future__ import annotations


EXPORT_PROFILE_GENERIC = "generic_pages"
EXPORT_PROFILE_PATIENT_JOURNAL = "patient_journal_pages"


EXPORT_PROFILES: tuple[str, ...] = (
    EXPORT_PROFILE_GENERIC,
    EXPORT_PROFILE_PATIENT_JOURNAL,
)


EXPORT_PROFILE_LABELS = {
    EXPORT_PROFILE_GENERIC: "Generic Pages",
    EXPORT_PROFILE_PATIENT_JOURNAL: "Patient Journal Pages",
}
