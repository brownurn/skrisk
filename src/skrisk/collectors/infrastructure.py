"""Clients for infrastructure enrichment services."""

from __future__ import annotations

from urllib.parse import quote

import httpx


class MewhoisClient:
    """HTTP client for the mewhois domain enrichment service."""

    def __init__(self, *, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
        except Exception:
            return False
        return True

    async def lookup_domain(
        self,
        domain: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        url = f"{self._base_url}/api/v1/whois/{quote(domain, safe='')}"
        if client is None:
            async with httpx.AsyncClient(timeout=self._timeout) as managed_client:
                return await self.lookup_domain(domain, client=managed_client)

        response = await client.get(url)
        response.raise_for_status()
        return response.json()


class MeipClient:
    """HTTP client for the meip IP enrichment service."""

    def __init__(self, *, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
        except Exception:
            return False
        return True

    async def lookup_ip(
        self,
        ip: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        url = f"{self._base_url}/api/v1/ip/{quote(ip, safe='')}"
        if client is None:
            async with httpx.AsyncClient(timeout=self._timeout) as managed_client:
                return await self.lookup_ip(ip, client=managed_client)

        response = await client.get(url)
        response.raise_for_status()
        return response.json()
