"""Infrastructure enrichment using mewhois, meip, and local DNS resolution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import socket
from typing import Any

from skrisk.collectors.infrastructure import MeipClient, MewhoisClient
from skrisk.config import Settings
from skrisk.storage.repository import SkillRepository


class InfrastructureEnrichmentService:
    """Enrich domain and IP indicators with infrastructure context."""

    def __init__(
        self,
        *,
        session_factory,
        settings: Settings,
        whois_client=None,
        ip_client=None,
        resolver=None,
    ) -> None:
        self._repository = SkillRepository(session_factory)
        self._settings = settings
        self._whois_client = whois_client or MewhoisClient(base_url=settings.mewhois_url)
        self._ip_client = ip_client or MeipClient(base_url=settings.meip_url)
        self._resolver = resolver or _resolve_hostname

    async def run_once(
        self,
        *,
        limit: int = 100,
        requested_at: datetime | None = None,
    ) -> dict[str, int]:
        requested_at = requested_at or datetime.now(UTC)
        candidates = await self._repository.list_infrastructure_candidates(limit=limit)
        self._settings.archive_root.mkdir(parents=True, exist_ok=True)

        ip_provider_available = await self._provider_available(self._ip_client)
        counts = {
            "candidates_processed": 0,
            "whois_completed": 0,
            "dns_completed": 0,
            "ip_completed": 0,
            "ip_provider_unavailable": 0,
            "failed": 0,
        }
        ip_completion_cache: dict[str, bool] = {}

        for candidate in candidates:
            counts["candidates_processed"] += 1
            indicator_id = candidate["id"]
            indicator_type = candidate["indicator_type"]
            indicator_value = candidate["indicator_value"]
            completed_providers = set(candidate["completed_providers"])

            if indicator_type == "domain":
                if "local_dns" not in completed_providers:
                    try:
                        resolved_ips = await self._resolve_ips(indicator_value)
                        ip_profiles: dict[str, dict[str, Any]] = {}
                        if resolved_ips:
                            for ip in resolved_ips:
                                ip_indicator_id = await self._repository.upsert_indicator("ip", ip)
                                if ip_provider_available:
                                    profile, was_completed = await self._enrich_ip_indicator(
                                        indicator_id=ip_indicator_id,
                                        ip=ip,
                                        requested_at=requested_at,
                                        completion_cache=ip_completion_cache,
                                    )
                                    if profile is not None:
                                        ip_profiles[ip] = profile
                                    if not was_completed and profile is not None:
                                        counts["ip_completed"] += 1
                                else:
                                    counts["ip_provider_unavailable"] += 1

                        dns_payload = {
                            "host": indicator_value,
                            "resolved_ips": resolved_ips,
                            "resolved_ip_profiles": ip_profiles,
                        }
                        await self._repository.record_indicator_enrichment(
                            indicator_id=indicator_id,
                            provider="local_dns",
                            lookup_key=indicator_value,
                            status="completed",
                            summary=_dns_summary(dns_payload),
                            archive_relative_path=self._archive_payload(
                                provider="local_dns",
                                lookup_key=indicator_value,
                                payload=dns_payload,
                                fetched_at=requested_at,
                            ),
                            normalized_payload=dns_payload,
                            requested_at=requested_at,
                            completed_at=requested_at,
                        )
                        counts["dns_completed"] += 1
                    except Exception:
                        counts["failed"] += 1

                if "mewhois" not in completed_providers:
                    try:
                        payload = await self._whois_client.lookup_domain(indicator_value)
                        await self._repository.record_indicator_enrichment(
                            indicator_id=indicator_id,
                            provider="mewhois",
                            lookup_key=indicator_value,
                            status="completed",
                            summary=_whois_summary(payload),
                            archive_relative_path=self._archive_payload(
                                provider="mewhois",
                                lookup_key=indicator_value,
                                payload=payload,
                                fetched_at=requested_at,
                            ),
                            normalized_payload=payload,
                            requested_at=requested_at,
                            completed_at=requested_at,
                        )
                        counts["whois_completed"] += 1
                    except Exception:
                        counts["failed"] += 1

            elif indicator_type == "ip":
                if not ip_provider_available:
                    counts["ip_provider_unavailable"] += 1
                    continue

                try:
                    _, was_completed = await self._enrich_ip_indicator(
                        indicator_id=indicator_id,
                        ip=indicator_value,
                        requested_at=requested_at,
                        completion_cache=ip_completion_cache,
                    )
                    if not was_completed:
                        counts["ip_completed"] += 1
                except Exception:
                    counts["failed"] += 1

        return counts

    async def _provider_available(self, client: Any) -> bool:
        health_check = getattr(client, "health_check", None)
        if health_check is None:
            return True
        return bool(await health_check())

    async def _enrich_ip_indicator(
        self,
        *,
        indicator_id: int,
        ip: str,
        requested_at: datetime,
        completion_cache: dict[str, bool],
    ) -> tuple[dict[str, Any] | None, bool]:
        if ip in completion_cache:
            already_completed = completion_cache[ip]
            if already_completed:
                detail = await self._repository.get_indicator_detail("ip", ip)
                enrichment = _latest_completed_enrichment(detail, provider="meip")
                return (
                    enrichment.get("normalized_payload") if enrichment else None,
                    True,
                )

        if await self._repository.indicator_has_completed_enrichment(
            indicator_id=indicator_id,
            provider="meip",
        ):
            completion_cache[ip] = True
            detail = await self._repository.get_indicator_detail("ip", ip)
            enrichment = _latest_completed_enrichment(detail, provider="meip")
            return (
                enrichment.get("normalized_payload") if enrichment else None,
                True,
            )

        payload = await self._ip_client.lookup_ip(ip)
        await self._repository.record_indicator_enrichment(
            indicator_id=indicator_id,
            provider="meip",
            lookup_key=ip,
            status="completed",
            summary=_ip_summary(payload),
            archive_relative_path=self._archive_payload(
                provider="meip",
                lookup_key=ip,
                payload=payload,
                fetched_at=requested_at,
            ),
            normalized_payload=payload,
            requested_at=requested_at,
            completed_at=requested_at,
        )
        completion_cache[ip] = True
        return payload, False

    async def _resolve_ips(self, hostname: str) -> list[str]:
        resolved = self._resolver(hostname)
        if asyncio.iscoroutine(resolved):
            resolved = await resolved
        return sorted({str(value) for value in resolved if value})

    def _archive_payload(
        self,
        *,
        provider: str,
        lookup_key: str,
        payload: dict[str, Any],
        fetched_at: datetime,
    ) -> str:
        relative_path = (
            Path("intel")
            / "infrastructure"
            / provider
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / fetched_at.strftime("%H%M%SZ")
            / f"{sha256(f'{provider}:{lookup_key}'.encode('utf-8')).hexdigest()}.json"
        )
        archive_path = self._settings.archive_root / relative_path
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return relative_path.as_posix()


async def _resolve_hostname(hostname: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        address_info = await loop.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return []

    addresses: set[str] = set()
    for family, _type, _proto, _canonname, sockaddr in address_info:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        if not sockaddr:
            continue
        addresses.add(str(sockaddr[0]))
    return sorted(addresses)


def _latest_completed_enrichment(detail: dict[str, Any] | None, *, provider: str) -> dict[str, Any] | None:
    if not detail:
        return None
    completed = [
        enrichment
        for enrichment in detail.get("enrichments") or []
        if enrichment.get("provider") == provider and enrichment.get("status") == "completed"
    ]
    if not completed:
        return None
    return completed[-1]


def _dns_summary(payload: dict[str, Any]) -> str:
    resolved_ips = payload.get("resolved_ips") or []
    return "resolved_ips=" + ",".join(str(value) for value in resolved_ips)


def _whois_summary(payload: dict[str, Any]) -> str:
    registrar = payload.get("registrar") or "unknown"
    registrant = payload.get("registrantOrg") or "unknown"
    country = payload.get("registrantCountry") or "unknown"
    return f"registrar={registrar} registrant={registrant} country={country}"


def _ip_summary(payload: dict[str, Any]) -> str:
    asn = payload.get("asn") or "unknown"
    as_name = payload.get("asName") or "unknown"
    flags = ",".join(payload.get("flags") or [])
    return f"asn={asn} as_name={as_name} flags={flags}"
