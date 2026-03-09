"""Neo4j graph projection helpers for SK Risk."""

from __future__ import annotations

from base64 import b64encode
from typing import Any

import httpx

from skrisk.config import Settings
from skrisk.storage.repository import SkillRepository


def build_skill_graph_payload(skill_detail: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    skill_id = f"skill:{_skill_coordinate(skill_detail)}"
    repo_id = f"repo:{skill_detail.get('publisher')}/{skill_detail.get('repo')}"

    nodes.append(
        {
            "id": skill_id,
            "type": "skill",
            "properties": {
                "publisher": skill_detail.get("publisher"),
                "repo": skill_detail.get("repo"),
                "skill_slug": skill_detail.get("skill_slug"),
                "title": skill_detail.get("title"),
            },
        }
    )
    nodes.append(
        {
            "id": repo_id,
            "type": "repo",
            "properties": {
                "publisher": skill_detail.get("publisher"),
                "repo": skill_detail.get("repo"),
            },
        }
    )
    edges.append({"from": skill_id, "to": repo_id, "type": "HOSTED_IN"})

    for source_entry in skill_detail.get("source_entries") or []:
        source_name = str(source_entry.get("source_name") or "")
        registry_id = f"registry:{source_name}"
        nodes.append(
            {
                "id": registry_id,
                "type": "registry",
                "properties": {
                    "name": source_name,
                    "source_url": source_entry.get("source_url"),
                },
            }
        )
        edges.append({"from": skill_id, "to": registry_id, "type": "SEEN_IN"})

    latest_snapshot = skill_detail.get("latest_snapshot") or {}
    for indicator in latest_snapshot.get("indicator_links") or []:
        indicator_type = str(indicator.get("indicator_type") or "")
        indicator_value = str(indicator.get("indicator_value") or "")
        if not indicator_type or not indicator_value:
            continue
        indicator_id = f"indicator:{indicator_type}:{indicator_value}"
        nodes.append(
            {
                "id": indicator_id,
                "type": "indicator",
                "properties": {
                    "indicator_type": indicator_type,
                    "indicator_value": indicator_value,
                },
            }
        )
        edges.append({"from": skill_id, "to": indicator_id, "type": "EMITS"})

    return {
        "nodes": _dedupe_graph_nodes(nodes),
        "edges": _dedupe_graph_edges(edges),
    }


class GraphProjectService:
    """Project canonical skill relationships into Neo4j via HTTP transactions."""

    def __init__(self, *, settings: Settings, session_factory=None) -> None:
        self._settings = settings
        self._repository = SkillRepository(session_factory) if session_factory is not None else None

    async def validate_runtime(self) -> None:
        if not self._settings.require_graph_runtime:
            return
        await self.ensure_runtime()

    async def ensure_runtime(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._transaction_url,
                    headers=self._headers(),
                    json={"statements": [{"statement": "RETURN 1 AS ok"}]},
                )
                response.raise_for_status()
        except Exception as exc:  # pragma: no cover - exercised through tests via monkeypatch
            raise RuntimeError(
                f"Neo4j runtime is required but unavailable at {self._settings.neo4j_http_url}"
            ) from exc

    async def project_all(self) -> dict[str, int]:
        await self.validate_runtime()
        if self._repository is None:
            raise ValueError("session_factory is required to build graph payloads")

        skill_rows = await self._repository.list_skills(limit=0)
        statements: list[dict[str, Any]] = []
        projected_skills = 0
        for row in skill_rows:
            detail = await self._repository.get_skill_detail(
                publisher=row["publisher"],
                repo=row["repo"],
                skill_slug=row["skill_slug"],
            )
            if detail is None:
                continue
            projected_skills += 1
            graph = build_skill_graph_payload(detail)
            statements.extend(_graph_statements(graph))

        if not statements:
            return {"skills_projected": 0}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._transaction_url,
                headers=self._headers(),
                json={"statements": statements},
            )
            response.raise_for_status()
        return {"skills_projected": projected_skills}

    async def project_payload(self, graph: dict[str, Any]) -> int:
        await self.ensure_runtime()
        statements = _graph_statements(graph)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._transaction_url,
                headers=self._headers(),
                json={"statements": statements},
            )
            response.raise_for_status()
        return len(statements)

    @property
    def _transaction_url(self) -> str:
        return (
            f"{self._settings.neo4j_http_url.rstrip('/')}/db/"
            f"{self._settings.neo4j_database}/tx/commit"
        )

    def _headers(self) -> dict[str, str]:
        auth = b64encode(
            f"{self._settings.neo4j_user}:{self._settings.neo4j_password}".encode("utf-8")
        ).decode("ascii")
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }


def _skill_coordinate(skill_detail: dict[str, Any]) -> str:
    return "/".join(
        [
            str(skill_detail.get("publisher") or ""),
            str(skill_detail.get("repo") or ""),
            str(skill_detail.get("skill_slug") or ""),
        ]
    )


def _dedupe_graph_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for node in nodes:
        deduped[node["id"]] = node
    return list(deduped.values())


def _dedupe_graph_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        deduped[(edge["from"], edge["to"], edge["type"])] = edge
    return list(deduped.values())


def _graph_statements(graph: dict[str, Any]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        statements.append(
            {
                "statement": (
                    f"MERGE (n:{node['type'].capitalize()} {{id: $id}}) "
                    "SET n += $properties"
                ),
                "parameters": {
                    "id": node["id"],
                    "properties": node["properties"],
                },
            }
        )
    for edge in graph["edges"]:
        statements.append(
            {
                "statement": (
                    "MATCH (a {id: $from_id}), (b {id: $to_id}) "
                    f"MERGE (a)-[r:{edge['type']}]->(b)"
                ),
                "parameters": {
                    "from_id": edge["from"],
                    "to_id": edge["to"],
                },
            }
        )
    return statements
