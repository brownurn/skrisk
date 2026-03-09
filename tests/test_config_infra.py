from __future__ import annotations

from skrisk.config import load_settings


def test_load_settings_uses_infrastructure_port_defaults_when_urls_not_set(monkeypatch) -> None:
    monkeypatch.delenv("SKRISK_MEWHOIS_URL", raising=False)
    monkeypatch.delenv("SKRISK_MEIP_URL", raising=False)
    monkeypatch.setenv("SKRISK_MEWHOIS_PORT", "18191")
    monkeypatch.setenv("SKRISK_MEIP_PORT", "18190")

    settings = load_settings()

    assert settings.mewhois_url == "http://127.0.0.1:18191"
    assert settings.meip_url == "http://127.0.0.1:18190"


def test_load_settings_prefers_explicit_infrastructure_urls(monkeypatch) -> None:
    monkeypatch.setenv("SKRISK_MEWHOIS_URL", "http://10.23.94.13:8191")
    monkeypatch.setenv("SKRISK_MEIP_URL", "http://10.23.94.13:8190")
    monkeypatch.setenv("SKRISK_MEWHOIS_PORT", "18191")
    monkeypatch.setenv("SKRISK_MEIP_PORT", "18190")

    settings = load_settings()

    assert settings.mewhois_url == "http://10.23.94.13:8191"
    assert settings.meip_url == "http://10.23.94.13:8190"
