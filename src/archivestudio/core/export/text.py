"""Plain-text export rendering."""

from __future__ import annotations

from archivestudio.core.export.common import ExportBundle


def render_text(bundle: ExportBundle) -> str:
    """Render a plain text export with simple markdown-like structure."""
    lines: list[str] = [
        f"# {bundle.project_name}",
        "",
        f"Exported at: {bundle.exported_at}",
        f"Scope: {bundle.scope_label}",
        f"Selected stage: {bundle.selected_stage}",
        f"Pages: {len(bundle.records)}",
        "",
    ]

    for record in bundle.records:
        lines.extend(
            [
                f"## Page {record.page_sequence:04d}",
                f"Page ID: {record.page_id}",
                f"Source type: {record.source_type or 'unspecified'}",
                f"Image path: {record.image_path}",
                "",
            ]
        )
        selected_text = record.selected_text.strip()
        if selected_text:
            lines.append(selected_text)
        else:
            lines.append("[No text available for this stage]")
        lines.extend(["", ""])

    return "\n".join(lines).rstrip() + "\n"
