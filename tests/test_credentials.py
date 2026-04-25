"""Credential storage tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from archivestudio.core.config import credentials as credentials_module
from archivestudio.core.config.credentials import CredentialStoreError, load_api_key, store_api_key


def test_load_api_key_prefers_keychain_over_environment(monkeypatch) -> None:
    monkeypatch.setattr(credentials_module, "_load_keychain_api_key", lambda _provider: "from-keychain")
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    api_key, error = load_api_key("openai")

    assert api_key == "from-keychain"
    assert error is None


def test_load_api_key_falls_back_to_environment(monkeypatch) -> None:
    monkeypatch.setattr(credentials_module, "_load_keychain_api_key", lambda _provider: "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

    api_key, error = load_api_key("anthropic")

    assert api_key == "from-env"
    assert error is None


def test_load_api_key_returns_keychain_error_when_no_fallback(monkeypatch) -> None:
    def fail(_provider):
        raise CredentialStoreError("Keychain denied access")

    monkeypatch.setattr(credentials_module, "_load_keychain_api_key", fail)

    api_key, error = load_api_key("google")

    assert api_key == ""
    assert error == "Keychain denied access"


def test_store_api_key_requires_macos_for_secure_save(monkeypatch) -> None:
    monkeypatch.setattr(credentials_module.platform, "system", lambda: "Linux")

    with pytest.raises(CredentialStoreError, match="macOS Keychain"):
        store_api_key("openai", "sk-test")


def test_store_api_key_allows_blank_on_non_macos(monkeypatch) -> None:
    monkeypatch.setattr(credentials_module.platform, "system", lambda: "Linux")

    store_api_key("openai", "")


def test_store_api_key_writes_to_security_tool(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(credentials_module.platform, "system", lambda: "Darwin")

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(credentials_module.subprocess, "run", fake_run)

    store_api_key("openai", "sk-test")

    args = captured["args"]
    assert "/usr/bin/security" in args
    assert "add-generic-password" in args
    assert "-U" in args
    assert "sk-test" in args
