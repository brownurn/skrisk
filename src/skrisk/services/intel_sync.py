"""Bulk threat-intelligence synchronization services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable

from skrisk.collectors.abusech import (
    ParsedFeed,
    download_feed_archive,
    parse_threatfox_archive,
    parse_urlhaus_archive,
    write_archive_manifest,
)
from skrisk.config import Settings
from skrisk.storage.repository import SkillRepository


Parser = Callable[[Path], ParsedFeed]

URLHAUS_EXPORT_URL = "https://urlhaus-api.abuse.ch/files/exports/full.json.zip"
THREATFOX_EXPORT_URL = "https://threatfox-api.abuse.ch/files/exports/full.csv.zip"


@dataclass(slots=True, frozen=True)
class FeedDefinition:
    """Static metadata describing an Abuse.ch export."""

    feed_name: str
    source_url: str
    artifact_name: str
    parser: Parser


class AbuseChSyncService:
    """Archive, parse, and persist Abuse.ch feed exports."""

    def __init__(self, *, session_factory, settings: Settings) -> None:
        self._repository = SkillRepository(session_factory)
        self._settings = settings

    async def sync_all(
        self,
        *,
        urlhaus_bytes: bytes | None = None,
        threatfox_bytes: bytes | None = None,
    ) -> dict[str, int]:
        summary = {
            "feed_runs": 0,
            "indicators_upserted": 0,
            "observations_recorded": 0,
        }
        for definition, raw_bytes in (
            (
                FeedDefinition(
                    feed_name="urlhaus",
                    source_url=URLHAUS_EXPORT_URL,
                    artifact_name="full.json.zip",
                    parser=parse_urlhaus_archive,
                ),
                urlhaus_bytes,
            ),
            (
                FeedDefinition(
                    feed_name="threatfox",
                    source_url=THREATFOX_EXPORT_URL,
                    artifact_name="full.csv.zip",
                    parser=parse_threatfox_archive,
                ),
                threatfox_bytes,
            ),
        ):
            feed_summary = await self._sync_feed(definition=definition, raw_bytes=raw_bytes)
            for key, value in feed_summary.items():
                summary[key] += value
        return summary

    async def _sync_feed(
        self,
        *,
        definition: FeedDefinition,
        raw_bytes: bytes | None,
    ) -> dict[str, int]:
        fetched_at = datetime.now(UTC)
        if raw_bytes is None:
            if not self._settings.abusech_auth_key:
                raise ValueError("ABUSECH_AUTH_KEY is required to download Abuse.ch feeds")
            raw_bytes = await download_feed_archive(
                url=definition.source_url,
                auth_key=self._settings.abusech_auth_key,
            )

        destination = self._archive_destination(definition.feed_name, fetched_at)
        provisional_archive_path = destination / definition.artifact_name
        provisional_archive_path.parent.mkdir(parents=True, exist_ok=True)
        provisional_archive_path.write_bytes(raw_bytes)
        parsed = definition.parser(provisional_archive_path)
        archive_result = write_archive_manifest(
            provider="abusech",
            feed_name=definition.feed_name,
            fetched_at=fetched_at,
            raw_bytes=raw_bytes,
            row_count=parsed.row_count,
            destination=destination,
            source_url=definition.source_url,
            artifact_name=definition.artifact_name,
        )

        feed_run_id = await self._repository.record_intel_feed_run(
            provider="abusech",
            feed_name=definition.feed_name,
            source_url=definition.source_url,
            auth_mode="query-key",
            parser_version="v1",
            archive_sha256=archive_result.archive_sha256,
            archive_size_bytes=len(raw_bytes),
        )
        await self._repository.record_intel_feed_artifact(
            feed_run_id=feed_run_id,
            artifact_type="raw-archive",
            relative_path=self._relative_archive_path(archive_result.archive_path),
            sha256=archive_result.archive_sha256,
            size_bytes=archive_result.archive_path.stat().st_size,
            content_type="application/zip",
        )
        manifest_bytes = archive_result.manifest_path.read_bytes()
        await self._repository.record_intel_feed_artifact(
            feed_run_id=feed_run_id,
            artifact_type="manifest",
            relative_path=self._relative_archive_path(archive_result.manifest_path),
            sha256=sha256(manifest_bytes).hexdigest(),
            size_bytes=len(manifest_bytes),
            content_type="application/json",
        )

        indicators_upserted = 0
        observations_recorded = 0
        for item in parsed.indicators:
            indicator_id = await self._repository.upsert_indicator(
                item.indicator_type,
                item.indicator_value,
            )
            indicators_upserted += 1
            await self._repository.record_indicator_observation(
                indicator_id=indicator_id,
                feed_run_id=feed_run_id,
                source_provider=item.observation.get("source_provider", "abusech"),
                source_feed=item.observation.get("source_feed", definition.feed_name),
                provider_record_id=item.observation.get("provider_record_id"),
                classification=item.observation.get("classification"),
                confidence_label=item.observation.get("confidence_label"),
                summary=item.observation.get("summary"),
                malware_family=item.observation.get("malware_family"),
                threat_type=item.observation.get("threat_type"),
                reporter=item.observation.get("reporter"),
                raw_payload=item.observation.get("raw_payload"),
            )
            observations_recorded += 1

        return {
            "feed_runs": 1,
            "indicators_upserted": indicators_upserted,
            "observations_recorded": observations_recorded,
        }

    def _archive_destination(self, feed_name: str, fetched_at: datetime) -> Path:
        timestamp = fetched_at.strftime("%H%M%SZ")
        return (
            self._settings.archive_root
            / "intel"
            / "abusech"
            / feed_name
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / timestamp
        )

    def _relative_archive_path(self, path: Path) -> str:
        return path.relative_to(self._settings.archive_root).as_posix()
