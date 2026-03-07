"""Minimal VirusTotal client wrappers used for selective enrichment."""

from __future__ import annotations

import base64

import httpx


class VirusTotalClient:
    """Thin client around the VT v3 indicator endpoints."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def lookup(self, indicator_type: str, indicator_value: str) -> dict:
        endpoint = _indicator_endpoint(indicator_type, indicator_value)
        async with httpx.AsyncClient(
            base_url="https://www.virustotal.com/api/v3",
            timeout=30.0,
            headers={"x-apikey": self._api_key},
        ) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            return response.json()


def _indicator_endpoint(indicator_type: str, indicator_value: str) -> str:
    if indicator_type == "url":
        encoded = base64.urlsafe_b64encode(indicator_value.encode("utf-8")).decode("ascii").rstrip("=")
        return f"/urls/{encoded}"
    if indicator_type == "domain":
        return f"/domains/{indicator_value}"
    if indicator_type == "ip":
        return f"/ip_addresses/{indicator_value}"
    if indicator_type == "sha256":
        return f"/files/{indicator_value}"
    raise ValueError(f"Unsupported VT indicator type: {indicator_type}")
