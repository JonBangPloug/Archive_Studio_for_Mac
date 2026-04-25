"""Configuration: per-user paths, settings, and library locations."""

from archivestudio.core.config.paths import (
    PathAccessError,
    user_config_dir,
    user_data_dir,
    user_log_dir,
    user_log_file,
    user_library_dir,
    user_settings_file,
)
from archivestudio.core.config.credentials import CredentialStoreError
from archivestudio.core.config.settings import (
    AppSettings,
    ProviderSettings,
    ensure_user_settings_file,
    load_app_settings,
    save_app_settings,
)

__all__ = [
    "AppSettings",
    "CredentialStoreError",
    "PathAccessError",
    "ProviderSettings",
    "ensure_user_settings_file",
    "load_app_settings",
    "save_app_settings",
    "user_config_dir",
    "user_data_dir",
    "user_log_dir",
    "user_log_file",
    "user_library_dir",
    "user_settings_file",
]
