"""Main window reliability tests."""

from __future__ import annotations

from archivestudio.ui.main_window import PageRecord
from archivestudio.ui.main_window import MainWindow


def test_load_launch_preset_fails_gracefully(monkeypatch, qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    captured: list[tuple[str, Exception]] = []

    monkeypatch.setattr(
        "archivestudio.ui.main_window.get_preset",
        lambda _name: (_ for _ in ()).throw(KeyError("missing preset")),
    )
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, error: captured.append((title, error)),
    )

    preset = window._load_launch_preset("Missing Preset", title="Could Not Load Preset")

    assert preset is None
    assert captured
    assert captured[0][0] == "Could Not Load Preset"


def test_delete_pages_message_uses_count_for_multiple_pages(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    records = [
        PageRecord(id=f"page-{index}", sequence=index, image_path=f"images/{index}.png", source_type=None)
        for index in range(1, 21)
    ]

    message = window._delete_pages_message(records)

    assert "Delete 20 selected pages?" in message
    assert "1, 2, 3" not in message


def test_selected_pages_scope_label_is_short_for_many_pages(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    records = [
        PageRecord(id=f"page-{index}", sequence=index, image_path=f"images/{index}.png", source_type=None)
        for index in range(1, 20)
    ]

    assert window._selected_pages_scope_label(records) == "19 selected pages"
