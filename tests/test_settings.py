"""Settings load/save tests."""

from __future__ import annotations

from pathlib import Path
import pytest

from archivestudio.core.config import settings as settings_module
from archivestudio.core.config.settings import AppSettings, ProviderSettings, load_app_settings, save_app_settings


def test_save_and_load_app_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.toml"
    monkeypatch.setattr(settings_module, "user_settings_file", lambda: settings_path)
    stored_keys: dict[str, str] = {}
    monkeypatch.setattr(
        settings_module,
        "store_api_key",
        lambda provider_name, api_key: stored_keys.__setitem__(provider_name, api_key),
    )
    monkeypatch.setattr(
        settings_module,
        "load_api_key",
        lambda provider_name: (stored_keys.get(provider_name, ""), None),
    )

    initial = AppSettings(
        openai=ProviderSettings(enabled=True, api_key='sk-"openai"', model="gpt-4.1-mini"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-sonnet-4-5"),
        google=ProviderSettings(enabled=True, api_key="google-key", model="gemini-2.5-pro"),
        default_provider="openai",
        auto_open_last_work=True,
        path=settings_path,
        last_import_dir=str(tmp_path / "imports"),
    )

    save_path = save_app_settings(initial)
    loaded = load_app_settings()

    assert save_path == settings_path
    assert loaded.openai.enabled is True
    assert loaded.openai.api_key == 'sk-"openai"'
    assert loaded.google.enabled is True
    assert loaded.default_provider == "openai"
    assert loaded.auto_open_last_work is True
    assert loaded.last_import_dir == str(tmp_path / "imports")
    rendered = settings_path.read_text(encoding="utf-8")
    assert "sk-" not in rendered
    assert "google-key" not in rendered
    assert "api_key" not in rendered
    assert 'last_import_dir = "' in rendered


def test_save_app_settings_is_atomic_on_replace_failure(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text("original-settings", encoding="utf-8")
    monkeypatch.setattr(settings_module, "user_settings_file", lambda: settings_path)
    monkeypatch.setattr(settings_module, "store_api_key", lambda _provider_name, _api_key: None)

    original_replace = settings_module.Path.replace

    def failing_replace(self: Path, target: Path) -> Path:
        if target == settings_path:
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(settings_module.Path, "replace", failing_replace)

    updated = AppSettings(
        openai=ProviderSettings(enabled=False, api_key="", model="gpt-4.1-mini"),
        anthropic=ProviderSettings(enabled=True, api_key="anthropic-key", model="claude-sonnet-4-5"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-2.5-pro"),
        default_provider="anthropic",
        auto_open_last_work=False,
        path=settings_path,
    )

    with pytest.raises(OSError):
        save_app_settings(updated)

    assert settings_path.read_text(encoding="utf-8") == "original-settings"


def test_load_app_settings_ignores_legacy_plaintext_api_key(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text(
        "\n".join(
            [
                "[providers.openai]",
                "enabled = true",
                'api_key = "legacy-plaintext-key"',
                'model = "gpt-test"',
                "",
                "[providers.anthropic]",
                "enabled = false",
                'model = "claude-test"',
                "",
                "[providers.google]",
                "enabled = false",
                'model = "gemini-test"',
                "",
                "[app]",
                'default_provider = "openai"',
                "auto_open_last_work = false",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "user_settings_file", lambda: settings_path)
    monkeypatch.setattr(settings_module, "load_api_key", lambda _provider_name: ("", None))

    loaded = load_app_settings()

    assert loaded.openai.enabled is True
    assert loaded.openai.api_key == ""


def test_save_app_settings_can_skip_credential_storage(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.toml"
    monkeypatch.setattr(settings_module, "user_settings_file", lambda: settings_path)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        settings_module,
        "store_api_key",
        lambda provider_name, api_key: calls.append((provider_name, api_key)),
    )

    settings = AppSettings(
        openai=ProviderSettings(enabled=True, api_key="openai-key", model="gpt-4.1-mini"),
        anthropic=ProviderSettings(enabled=False, api_key="", model="claude-sonnet-4-5"),
        google=ProviderSettings(enabled=False, api_key="", model="gemini-2.5-pro"),
        default_provider="openai",
        auto_open_last_work=False,
        path=settings_path,
        last_import_dir=str(tmp_path / "source"),
    )

    save_app_settings(settings, store_credentials=False)

    assert calls == []
    assert f'last_import_dir = "{tmp_path / "source"}"' in settings_path.read_text(
        encoding="utf-8"
    )
