"""Archive and parser helpers for Abuse.ch threat-intelligence feeds."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import httpx


@dataclass(slots=True, frozen=True)
class ArchiveManifestResult:
    """Paths and hashes for an archived feed snapshot."""

    archive_path: Path
    manifest_path: Path
    archive_sha256: str


@dataclass(slots=True, frozen=True)
class ParsedIndicator:
    """Normalized IOC extracted from a provider record."""

    indicator_type: str
    indicator_value: str
    observation: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ParsedFeed:
    """Normalized representation of a parsed bulk feed export."""

    provider: str
    feed_name: str
    indicators: list[ParsedIndicator]
    row_count: int


async def download_feed_archive(
    *,
    url: str,
    auth_key: str,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """Download an Abuse.ch export using the provided auth key."""

    if client is None:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as managed_client:
            return await download_feed_archive(url=url, auth_key=auth_key, client=managed_client)

    response = await client.get(url, params={"auth-key": auth_key})
    response.raise_for_status()
    return response.content


async def download_urlhaus_recent_payload(
    *,
    auth_key: str,
    limit: int = 1000,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Download the recent URLhaus JSON payload."""

    url = f"https://urlhaus-api.abuse.ch/v1/urls/recent/limit/{limit}/"
    return await _download_json_payload(url=url, auth_key=auth_key, method="GET", client=client)


