"""Selective VirusTotal triage with budget enforcement and caching."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from skrisk.collectors.virustotal import VirusTotalClient
from skrisk.config import Settings
from skrisk.storage.repository import SkillRepository


class VTTriageService:
    """Process queued VT lookups within the configured daily budget."""

    def __init__(self, *, session_factory, settings: Settings, client=None) -> None:
        self._repository = SkillRepository(session_factory)
        self._settings = settings
        self._client = client or (
            VirusTotalClient(settings.vt_api_key) if settings.vt_api_key else None
        )

    async def run_once(self) -> dict[str, int]:
        if self._client is None:
            raise ValueError("VT_APIKEY is required to run VT triage")

        now = datetime.now(UTC)
        used_today = await self._repository.count_indicator_enrichments_today(
            provider="virustotal",
            now=now,
        )
        remaining_budget = max(0, self._settings.vt_daily_budget - used_today)
        queue_items = await self._repository.list_vt_queue_items(status="queued")

        completed = 0
        skipped_budget = 0

        for queue_item in queue_items:
            if remaining_budget <= 0:
                skipped_budget += 1
                continue

            await self._repository.update_vt_queue_item(
                queue_item_id=queue_item["id"],
                status="running",
                attempt_count=queue_item["attempt_count"] + 1,
            )
            payload = await self._client.lookup(
                queue_item["indicator_type"],
                queue_item["indicator_value"],
            )
            archive_relative_path = self._archive_response(
                indicator_type=queue_item["indicator_type"],
                indicator_value=queue_item["indicator_value"],
                payload=payload,
                fetched_at=now,
            )
            await self._repository.record_indicator_enrichment(
                indicator_id=queue_item["indicator_id"],
                provider="virustotal",
                lookup_key=queue_item["indicator_value"],
                status="completed",
                summary=_summarize_payload(payload),
                archive_relative_path=archive_relative_path,
                normalized_payload=payload,
                requested_at=now,
                completed_at=now,
            )
            await self._repository.update_vt_queue_item(
                queue_item_id=queue_item["id"],
                status="completed",
            )
            remaining_budget -= 1
            completed += 1

        return {
            "lookups_completed": completed,
            "lookups_skipped_budget": skipped_budget,
        }

    def _archive_response(
        self,
        *,
        indicator_type: str,
        indicator_value: str,
        payload: dict,
        fetched_at: datetime,
    ) -> str:
        relative_path = (
            Path("intel")
            / "virustotal"
            / indicator_type
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / fetched_at.strftime("%H%M%SZ")
            / f"{sha256(f'{indicator_type}:{indicator_value}'.encode('utf-8')).hexdigest()}.json"
        )
        archive_path = self._settings.archive_root / relative_path
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return relative_path.as_posix()


def _summarize_payload(payload: dict) -> str:
    stats = payload.get("stats", {})
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)
    return f"malicious={malicious} suspicious={suspicious} harmless={harmless}"
