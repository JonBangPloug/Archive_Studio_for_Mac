"""Main window reliability tests."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt

from archivestudio.core.config.settings import AppSettings, ProviderSettings
from archivestudio.ui import main_window as main_window_module
from archivestudio.ui.main_window import (
    WORKSPACE_LAYOUT_SIDE_BY_SIDE,
    WORKSPACE_LAYOUT_STACKED,
    MainWindow,
    PageRecord,
)


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


def test_provider_status_label_describes_app_default_not_task_model(monkeypatch, qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    provider = SimpleNamespace(provider_name="google", model_id="gemini-test")
    selection = SimpleNamespace(
        provider=provider,
        used_fallback=False,
        message=None,
    )
    settings = SimpleNamespace(default_provider="google")
    monkeypatch.setattr("archivestudio.ui.main_window.load_app_settings", lambda: settings)
    monkeypatch.setattr(
        "archivestudio.ui.main_window.create_provider_from_settings",
        lambda _settings: selection,
    )

    window._refresh_provider_status()

    assert window.provider_status_label.text() == "App default model: google:gemini-test"
    assert "Prompt presets can override" in window.provider_status_label.toolTip()


def test_workspace_layout_can_switch_between_stacked_and_side_by_side(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window._apply_workspace_layout(WORKSPACE_LAYOUT_STACKED, persist=False)
    assert window.workspace_splitter.orientation() == Qt.Orientation.Vertical
    assert window.stacked_layout_action.isChecked() is True

    window._apply_workspace_layout(WORKSPACE_LAYOUT_SIDE_BY_SIDE, persist=False)
    assert window.workspace_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.side_by_side_layout_action.isChecked() is True


def test_workspace_layout_toggle_is_persisted(monkeypatch, qtbot, tmp_path) -> None:
    settings = AppSettings(
        openai=ProviderSettings(enabled=False, api_key="", model="gpt-test"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-test"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-test"),
        default_provider="demo",
        auto_open_last_work=False,
        path=tmp_path / "settings.toml",
        workspace_layout=WORKSPACE_LAYOUT_STACKED,
        pages_pane_visible=True,
        main_splitter_sizes=(250, 1000),
        stacked_workspace_sizes=(520, 320),
        side_by_side_workspace_sizes=(700, 500),
    )
    saved: list[AppSettings] = []

    def fake_load_app_settings() -> AppSettings:
        return saved[-1] if saved else settings

    def fake_save_app_settings(value: AppSettings, *, store_credentials: bool = True):
        saved.append(value)
        return value.path

    monkeypatch.setattr(main_window_module, "load_app_settings", fake_load_app_settings)
    monkeypatch.setattr(main_window_module, "save_app_settings", fake_save_app_settings)

    window = MainWindow()
    qtbot.addWidget(window)

    assert window._last_pages_pane_width == 320
    assert window.pages_panel.minimumWidth() == 160
    assert window.move_page_down_button.text() == "Down"
    assert window.rotate_pages_button.text() == "Rotate"
    assert window.delete_page_button.text() == "Delete"

    window._set_workspace_layout(WORKSPACE_LAYOUT_SIDE_BY_SIDE)

    assert saved
    assert saved[-1].workspace_layout == WORKSPACE_LAYOUT_SIDE_BY_SIDE
    assert saved[-1].main_splitter_sizes
    assert saved[-1].side_by_side_workspace_sizes


def test_pages_pane_can_be_hidden_and_restored(monkeypatch, qtbot, tmp_path) -> None:
    settings = AppSettings(
        openai=ProviderSettings(enabled=False, api_key="", model="gpt-test"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-test"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-test"),
        default_provider="demo",
        auto_open_last_work=False,
        path=tmp_path / "settings.toml",
        workspace_layout=WORKSPACE_LAYOUT_STACKED,
        pages_pane_visible=True,
        main_splitter_sizes=(170, 1000),
        stacked_workspace_sizes=(520, 320),
        side_by_side_workspace_sizes=(700, 500),
    )
    saved: list[AppSettings] = []

    def fake_load_app_settings() -> AppSettings:
        return saved[-1] if saved else settings

    def fake_save_app_settings(value: AppSettings, *, store_credentials: bool = True):
        saved.append(value)
        return value.path

    monkeypatch.setattr(main_window_module, "load_app_settings", fake_load_app_settings)
    monkeypatch.setattr(main_window_module, "save_app_settings", fake_save_app_settings)

    window = MainWindow()
    qtbot.addWidget(window)
    window.main_splitter.setSizes([180, main_window_module.PAGES_PANE_TOGGLE_WIDTH, 1000])
    window._apply_pages_pane_visibility(False, persist=True)

    assert window.show_pages_pane_action.isChecked() is False
    assert window.pages_panel.isHidden() is True
    assert window.pages_pane_toggle_bar.isHidden() is False
    assert window.pages_pane_toggle_button.text() == ">"
    assert saved[-1].pages_pane_visible is False
    assert saved[-1].main_splitter_sizes[0] >= 160

    window._apply_pages_pane_visibility(True, persist=True)

    assert window.show_pages_pane_action.isChecked() is True
    assert window.pages_panel.isHidden() is False
    assert window.pages_pane_toggle_button.text() == "<"
    assert window.main_splitter.sizes()[0] > 0
    assert saved[-1].pages_pane_visible is True


def test_pages_pane_toggle_button_hides_and_restores(monkeypatch, qtbot, tmp_path) -> None:
    settings = AppSettings(
        openai=ProviderSettings(enabled=False, api_key="", model="gpt-test"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-test"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-test"),
        default_provider="demo",
        auto_open_last_work=False,
        path=tmp_path / "settings.toml",
        workspace_layout=WORKSPACE_LAYOUT_STACKED,
        pages_pane_visible=True,
        main_splitter_sizes=(180, 1000),
        stacked_workspace_sizes=(520, 320),
        side_by_side_workspace_sizes=(700, 500),
    )
    saved: list[AppSettings] = []

    def fake_load_app_settings() -> AppSettings:
        return saved[-1] if saved else settings

    def fake_save_app_settings(value: AppSettings, *, store_credentials: bool = True):
        saved.append(value)
        return value.path

    monkeypatch.setattr(main_window_module, "load_app_settings", fake_load_app_settings)
    monkeypatch.setattr(main_window_module, "save_app_settings", fake_save_app_settings)

    window = MainWindow()
    qtbot.addWidget(window)

    window.pages_pane_toggle_button.click()

    assert window.pages_panel.isHidden() is True
    assert window.pages_pane_toggle_bar.isHidden() is False
    assert window.pages_pane_toggle_button.text() == ">"
    assert saved[-1].pages_pane_visible is False

    window.pages_pane_toggle_button.click()

    assert window.pages_panel.isHidden() is False
    assert window.pages_pane_toggle_button.text() == "<"
    assert saved[-1].main_splitter_sizes[0] >= 160
    assert saved[-1].pages_pane_visible is True


def test_cramped_saved_pages_pane_width_is_migrated(monkeypatch, qtbot, tmp_path) -> None:
    settings = AppSettings(
        openai=ProviderSettings(enabled=False, api_key="", model="gpt-test"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-test"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-test"),
        default_provider="demo",
        auto_open_last_work=False,
        path=tmp_path / "settings.toml",
        workspace_layout=WORKSPACE_LAYOUT_STACKED,
        pages_pane_visible=True,
        main_splitter_sizes=(120, 1000),
        stacked_workspace_sizes=(520, 320),
        side_by_side_workspace_sizes=(700, 500),
    )

    monkeypatch.setattr(main_window_module, "load_app_settings", lambda: settings)

    window = MainWindow()
    qtbot.addWidget(window)

    assert window._last_pages_pane_width == 160
    assert window.pages_panel.minimumWidth() == 160