async def download_threatfox_recent_payload(
    *,
    auth_key: str,
    days: int = 1,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Download recent ThreatFox IOCs through the official API."""

    return await _download_json_payload(
        url="https://threatfox-api.abuse.ch/api/v1/",
        auth_key=auth_key,
        method="POST",
        json_payload={"query": "get_iocs", "days": days},
        client=client,
    )


def write_archive_manifest(
    *,
    provider: str,
    feed_name: str,
    fetched_at: datetime,
    raw_bytes: bytes,
    row_count: int,
    destination: Path,
    source_url: str,
    artifact_name: str,
) -> ArchiveManifestResult:
    """Persist a raw feed archive and a small manifest beside it."""

    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / artifact_name
    archive_path.write_bytes(raw_bytes)
    archive_sha256 = sha256(raw_bytes).hexdigest()

    manifest = {
        "provider": provider,
        "feed_name": feed_name,
        "fetched_at": fetched_at.isoformat(),
        "source_url": source_url,
        "archive_path": archive_path.as_posix(),
        "archive_sha256": archive_sha256,
        "archive_size_bytes": len(raw_bytes),
        "row_count": row_count,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return ArchiveManifestResult(
        archive_path=archive_path,
        manifest_path=manifest_path,
        archive_sha256=archive_sha256,
    )


def parse_urlhaus_archive(archive_path: Path) -> ParsedFeed:
    """Parse the URLhaus full JSON export into normalized IOC records."""

    payload = json.loads(_read_zip_member_text(archive_path, "urlhaus_full.json"))
    rows = payload.values() if isinstance(payload, dict) else payload

    indicators: list[ParsedIndicator] = []
    row_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_count += 1
        indicators.extend(_urlhaus_record_indicators(row))

    return ParsedFeed(
        provider="abusech",
        feed_name="urlhaus",
        indicators=indicators,
        row_count=row_count,
    )


def parse_threatfox_archive(archive_path: Path) -> ParsedFeed:
    """Parse the ThreatFox full CSV export into normalized IOC records."""

    raw_text = _read_zip_member_text(archive_path, "full.csv")
    lines = [line for line in raw_text.splitlines() if line and not line.startswith("#")]
    reader = csv.DictReader(lines)

    indicators: list[ParsedIndicator] = []
    row_count = 0
    for row in reader:
        row_count += 1
        indicator_value = (row.get("ioc") or "").strip()
        indicator_type = _normalize_threatfox_type(row.get("ioc_type") or "")
        if not indicator_value or indicator_type is None:
            continue
        indicators.append(
            ParsedIndicator(
                indicator_type=indicator_type,
                indicator_value=indicator_value,
                observation={
                    "source_provider": "abusech",
                    "source_feed": "threatfox",
                    "provider_record_id": row.get("id") or None,
                    "classification": row.get("threat_type") or None,
                    "confidence_label": row.get("confidence_level") or None,
                    "malware_family": row.get("malware") or row.get("malware_printable") or None,
                    "reporter": row.get("reporter") or None,
                    "summary": row.get("threat_type") or row.get("malware_printable") or None,
                    "raw_payload": row,
                },
            )
        )

    return ParsedFeed(
        provider="abusech",
        feed_name="threatfox",
        indicators=indicators,
        row_count=row_count,
    )


def parse_urlhaus_recent_payload(payload: dict[str, Any]) -> ParsedFeed:
    """Parse the URLhaus recent-URLs API payload."""

    rows = payload.get("urls", []) if isinstance(payload, dict) else []
    indicators: list[ParsedIndicator] = []
    row_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_count += 1
        indicators.extend(_urlhaus_record_indicators(row, source_feed="urlhaus_recent"))

    return ParsedFeed(
        provider="abusech",
        feed_name="urlhaus_recent",
        indicators=indicators,
        row_count=row_count,
    )


def parse_threatfox_recent_payload(payload: dict[str, Any]) -> ParsedFeed:
    """Parse the ThreatFox recent-IOCs API payload."""

    rows = payload.get("data", []) if isinstance(payload, dict) else []
    indicators: list[ParsedIndicator] = []
    row_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_count += 1
        indicator_value = (row.get("ioc") or "").strip()
        indicator_type = _normalize_threatfox_type(row.get("ioc_type") or "")
        if not indicator_value or indicator_type is None:
            continue
        indicators.append(
            ParsedIndicator(
                indicator_type=indicator_type,
                indicator_value=indicator_value,
                observation={
                    "source_provider": "abusech",
                    "source_feed": "threatfox_recent",
                    "provider_record_id": row.get("id") or None,
                    "classification": row.get("threat_type") or None,
                    "confidence_label": row.get("confidence_level") or None,
                    "malware_family": row.get("malware") or row.get("malware_printable") or None,
                    "reporter": row.get("reporter") or None,
                    "summary": row.get("threat_type") or row.get("malware_printable") or None,
                    "raw_payload": row,
                },
            )
        )

    return ParsedFeed(
        provider="abusech",
        feed_name="threatfox_recent",
        indicators=indicators,
        row_count=row_count,
    )


def _read_zip_member_text(archive_path: Path, member_name: str) -> str:
    with ZipFile(archive_path) as archive:
        with archive.open(member_name) as member:
            return member.read().decode("utf-8")


def _urlhaus_record_indicators(
    row: dict[str, Any],
    *,
    source_feed: str = "urlhaus",
) -> list[ParsedIndicator]:
    indicators: list[ParsedIndicator] = []
    observation = {
        "source_provider": "abusech",
        "source_feed": source_feed,
        "provider_record_id": str(row.get("id") or ""),
        "classification": row.get("threat") or row.get("url_status") or None,
        "summary": row.get("url_status") or None,
        "raw_payload": row,
    }

    url = str(row.get("url") or "").strip()
    if url:
        indicators.append(
            ParsedIndicator(
                indicator_type="url",
                indicator_value=url,
                observation=observation,
            )
        )

    host = str(row.get("host") or "").strip()
    if host:
        indicators.append(
            ParsedIndicator(
                indicator_type=_host_indicator_type(host),
                indicator_value=host,
                observation=observation,
            )
        )

    for payload in row.get("payloads") or []:
        digest = str(payload.get("response_sha256") or "").strip()
        if not digest:
            continue
        indicators.append(
            ParsedIndicator(
                indicator_type="sha256",
                indicator_value=digest,
                observation={
                    **observation,
                    "summary": payload.get("filename") or observation["summary"],
                },
            )
        )

    return indicators


def _host_indicator_type(value: str) -> str:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return "domain"
    return "ip"


def _normalize_threatfox_type(raw_type: str) -> str | None:
    indicator_type = raw_type.strip().lower()
    if indicator_type in {"domain", "hostname", "url", "ip", "sha256"}:
        return indicator_type
    return None


async def _download_json_payload(
    *,
    url: str,
    auth_key: str,
    method: str,
    json_payload: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    if client is None:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as managed_client:
            return await _download_json_payload(
                url=url,
                auth_key=auth_key,
                method=method,
                json_payload=json_payload,
                client=managed_client,
            )

    headers = {"Auth-Key": auth_key}
    if method == "POST":
        response = await client.post(url, headers=headers, json=json_payload)
    else:
        response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
