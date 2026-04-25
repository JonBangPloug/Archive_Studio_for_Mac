"""Page range parsing tests for the desktop task UI."""

from __future__ import annotations

import pytest

from archivestudio.ui.task_ranges import PageRangeParseError, parse_page_range_spec


def test_parse_page_range_spec_accepts_ranges_and_individual_pages() -> None:
    result = parse_page_range_spec("1-3, 5, 7-8", allowed_sequences=set(range(1, 10)))
    assert result == [1, 2, 3, 5, 7, 8]


def test_parse_page_range_spec_deduplicates_and_sorts() -> None:
    result = parse_page_range_spec("5,3,3,2-4", allowed_sequences=set(range(1, 10)))
    assert result == [2, 3, 4, 5]


def test_parse_page_range_spec_rejects_missing_pages() -> None:
    with pytest.raises(PageRangeParseError, match="do not exist"):
        parse_page_range_spec("1-3, 10", allowed_sequences={1, 2, 3, 4, 5})


def test_parse_page_range_spec_rejects_invalid_ranges() -> None:
    with pytest.raises(PageRangeParseError, match="start must be <="):
        parse_page_range_spec("5-2", allowed_sequences=set(range(1, 10)))
