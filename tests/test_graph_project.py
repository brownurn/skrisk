from __future__ import annotations

import httpx
import pytest

from skrisk.config import Settings
from skrisk.services.graph_project import GraphProjectService, build_skill_graph_payload


def _skill_detail() -> dict:
    return {
        "publisher": "openclaw",
        "repo": "openclaw",
        "skill_slug": "prose",
        "title": "Prose",
        "sources": ["skills.sh", "skillsmp"],
        "source_entries": [
            {
                "source_name": "skills.sh",
                "source_url": "https://skills.sh/openclaw/openclaw/prose",
            },
            {
                "source_name": "skillsmp",
                "source_url": "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
            },
        ],
        "latest_snapshot": {
            "indicator_links": [
                {
                    "indicator_type": "domain",
                    "indicator_value": "drop.example",
                }
            ]
        },
    }


def test_build_skill_graph_payload_includes_seen_in_edges() -> None:
    graph = build_skill_graph_payload(_skill_detail())

    assert any(edge["type"] == "SEEN_IN" for edge in graph["edges"])
    assert any(node["type"] == "registry" and node["id"] == "registry:skills.sh" for node in graph["nodes"])


def test_build_skill_graph_payload_includes_infrastructure_relationships() -> None:
    detail = _skill_detail()
    detail["latest_snapshot"]["indicator_links"][0]["enrichments"] = [
        {
            "provider": "local_dns",
            "status": "completed",
            "normalized_payload": {
                "host": "drop.example",
                "resolved_ips": ["8.8.8.8"],
            },
        },
        {
            "provider": "mewhois",
            "status": "completed",
            "normalized_payload": {
                "registrar": "Example Registrar",
                "registrantOrg": "Bad Actors LLC",
                "nameservers": ["ns1.drop.example"],
            },
        },
        {
            "provider": "meip",
            "status": "completed",
            "normalized_payload": {
                "ip": "8.8.8.8",
                "asn": "AS15169",
                "asName": "Google LLC",
            },
        },
    ]

    graph = build_skill_graph_payload(detail)

    assert any(edge["type"] == "RESOLVES_TO" for edge in graph["edges"])
    assert any(edge["type"] == "REGISTERED_WITH" for edge in graph["edges"])
    assert any(edge["type"] == "REGISTERED_TO" for edge in graph["edges"])
    assert any(edge["type"] == "USES_NAMESERVER" for edge in graph["edges"])
    assert any(edge["type"] == "ANNOUNCED_BY" for edge in graph["edges"])


@pytest.mark.asyncio
async def test_graph_project_validation_fails_when_required_service_is_unavailable(monkeypatch) -> None:
    settings = Settings(
        neo4j_http_url="http://neo4j.invalid:7474",
        require_graph_runtime=True,
    )
    service = GraphProjectService(settings=settings)

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectError("unreachable", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(RuntimeError, match="Neo4j"):
        await service.validate_runtime()
