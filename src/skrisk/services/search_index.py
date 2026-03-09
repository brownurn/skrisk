"""OpenSearch projection helpers for SK Risk."""

from __future__ import annotations

import json
from typing import Any

import httpx

from skrisk.config import Settings
from skrisk.storage.repository import SkillRepository


def build_skill_document(skill_detail: dict[str, Any]) -> dict[str, Any]:
    latest_snapshot = skill_detail.get("latest_snapshot") or {}
    risk_report = latest_snapshot.get("risk_report") or {}
    return {
        "id": _skill_coordinate(skill_detail),
        "publisher": skill_detail.get("publisher"),
        "repo": skill_detail.get("repo"),
        "skill_slug": skill_detail.get("skill_slug"),
        "title": skill_detail.get("title"),
        "sources": list(skill_detail.get("sources") or []),
        "source_count": int(skill_detail.get("source_count") or 0),
        "current_total_installs": skill_detail.get("current_total_installs"),
        "current_total_installs_observed_at": skill_detail.get(
            "current_total_installs_observed_at"
        ),
        "impact_score": int(skill_detail.get("impact_score") or 0),
        "priority_score": int(skill_detail.get("priority_score") or 0),
        "install_breakdown": list(skill_detail.get("install_breakdown") or []),
        "severity": risk_report.get("severity"),
        "risk_score": int(risk_report.get("score") or 0),
        "confidence": risk_report.get("confidence"),
        "categories": list(risk_report.get("categories") or []),
        "domains": list(risk_report.get("domains") or []),
        "version_label": latest_snapshot.get("version_label"),
        "snapshot_id": latest_snapshot.get("id"),
    }


class SearchIndexService:
    """Project canonical skill summaries into OpenSearch."""

    def __init__(self, *, settings: Settings, session_factory=None) -> None:
        self._settings = settings
        self._repository = SkillRepository(session_factory) if session_factory is not None else None

    async def validate_runtime(self) -> None:
        if not self._settings.require_search_runtime:
            return
        await self.ensure_runtime()

    async def ensure_runtime(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._settings.opensearch_url)
                response.raise_for_status()
        except Exception as exc:  # pragma: no cover - exercised through tests via monkeypatch
            raise RuntimeError(
                f"OpenSearch runtime is required but unavailable at {self._settings.opensearch_url}"
            ) from exc

    async def index_all(self) -> dict[str, int]:
        await self.validate_runtime()
        if self._repository is None:
            raise ValueError("session_factory is required to build search documents")

        skill_rows = await self._repository.list_skills(limit=0)
        documents = [build_skill_document(row) for row in skill_rows]
        if not documents:
            return {"documents_indexed": 0}

        await self.bulk_index(documents)
        return {"documents_indexed": len(documents)}

    async def _ensure_index(self) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{self._settings.opensearch_url}/{self._settings.opensearch_index_name}",
                json={
                    "mappings": {
                        "properties": {
                            "publisher": {"type": "keyword"},
                            "repo": {"type": "keyword"},
                            "skill_slug": {"type": "keyword"},
                            "sources": {"type": "keyword"},
                            "source_count": {"type": "integer"},
                            "current_total_installs": {"type": "long"},
                            "impact_score": {"type": "integer"},
                            "priority_score": {"type": "integer"},
                            "severity": {"type": "keyword"},
                            "risk_score": {"type": "integer"},
                            "categories": {"type": "keyword"},
                            "domains": {"type": "keyword"},
                        }
                    }
                },
                headers={"Content-Type": "application/json"},
            )
            if response.status_code not in {200, 201, 400}:
                response.raise_for_status()

    async def bulk_index(self, documents: list[dict[str, Any]]) -> int:
        await self.ensure_runtime()
        await self._ensure_index()
        lines: list[str] = []
        for document in documents:
            lines.append(
                json.dumps(
                    {
                        "index": {
                            "_index": self._settings.opensearch_index_name,
                            "_id": document["id"],
                        }
                    }
                )
            )
            lines.append(json.dumps(document))

        payload = "\n".join(lines) + "\n"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._settings.opensearch_url}/_bulk",
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
            response.raise_for_status()
        return len(documents)


def _skill_coordinate(skill_detail: dict[str, Any]) -> str:
    return "/".join(
        [
            str(skill_detail.get("publisher") or ""),
            str(skill_detail.get("repo") or ""),
            str(skill_detail.get("skill_slug") or ""),
        ]
    )
