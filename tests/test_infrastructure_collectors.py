from __future__ import annotations

import httpx
import pytest

from skrisk.collectors.infrastructure import MeipClient, MewhoisClient


@pytest.mark.asyncio
async def test_mewhois_client_returns_normalized_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/whois/drop.example"
        return httpx.Response(
            200,
            json={
                "domain": "drop.example",
                "registrar": "Example Registrar",
                "registrantOrg": "Bad Actors LLC",
                "registrantCountry": "US",
                "nameservers": ["ns1.drop.example", "ns2.drop.example"],
                "isPrivacyProtected": True,
                "cacheHit": True,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://whois.test") as client:
        payload = await MewhoisClient(base_url="https://whois.test").lookup_domain(
            "drop.example",
            client=client,
        )

    assert payload["domain"] == "drop.example"
    assert payload["registrar"] == "Example Registrar"
    assert payload["registrantOrg"] == "Bad Actors LLC"
    assert payload["nameservers"] == ["ns1.drop.example", "ns2.drop.example"]


@pytest.mark.asyncio
async def test_meip_client_health_check_returns_false_for_connect_failures(monkeypatch) -> None:
    client = MeipClient(base_url="https://ip.test")

    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_meip_client_returns_ip_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ip/8.8.8.8"
        return httpx.Response(
            200,
            json={
                "ip": "8.8.8.8",
                "asn": "AS15169",
                "asName": "Google LLC",
                "countryCode": "US",
                "flags": ["Hosting", "Anycast"],
                "isHosting": True,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://ip.test") as http_client:
        payload = await MeipClient(base_url="https://ip.test").lookup_ip(
            "8.8.8.8",
            client=http_client,
        )

    assert payload["ip"] == "8.8.8.8"
    assert payload["asn"] == "AS15169"
    assert payload["asName"] == "Google LLC"
    assert payload["flags"] == ["Hosting", "Anycast"]
