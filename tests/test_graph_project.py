from __future__ import annotations

import asyncio
import httpx
import pytest

from skrisk.config import Settings
from skrisk.services.graph_project import (
    GraphProjectService,
    _chunked_statements,
    build_skill_graph_payload,
)


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


def test_chunked_statements_splits_large_statement_batches() -> None:
    statements = [{"statement": f"RETURN {idx}"} for idx in range(7)]

    chunks = _chunked_statements(statements, max_statements_per_request=3)

    assert chunks == [
        [{"statement": "RETURN 0"}, {"statement": "RETURN 1"}, {"statement": "RETURN 2"}],
        [{"statement": "RETURN 3"}, {"statement": "RETURN 4"}, {"statement": "RETURN 5"}],
        [{"statement": "RETURN 6"}],
    ]


@pytest.mark.asyncio
async def test_project_payload_sends_bounded_statement_batches(monkeypatch) -> None:
    settings = Settings(neo4j_http_url="http://neo4j.invalid:7474")
    service = GraphProjectService(settings=settings)

    async def fake_ensure_runtime() -> None:
        return None

    calls: list[list[dict[str, object]]] = []

    async def fake_post(self, url, **kwargs):
        calls.append(kwargs["json"]["statements"])
        return httpx.Response(200, request=httpx.Request("POST", url), json={"results": [], "errors": []})

    monkeypatch.setattr(service, "ensure_runtime", fake_ensure_runtime)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    graph = {
        "nodes": [
            {"id": f"node:{idx}", "type": "skill", "properties": {"value": idx}}
            for idx in range(3)
        ],
        "edges": [
            {"from": "node:0", "to": f"node:{idx}", "type": "REL"}
            for idx in range(1, 3)
        ],
    }

    statement_count = await service.project_payload(
        graph,
        max_statements_per_request=2,
    )

    assert statement_count == 5
    assert [len(batch) for batch in calls] == [2, 2, 1]


@pytest.mark.asyncio
async def test_project_skill_coordinates_runs_workers_concurrently(monkeypatch) -> None:
    settings = Settings(neo4j_http_url="http://neo4j.invalid:7474")
    service = GraphProjectService(settings=settings)

    coords = [
        {"publisher": "p", "repo": "r", "skill_slug": f"s{idx}"}
        for idx in range(6)
    ]

    active = 0
    max_active = 0

    async def fake_ensure_runtime() -> None:
        return None

    async def fake_get_skill_detail(*, publisher: str, repo: str, skill_slug: str) -> dict:
        await asyncio.sleep(0.01)
        return {
            "publisher": publisher,
            "repo": repo,
            "skill_slug": skill_slug,
            "title": skill_slug,
            "source_entries": [],
            "latest_snapshot": {"indicator_links": []},
        }

    async def fake_project_payload(graph, *, max_statements_per_request=500, client=None, ensure_runtime=True):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1

    service._repository = type(
        "RepoStub",
        (),
        {"get_skill_detail": staticmethod(fake_get_skill_detail)},
    )()
    monkeypatch.setattr(service, "ensure_runtime", fake_ensure_runtime)
    monkeypatch.setattr(service, "project_payload", fake_project_payload)

    summary = await service.project_skill_coordinates(
        coords,
        concurrency=3,
        max_statements_per_request=10,
    )

    assert summary["skills_projected"] == 6
    assert summary["skills_failed"] == 0
    assert summary["statements_total"] == 6
    assert max_active >= 2
