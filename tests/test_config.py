from __future__ import annotations

from skrisk.config import load_settings


def test_load_settings_uses_postgres_port_override_for_database_url(monkeypatch) -> None:
    monkeypatch.delenv("SKRISK_DATABASE_URL", raising=False)
    monkeypatch.setenv("SKRISK_POSTGRES_PORT", "15433")

    settings = load_settings()

    assert settings.database_url == "postgresql://skrisk:skrisk@127.0.0.1:15433/skrisk"


def test_load_settings_prefers_explicit_database_url(monkeypatch) -> None:
    monkeypatch.setenv("SKRISK_DATABASE_URL", "sqlite+aiosqlite:///./custom.db")
    monkeypatch.setenv("SKRISK_POSTGRES_PORT", "15433")

    settings = load_settings()

    assert settings.database_url == "sqlite+aiosqlite:///./custom.db"


def test_load_settings_uses_port_overrides_for_runtime_urls(monkeypatch) -> None:
    monkeypatch.delenv("SKRISK_OPENSEARCH_URL", raising=False)
    monkeypatch.delenv("SKRISK_NEO4J_HTTP_URL", raising=False)
    monkeypatch.setenv("SKRISK_OPENSEARCH_PORT", "19200")
    monkeypatch.setenv("SKRISK_NEO4J_HTTP_PORT", "17474")

    settings = load_settings()

    assert settings.opensearch_url == "http://127.0.0.1:19200"
    assert settings.neo4j_http_url == "http://127.0.0.1:17474"
