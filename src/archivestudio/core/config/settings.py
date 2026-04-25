"""User settings file management.

For now this focuses on provider selection and a couple of simple app
preferences. API keys are stored outside this TOML file.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
import tomllib

from archivestudio.core.config.paths import user_settings_file
from archivestudio.core.config.credentials import load_api_key, store_api_key


DEFAULT_SETTINGS_TOML = """# ArchiveStudio user settings
#
# Choose the providers you want to use. API keys are stored in macOS Keychain.
# Technical fallback environment variables:
# OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GEMINI_API_KEY.
# This file lives in your per-user config directory, not inside projects.

[providers.openai]
enabled = false
model = "gpt-4.1-mini"

[providers.anthropic]
enabled = false
model = "claude-sonnet-4-5"

[providers.google]
enabled = false
model = "gemini-2.5-pro"

[app]
default_provider = "demo"
auto_open_last_work = false
last_import_dir = ""
"""


@dataclass(frozen=True)
class ProviderSettings:
    enabled: bool
    api_key: str
    model: str
    credential_error: str | None = None


@dataclass(frozen=True)
class AppSettings:
    openai: ProviderSettings
    anthropic: ProviderSettings
    google: ProviderSettings
    default_provider: str
    auto_open_last_work: bool
    path: Path
    last_import_dir: str = ""


def ensure_user_settings_file() -> Path:
    """Create the user settings file with a starter template if missing."""
    path = user_settings_file()
    if not path.exists():
        _atomic_write_text(path, DEFAULT_SETTINGS_TOML)
    return path


def load_app_settings() -> AppSettings:
    """Load user settings from TOML, creating the file on first use."""
    path = ensure_user_settings_file()
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    providers = data.get("providers", {})
    app = data.get("app", {})

    return AppSettings(
        openai=_provider_settings(
            "openai",
            providers.get("openai", {}),
            default_model="gpt-4.1-mini",
        ),
        anthropic=_provider_settings(
            "anthropic",
            providers.get("anthropic", {}),
            default_model="claude-sonnet-4-5",
        ),
        google=_provider_settings(
            "google",
            providers.get("google", {}),
            default_model="gemini-2.5-pro",
        ),
        default_provider=str(app.get("default_provider", "demo")),
        auto_open_last_work=bool(app.get("auto_open_last_work", False)),
        path=path,
        last_import_dir=str(app.get("last_import_dir", "")),
    )


def save_app_settings(settings: AppSettings, *, store_credentials: bool = True) -> Path:
    """Persist user settings back to the TOML file."""
    path = ensure_user_settings_file()
    if store_credentials:
        _store_api_keys(settings)
    payload = _render_settings_toml(settings)
    _atomic_write_text(path, payload)
    return path


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise


def _provider_settings(
    provider_name: str,
    raw: dict[str, object],
    *,
    default_model: str,
) -> ProviderSettings:
    api_key, credential_error = load_api_key(provider_name)
    return ProviderSettings(
        enabled=bool(raw.get("enabled", False)),
        api_key=api_key,
        model=str(raw.get("model", default_model)),
        credential_error=credential_error,
    )


def _store_api_keys(settings: AppSettings) -> None:
    store_api_key("openai", settings.openai.api_key)
    store_api_key("anthropic", settings.anthropic.api_key)
    store_api_key("google", settings.google.api_key)


def _render_settings_toml(settings: AppSettings) -> str:
    sections = [
        "# ArchiveStudio user settings",
        "# This file can be edited manually or through the in-app Settings dialog.",
        "",
        "[providers.openai]",
        _provider_lines(settings.openai),
        "",
        "[providers.anthropic]",
        _provider_lines(settings.anthropic),
        "",
        "[providers.google]",
        _provider_lines(settings.google),
        "",
        "[app]",
        f'default_provider = "{_escape_toml_string(settings.default_provider)}"',
        f"auto_open_last_work = {_bool_literal(settings.auto_open_last_work)}",
        f'last_import_dir = "{_escape_toml_string(settings.last_import_dir)}"',
        "",
    ]
    return "\n".join(sections)


def _provider_lines(settings: ProviderSettings) -> str:
    return "\n".join(
        [
            f"enabled = {_bool_literal(settings.enabled)}",
            f'model = "{_escape_toml_string(settings.model)}"',
        ]
    )


def _bool_literal(value: bool) -> str:
    return "true" if value else "false"


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
