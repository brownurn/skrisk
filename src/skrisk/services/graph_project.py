"""Neo4j graph projection helpers for SK Risk."""

from __future__ import annotations

from base64 import b64encode
import asyncio
from collections.abc import Callable
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
        for enrichment in indicator.get("enrichments") or []:
            if enrichment.get("status") != "completed":
                continue
            payload = enrichment.get("normalized_payload") or {}
            provider = enrichment.get("provider")
            if provider == "local_dns":
                for resolved_ip in payload.get("resolved_ips") or []:
                    resolved_ip_value = str(resolved_ip or "")
                    if not resolved_ip_value:
                        continue
                    resolved_ip_id = f"indicator:ip:{resolved_ip_value}"
                    nodes.append(
                        {
                            "id": resolved_ip_id,
                            "type": "indicator",
                            "properties": {
                                "indicator_type": "ip",
                                "indicator_value": resolved_ip_value,
                            },
                        }
                    )
                    edges.append({"from": indicator_id, "to": resolved_ip_id, "type": "RESOLVES_TO"})
                    profile = (payload.get("resolved_ip_profiles") or {}).get(resolved_ip_value) or {}
                    asn = str(profile.get("asn") or "").strip()
                    if asn:
                        asn_id = f"asn:{asn}"
                        nodes.append(
                            {
                                "id": asn_id,
                                "type": "asn",
                                "properties": {
                                    "asn": asn,
                                    "as_name": profile.get("asName"),
                                },
                            }
                        )
                        edges.append({"from": resolved_ip_id, "to": asn_id, "type": "ANNOUNCED_BY"})
            if provider == "mewhois":
                registrar = str(payload.get("registrar") or "").strip()
                if registrar:
                    registrar_id = f"registrar:{registrar.casefold()}"
                    nodes.append(
                        {
                            "id": registrar_id,
                            "type": "registrar",
                            "properties": {"name": registrar},
                        }
                    )
                    edges.append({"from": indicator_id, "to": registrar_id, "type": "REGISTERED_WITH"})
                registrant_org = str(payload.get("registrantOrg") or "").strip()
                if registrant_org:
                    org_id = f"organization:{registrant_org.casefold()}"
                    nodes.append(
                        {
                            "id": org_id,
                            "type": "organization",
                            "properties": {"name": registrant_org},
                        }
                    )
                    edges.append({"from": indicator_id, "to": org_id, "type": "REGISTERED_TO"})
                for nameserver in payload.get("nameservers") or []:
                    nameserver_value = str(nameserver or "").strip()
                    if not nameserver_value:
                        continue
                    nameserver_id = f"nameserver:{nameserver_value.casefold()}"
                    nodes.append(
                        {
                            "id": nameserver_id,
                            "type": "nameserver",
                            "properties": {"hostname": nameserver_value},
                        }
                    )
                    edges.append({"from": indicator_id, "to": nameserver_id, "type": "USES_NAMESERVER"})
            if provider == "meip":
                asn = str(payload.get("asn") or "").strip()
                if asn:
                    asn_id = f"asn:{asn}"
                    nodes.append(
                        {
                            "id": asn_id,
                            "type": "asn",
                            "properties": {
                                "asn": asn,
                                "as_name": payload.get("asName"),
                            },
                        }
                    )
                    edges.append({"from": indicator_id, "to": asn_id, "type": "ANNOUNCED_BY"})

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
        return await self.project_skill_coordinates(skill_rows)

    async def project_payload(
        self,
        graph: dict[str, Any],
        *,
        max_statements_per_request: int = 500,
        client: httpx.AsyncClient | None = None,
        ensure_runtime: bool = True,
    ) -> int:
        if ensure_runtime:
            await self.ensure_runtime()
        statements = _graph_statements(graph)
        if not statements:
            return 0

        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
        assert client is not None
        try:
            for statement_chunk in _chunked_statements(
                statements,
                max_statements_per_request=max_statements_per_request,
            ):
                response = await client.post(
                    self._transaction_url,
                    headers=self._headers(),
                    json={"statements": statement_chunk},
                )
                response.raise_for_status()
        finally:
            if owns_client:
                await client.aclose()
        return len(statements)

    async def clear_graph(self) -> None:
        await self.ensure_runtime()
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(
                self._transaction_url,
                headers=self._headers(),
                json={"statements": [{"statement": "MATCH (n) DETACH DELETE n"}]},
            )
            response.raise_for_status()

    async def project_skill_coordinates(
        self,
        coordinates: list[dict[str, Any]],
        *,
        concurrency: int = 8,
        max_statements_per_request: int = 500,
        progress_callback: Callable[[dict[str, int | str]], None] | None = None,
    ) -> dict[str, int]:
        await self.ensure_runtime()
        if self._repository is None:
            raise ValueError("session_factory is required to project skill coordinates")
        if not coordinates:
            return {"skills_projected": 0, "skills_failed": 0, "statements_total": 0}

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for coordinate in coordinates:
            queue.put_nowait(coordinate)
        worker_count = max(1, min(concurrency, len(coordinates)))
        for _ in range(worker_count):
            queue.put_nowait(None)

        stats = {
            "skills_projected": 0,
            "skills_failed": 0,
            "statements_total": 0,
        }
        lock = asyncio.Lock()

        async def worker() -> None:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
                while True:
                    coordinate = await queue.get()
                    try:
                        if coordinate is None:
                            return
                        detail = await self._repository.get_skill_detail(
                            publisher=str(coordinate["publisher"]),
                            repo=str(coordinate["repo"]),
                            skill_slug=str(coordinate["skill_slug"]),
                        )
                        if detail is None:
                            async with lock:
                                stats["skills_failed"] += 1
                            continue
                        graph = build_skill_graph_payload(detail)
                        statement_count = await self.project_payload(
                            graph,
                            client=client,
                            ensure_runtime=False,
                            max_statements_per_request=max_statements_per_request,
                        )
                        async with lock:
                            stats["skills_projected"] += 1
                            stats["statements_total"] += statement_count
                            if progress_callback is not None:
                                progress_callback(
                                    {
                                        "skills_projected": stats["skills_projected"],
                                        "skills_failed": stats["skills_failed"],
                                        "statements_total": stats["statements_total"],
                                        "last_skill": "/".join(
                                            [
                                                str(coordinate["publisher"]),
                                                str(coordinate["repo"]),
                                                str(coordinate["skill_slug"]),
                                            ]
                                        ),
                                    }
                                )
                    except Exception:
                        async with lock:
                            stats["skills_failed"] += 1
                            if progress_callback is not None:
                                progress_callback(
                                    {
                                        "skills_projected": stats["skills_projected"],
                                        "skills_failed": stats["skills_failed"],
                                        "statements_total": stats["statements_total"],
                                        "last_skill": "/".join(
                                            [
                                                str(coordinate["publisher"]),
                                                str(coordinate["repo"]),
                                                str(coordinate["skill_slug"]),
                                            ]
                                        ),
                                    }
                                )
                    finally:
                        queue.task_done()

        tasks = [asyncio.create_task(worker()) for _ in range(worker_count)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
        return stats

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


def _chunked_statements(
    statements: list[dict[str, Any]],
    *,
    max_statements_per_request: int,
) -> list[list[dict[str, Any]]]:
    if max_statements_per_request <= 0:
        return [statements]
    return [
        statements[index : index + max_statements_per_request]
        for index in range(0, len(statements), max_statements_per_request)
    ]
