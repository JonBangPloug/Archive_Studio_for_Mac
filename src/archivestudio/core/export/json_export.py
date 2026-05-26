"""JSON and JSONL export rendering."""

from __future__ import annotations

import json

from archivestudio.core.export.common import ExportBundle, ExportPageRecord
from archivestudio.core.export.profiles import EXPORT_PROFILE_GENERIC, EXPORT_PROFILE_PATIENT_JOURNAL


def render_json(bundle: ExportBundle) -> str:
    """Render an export bundle as pretty JSON."""
    payload = {
        "project": {
            "name": bundle.project_name,
        },
        "export": {
            "format": bundle.export_format,
            "profile": bundle.export_profile,
            "selected_stage": bundle.selected_stage,
            "scope": bundle.scope_label,
            "exported_at": bundle.exported_at,
            "record_count": len(bundle.records),
        },
        "records": [_record_to_dict(record, profile=bundle.export_profile) for record in bundle.records],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_jsonl(bundle: ExportBundle) -> str:
    """Render an export bundle as one JSON record per line."""
    lines = [
        json.dumps(
            {
                "project_name": bundle.project_name,
                "export_profile": bundle.export_profile,
                "selected_stage": bundle.selected_stage,
                "scope": bundle.scope_label,
                "exported_at": bundle.exported_at,
                **_record_to_dict(record, profile=bundle.export_profile),
            },
            ensure_ascii=False,
        )
        for record in bundle.records
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _record_to_dict(record: ExportPageRecord, *, profile: str) -> dict[str, object]:
    if profile == EXPORT_PROFILE_PATIENT_JOURNAL:
        return _patient_journal_record(record)
    return _generic_record(record)


def _generic_record(record: ExportPageRecord) -> dict[str, object]:
    return {
        "page_id": record.page_id,
        "page_sequence": record.page_sequence,
        "source_type": record.source_type,
        "image_path": record.image_path,
        "selected_stage": record.selected_stage,
        "selected_text": record.selected_text,
        "text_versions": record.text_versions,
        "version_metadata": record.version_metadata,
    }


def _patient_journal_record(record: ExportPageRecord) -> dict[str, object]:
    return {
        "record_type": "patient_journal_page",
        "page": {
            "id": record.page_id,
            "sequence": record.page_sequence,
            "image_path": record.image_path,
            "source_type": record.source_type,
        },
        "journal_text": {
            "selected_stage": record.selected_stage,
            "selected_text": record.selected_text,
            "original_text": record.text_versions.get("original", ""),
            "corrected_text": record.text_versions.get("corrected", ""),
            "translated_text": record.text_versions.get("translated", ""),
        },
        "provenance": {
            "original": record.version_metadata.get("original", {}),
            "corrected": record.version_metadata.get("corrected", {}),
            "translated": record.version_metadata.get("translated", {}),
        },
        "structured_fields": {
            "entry_date": None,
            "patient_identifier": None,
            "ward_or_location": None,
            "clinician": None,
            "diagnosis_or_subject": None,
        },
    }
