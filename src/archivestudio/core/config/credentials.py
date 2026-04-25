"""API credential storage.

On macOS, ArchiveStudio stores API keys in Keychain via the system ``security``
tool. Environment variables remain supported as a technical-user fallback.
"""

from __future__ import annotations

import os
import platform
import subprocess


KEYCHAIN_SERVICE = "ArchiveStudio"

_ENV_VARS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}


class CredentialStoreError(RuntimeError):
    """Raised when credentials cannot be read from or written to secure storage."""


def load_api_key(provider_name: str) -> tuple[str, str | None]:
    """Return ``(api_key, error_message)`` from Keychain, then environment."""
    keychain_error: str | None = None
    try:
        keychain_key = _load_keychain_api_key(provider_name)
    except CredentialStoreError as exc:
        keychain_error = str(exc)
    else:
        if keychain_key:
            return keychain_key, None

    env_key = _load_environment_api_key(provider_name)
    if env_key:
        return env_key, keychain_error

    return "", keychain_error


def store_api_key(provider_name: str, api_key: str) -> None:
    """Store an API key in macOS Keychain, or delete it when blank."""
    cleaned = api_key.strip()
    if not cleaned and platform.system() != "Darwin":
        return

    if platform.system() != "Darwin":
        raise CredentialStoreError(
            "Secure API key saving currently requires macOS Keychain. "
            "Use environment variables for this provider on this platform."
        )

    if not cleaned:
        _delete_keychain_api_key(provider_name)
        return

    result = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            provider_name,
            "-w",
            cleaned,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialStoreError(
            f"Could not save {provider_name} API key to macOS Keychain: "
            f"{_security_error_message(result)}"
        )


def _load_keychain_api_key(provider_name: str) -> str:
    if platform.system() != "Darwin":
        return ""

    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-w",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            provider_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if _is_missing_keychain_item(result):
        return ""
    raise CredentialStoreError(
        f"Could not read {provider_name} API key from macOS Keychain: "
        f"{_security_error_message(result)}"
    )


def _delete_keychain_api_key(provider_name: str) -> None:
    result = subprocess.run(
        [
            "/usr/bin/security",
            "delete-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            provider_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 or _is_missing_keychain_item(result):
        return
    raise CredentialStoreError(
        f"Could not remove {provider_name} API key from macOS Keychain: "
        f"{_security_error_message(result)}"
    )


def _load_environment_api_key(provider_name: str) -> str:
    for env_var in _ENV_VARS.get(provider_name, ()):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return ""


def _is_missing_keychain_item(result: subprocess.CompletedProcess[str]) -> bool:
    combined = f"{result.stdout}\n{result.stderr}"
    return result.returncode == 44 or "could not be found" in combined.lower()


def _security_error_message(result: subprocess.CompletedProcess[str]) -> str:
    message = (result.stderr or result.stdout or "").strip()
    return message or f"security command exited with code {result.returncode}"
