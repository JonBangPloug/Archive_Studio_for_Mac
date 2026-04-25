"""Helpers for parsing page range input in the desktop UI."""

from __future__ import annotations


class PageRangeParseError(ValueError):
    """Raised when a page range string cannot be parsed or validated."""


def parse_page_range_spec(spec: str, *, allowed_sequences: set[int]) -> list[int]:
    """Parse a page range spec like ``1-3,5,7-9`` into sorted unique page numbers."""
    cleaned = spec.strip()
    if not cleaned:
        raise PageRangeParseError("Enter at least one page number or range.")

    selected: set[int] = set()
    for raw_part in cleaned.split(","):
        part = raw_part.strip()
        if not part:
            raise PageRangeParseError("Page ranges cannot contain empty segments.")

        if "-" in part:
            bounds = [item.strip() for item in part.split("-", maxsplit=1)]
            if len(bounds) != 2 or not bounds[0] or not bounds[1]:
                raise PageRangeParseError(f"Invalid range: {part}")
            try:
                start = int(bounds[0])
                end = int(bounds[1])
            except ValueError as exc:
                raise PageRangeParseError(f"Invalid range: {part}") from exc
            if start > end:
                raise PageRangeParseError(f"Range start must be <= end: {part}")
            selected.update(range(start, end + 1))
        else:
            try:
                selected.add(int(part))
            except ValueError as exc:
                raise PageRangeParseError(f"Invalid page number: {part}") from exc

    if not selected:
        raise PageRangeParseError("No page numbers were selected.")

    invalid = sorted(number for number in selected if number not in allowed_sequences)
    if invalid:
        invalid_text = ", ".join(str(number) for number in invalid)
        raise PageRangeParseError(f"These pages do not exist in the project: {invalid_text}")

    return sorted(selected)
