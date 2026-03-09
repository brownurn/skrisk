from __future__ import annotations

import httpx
import pytest

from skrisk.config import Settings
from skrisk.services.search_index import SearchIndexService, build_skill_document


def _skill_detail() -> dict:
    return {
        "publisher": "openclaw",
        "repo": "openclaw",
        "skill_slug": "prose",
        "title": "Prose",
        "current_total_installs": 1500,
        "current_total_installs_observed_at": "2026-03-08T09:00:00+00:00",
        "impact_score": 60,
        "priority_score": 84,
        "sources": ["skills.sh", "skillsmp"],
        "source_count": 2,
        "install_breakdown": [
            {
                "source_name": "skills.sh",
                "weekly_installs": 1200,
                "source_url": "https://skills.sh/openclaw/openclaw/prose",
                "registry_rank": 3,
            },
            {
                "source_name": "skillsmp",
                "weekly_installs": 300,
                "source_url": "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
                "registry_rank": None,
            },
        ],
        "latest_snapshot": {
            "id": 14,
            "version_label": "main@abc123",
            "risk_report": {
                "severity": "high",
                "score": 72,
                "confidence": "likely",
                "categories": ["remote_code_execution"],
                "domains": ["drop.example"],
                "indicator_matches": [],
            },
        },
    }


def test_build_skill_document_includes_sources_and_install_breakdown() -> None:
    document = build_skill_document(_skill_detail())

    assert document["id"] == "openclaw/openclaw/prose"
    assert document["sources"] == ["skills.sh", "skillsmp"]
    assert document["source_count"] == 2
    assert document["current_total_installs"] == 1500
    assert document["install_breakdown"][0]["source_name"] == "skills.sh"


@pytest.mark.asyncio
async def test_search_index_validation_fails_when_required_service_is_unavailable(monkeypatch) -> None:
    settings = Settings(
        opensearch_url="http://opensearch.invalid:9200",
        require_search_runtime=True,
    )
    service = SearchIndexService(settings=settings)

    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("unreachable", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(RuntimeError, match="OpenSearch"):
        await service.validate_runtime()
