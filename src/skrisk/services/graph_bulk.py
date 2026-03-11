"""Offline Neo4j bulk export/import helpers for SK Risk."""

from __future__ import annotations

import asyncio
from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import shlex

import asyncpg
import httpx

from skrisk.config import Settings


@dataclass(frozen=True)
class GraphCsvSpec:
    filename: str
    query: str


_GRAPH_CSV_SPECS: tuple[GraphCsvSpec, ...] = (
    GraphCsvSpec(
        "skills.csv",
        """
        SELECT
            skill_graph_id AS "id:ID",
            publisher,
            repo,
            skill_slug,
            title,
            severity,
            risk_score,
            confidence,
            total_installs
        FROM tmp_graph_skills
        ORDER BY skill_pk
        """,
    ),
    GraphCsvSpec(
        "repos.csv",
        """
        SELECT DISTINCT
            repo_graph_id AS "id:ID",
            publisher,
            repo,
            source_url
        FROM tmp_graph_skills
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "registries.csv",
        """
        SELECT
            'registry:' || rs.name AS "id:ID",
            rs.name AS name,
            rs.base_url AS base_url
        FROM registry_sources rs
        ORDER BY rs.id
        """,
    ),
    GraphCsvSpec(
        "indicators.csv",
        """
        SELECT DISTINCT
            graph_id AS "id:ID",
            indicator_type,
            indicator_value,
            normalized_value
        FROM (
            SELECT
                indicator_graph_id AS graph_id,
                indicator_type,
                indicator_value,
                normalized_value
            FROM tmp_graph_latest_indicators
            UNION ALL
            SELECT
                resolved_ip_graph_id AS graph_id,
                'ip' AS indicator_type,
                resolved_ip AS indicator_value,
                resolved_ip AS normalized_value
            FROM tmp_graph_resolved_ips
        ) AS indicator_nodes
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "asns.csv",
        """
        SELECT DISTINCT
            'asn:' || asn AS "id:ID",
            asn,
            as_name
        FROM (
            SELECT
                asn,
                as_name
            FROM tmp_graph_meip
            WHERE asn IS NOT NULL
            UNION ALL
            SELECT
                asn,
                as_name
            FROM tmp_graph_resolved_ips
            WHERE asn IS NOT NULL
        ) AS asn_nodes
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "registrars.csv",
        """
        SELECT DISTINCT
            'registrar:' || lower(registrar_name) AS "id:ID",
            registrar_name AS name
        FROM tmp_graph_mewhois
        WHERE registrar_name IS NOT NULL
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "organizations.csv",
        """
        SELECT DISTINCT
            'organization:' || lower(registrant_org) AS "id:ID",
            registrant_org AS name
        FROM tmp_graph_mewhois
        WHERE registrant_org IS NOT NULL
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "nameservers.csv",
        """
        SELECT DISTINCT
            'nameserver:' || lower(nameserver) AS "id:ID",
            nameserver AS hostname
        FROM tmp_graph_mewhois_nameservers
        ORDER BY "id:ID"
        """,
    ),
    GraphCsvSpec(
        "hosted_in.csv",
        """
        SELECT DISTINCT
            skill_graph_id AS ":START_ID",
            repo_graph_id AS ":END_ID"
        FROM tmp_graph_skills
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "seen_in.csv",
        """
        SELECT DISTINCT
            tgs.skill_graph_id AS ":START_ID",
            'registry:' || rs.name AS ":END_ID"
        FROM skill_source_entries sse
        JOIN registry_sources rs
          ON rs.id = sse.registry_source_id
        JOIN tmp_graph_skills tgs
          ON tgs.skill_pk = sse.skill_id
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "emits.csv",
        """
        SELECT DISTINCT
            tgs.skill_graph_id AS ":START_ID",
            tgli.indicator_graph_id AS ":END_ID"
        FROM tmp_graph_skills tgs
        JOIN skill_indicator_links sil
          ON sil.skill_snapshot_id = tgs.latest_snapshot_id
        JOIN tmp_graph_latest_indicators tgli
          ON tgli.indicator_pk = sil.indicator_id
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "resolves_to.csv",
        """
        SELECT DISTINCT
            source_indicator_graph_id AS ":START_ID",
            resolved_ip_graph_id AS ":END_ID"
        FROM tmp_graph_resolved_ips
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "announced_by.csv",
        """
        SELECT DISTINCT
            start_graph_id AS ":START_ID",
            'asn:' || asn AS ":END_ID"
        FROM (
            SELECT
                resolved_ip_graph_id AS start_graph_id,
                asn
            FROM tmp_graph_resolved_ips
            WHERE asn IS NOT NULL
            UNION ALL
            SELECT
                indicator_graph_id AS start_graph_id,
                asn
            FROM tmp_graph_meip
            WHERE asn IS NOT NULL
        ) AS announced_by_edges
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "registered_with.csv",
        """
        SELECT DISTINCT
            indicator_graph_id AS ":START_ID",
            'registrar:' || lower(registrar_name) AS ":END_ID"
        FROM tmp_graph_mewhois
        WHERE registrar_name IS NOT NULL
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "registered_to.csv",
        """
        SELECT DISTINCT
            indicator_graph_id AS ":START_ID",
            'organization:' || lower(registrant_org) AS ":END_ID"
        FROM tmp_graph_mewhois
        WHERE registrant_org IS NOT NULL
        ORDER BY 1, 2
        """,
    ),
    GraphCsvSpec(
        "uses_nameserver.csv",
        """
        SELECT DISTINCT
            indicator_graph_id AS ":START_ID",
            'nameserver:' || lower(nameserver) AS ":END_ID"
        FROM tmp_graph_mewhois_nameservers
        ORDER BY 1, 2
        """,
    ),
)


class GraphBulkImportService:
    """Export graph CSVs from Postgres and rebuild Neo4j via neo4j-admin."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def rebuild(
        self,
        *,
        bundle_dir: Path | None = None,
        threads: int,
        max_off_heap_memory: str,
        export_only: bool,
        import_only: bool,
    ) -> dict[str, object]:
        if export_only and import_only:
            raise ValueError("Choose either export-only or import-only, not both")

        active_bundle_dir = bundle_dir
        summary: dict[str, object] = {}
        if not import_only:
            active_bundle_dir = active_bundle_dir or self._default_bundle_dir()
            summary = await self.export_bundle(bundle_dir=active_bundle_dir)
        elif active_bundle_dir is None:
            raise ValueError("--bundle-dir is required for --import-only")

        assert active_bundle_dir is not None
        if not export_only:
            import_summary = await self.import_bundle(
                bundle_dir=active_bundle_dir,
                threads=threads,
                max_off_heap_memory=max_off_heap_memory,
            )
            summary.update(import_summary)

        summary.setdefault("bundle_dir", active_bundle_dir)
        return summary

    async def export_bundle(self, *, bundle_dir: Path) -> dict[str, object]:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        connection = await asyncpg.connect(_normalize_postgres_dsn(self._settings.database_url))
        try:
            await self._prepare_temp_tables(connection)
            for spec in _GRAPH_CSV_SPECS:
                output_path = bundle_dir / spec.filename
                with output_path.open("wb") as output:
                    await connection.copy_from_query(
                        spec.query,
                        output=output,
                        format="csv",
                        header=True,
                        encoding="utf-8",
                    )
        finally:
            await connection.close()

        latest_link_count = await self._count_lines(bundle_dir / "emits.csv")
        return {
            "bundle_dir": bundle_dir,
            "files_written": len(_GRAPH_CSV_SPECS),
            "latest_indicator_edges": max(0, latest_link_count - 1),
        }

    async def import_bundle(
        self,
        *,
        bundle_dir: Path,
        threads: int,
        max_off_heap_memory: str,
    ) -> dict[str, object]:
        missing_files = [spec.filename for spec in _GRAPH_CSV_SPECS if not (bundle_dir / spec.filename).exists()]
        if missing_files:
            raise FileNotFoundError(f"Missing graph bundle files: {', '.join(sorted(missing_files))}")

        await self._run_command(["docker", "compose", "stop", "neo4j"])
        try:
            await self._run_command(self._import_command(bundle_dir, threads, max_off_heap_memory))
        finally:
            await self._run_command(["docker", "compose", "up", "-d", "neo4j"])
        await self._wait_for_neo4j()
        counts = await self._fetch_graph_counts()
        return {
            "bundle_dir": bundle_dir,
            "graph_nodes": counts["nodes"],
            "graph_relationships": counts["relationships"],
        }

    async def _prepare_temp_tables(self, connection: asyncpg.Connection) -> None:
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_skills AS
            SELECT
                s.id AS skill_pk,
                s.latest_snapshot_id AS latest_snapshot_id,
                r.id AS repo_pk,
                r.publisher AS publisher,
                r.repo AS repo,
                r.source_url AS source_url,
                s.skill_slug AS skill_slug,
                s.title AS title,
                COALESCE(s.latest_severity, 'none') AS severity,
                COALESCE(s.latest_risk_score, 0) AS risk_score,
                COALESCE(s.latest_confidence, 'unknown') AS confidence,
                COALESCE(s.current_total_installs, 0) AS total_installs,
                'skill:' || r.publisher || '/' || r.repo || '/' || s.skill_slug AS skill_graph_id,
                'repo:' || r.publisher || '/' || r.repo AS repo_graph_id
            FROM skills s
            JOIN skill_repos r
              ON r.id = s.repo_id
            """
        )
        await connection.execute(
            "CREATE INDEX tmp_graph_skills_latest_snapshot_idx ON tmp_graph_skills (latest_snapshot_id)"
        )
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_latest_indicators AS
            SELECT DISTINCT
                i.id AS indicator_pk,
                i.indicator_type AS indicator_type,
                i.indicator_value AS indicator_value,
                i.normalized_value AS normalized_value,
                'indicator:' || i.indicator_type || ':' || i.indicator_value AS indicator_graph_id
            FROM skill_indicator_links sil
            JOIN tmp_graph_skills tgs
              ON tgs.latest_snapshot_id = sil.skill_snapshot_id
            JOIN indicators i
              ON i.id = sil.indicator_id
            """
        )
        await connection.execute(
            "CREATE INDEX tmp_graph_latest_indicators_pk_idx ON tmp_graph_latest_indicators (indicator_pk)"
        )
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_resolved_ips AS
            SELECT DISTINCT
                ie.indicator_id AS source_indicator_pk,
                tgli.indicator_graph_id AS source_indicator_graph_id,
                ip.value AS resolved_ip,
                'indicator:ip:' || ip.value AS resolved_ip_graph_id,
                NULLIF(BTRIM(COALESCE((ie.normalized_payload::jsonb -> 'resolved_ip_profiles' -> ip.value) ->> 'asn', '')), '') AS asn,
                NULLIF(BTRIM(COALESCE((ie.normalized_payload::jsonb -> 'resolved_ip_profiles' -> ip.value) ->> 'asName', '')), '') AS as_name
            FROM indicator_enrichments ie
            JOIN tmp_graph_latest_indicators tgli
              ON tgli.indicator_pk = ie.indicator_id
            CROSS JOIN LATERAL jsonb_array_elements_text(
                COALESCE(ie.normalized_payload::jsonb -> 'resolved_ips', '[]'::jsonb)
            ) AS ip(value)
            WHERE ie.provider = 'local_dns'
              AND ie.status = 'completed'
            """
        )
        await connection.execute(
            "CREATE INDEX tmp_graph_resolved_ips_source_idx ON tmp_graph_resolved_ips (source_indicator_pk)"
        )
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_mewhois AS
            SELECT
                ie.indicator_id AS indicator_pk,
                tgli.indicator_graph_id AS indicator_graph_id,
                NULLIF(
                    BTRIM(
                        COALESCE(
                            ie.normalized_payload::jsonb ->> 'registrar',
                            ie.normalized_payload::jsonb #>> '{rawResponse,registrar_name}',
                            ''
                        )
                    ),
                    ''
                ) AS registrar_name,
                NULLIF(
                    BTRIM(
                        COALESCE(
                            ie.normalized_payload::jsonb ->> 'registrantOrg',
                            ie.normalized_payload::jsonb #>> '{rawResponse,registrant_org}',
                            ''
                        )
                    ),
                    ''
                ) AS registrant_org,
                COALESCE(
                    ie.normalized_payload::jsonb -> 'nameservers',
                    ie.normalized_payload::jsonb #> '{rawResponse,name_servers}',
                    '[]'::jsonb
                ) AS nameservers
            FROM indicator_enrichments ie
            JOIN tmp_graph_latest_indicators tgli
              ON tgli.indicator_pk = ie.indicator_id
            WHERE ie.provider = 'mewhois'
              AND ie.status = 'completed'
            """
        )
        await connection.execute(
            "CREATE INDEX tmp_graph_mewhois_indicator_idx ON tmp_graph_mewhois (indicator_pk)"
        )
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_mewhois_nameservers AS
            SELECT DISTINCT
                indicator_pk,
                indicator_graph_id,
                BTRIM(value) AS nameserver
            FROM tmp_graph_mewhois,
                 LATERAL jsonb_array_elements_text(COALESCE(nameservers, '[]'::jsonb))
            WHERE BTRIM(value) <> ''
            """
        )
        await connection.execute(
            """
            CREATE TEMP TABLE tmp_graph_meip AS
            SELECT
                ie.indicator_id AS indicator_pk,
                tgli.indicator_graph_id AS indicator_graph_id,
                NULLIF(BTRIM(COALESCE(ie.normalized_payload::jsonb ->> 'asn', '')), '') AS asn,
                NULLIF(BTRIM(COALESCE(ie.normalized_payload::jsonb ->> 'asName', '')), '') AS as_name
            FROM indicator_enrichments ie
            JOIN tmp_graph_latest_indicators tgli
              ON tgli.indicator_pk = ie.indicator_id
            WHERE ie.provider = 'meip'
              AND ie.status = 'completed'
            """
        )
        await connection.execute(
            "CREATE INDEX tmp_graph_meip_indicator_idx ON tmp_graph_meip (indicator_pk)"
        )

    def _import_command(
        self,
        bundle_dir: Path,
        threads: int,
        max_off_heap_memory: str,
    ) -> list[str]:
        bundle_path = str(bundle_dir.resolve())
        command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-v",
            f"{bundle_path}:/import/graph",
            "neo4j",
            "bash",
            "-lc",
            self._neo4j_admin_command(
                bundle_mount="/import/graph",
                threads=threads,
                max_off_heap_memory=max_off_heap_memory,
            ),
        ]
        return command

    def _neo4j_admin_command(
        self,
        *,
        bundle_mount: str,
        threads: int,
        max_off_heap_memory: str,
    ) -> str:
        parts = [
            "/var/lib/neo4j/bin/neo4j-admin",
            "database",
            "import",
            "full",
            "neo4j",
            "--overwrite-destination=true",
            f"--threads={threads}",
            f"--max-off-heap-memory={max_off_heap_memory}",
            "--high-parallel-io=auto",
            "--id-type=string",
            "--skip-bad-relationships=true",
            "--skip-duplicate-nodes=true",
        ]
        node_specs = {
            "Skill": "skills.csv",
            "Repo": "repos.csv",
            "Registry": "registries.csv",
            "Indicator": "indicators.csv",
            "ASN": "asns.csv",
            "Registrar": "registrars.csv",
            "Organization": "organizations.csv",
            "Nameserver": "nameservers.csv",
        }
        relationship_specs = {
            "HOSTED_IN": "hosted_in.csv",
            "SEEN_IN": "seen_in.csv",
            "EMITS": "emits.csv",
            "RESOLVES_TO": "resolves_to.csv",
            "ANNOUNCED_BY": "announced_by.csv",
            "REGISTERED_WITH": "registered_with.csv",
            "REGISTERED_TO": "registered_to.csv",
            "USES_NAMESERVER": "uses_nameserver.csv",
        }
        for label, filename in node_specs.items():
            parts.append(f"--nodes={label}={bundle_mount}/{filename}")
        for rel_type, filename in relationship_specs.items():
            parts.append(f"--relationships={rel_type}={bundle_mount}/{filename}")
        return " ".join(shlex.quote(part) for part in parts)

    async def _run_command(self, cmd: list[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"Command failed ({process.returncode}): {' '.join(cmd)}\n"
                f"{stdout.decode('utf-8', errors='replace')}\n"
                f"{stderr.decode('utf-8', errors='replace')}"
            )

    async def _wait_for_neo4j(self, attempts: int = 60, delay_seconds: float = 2.0) -> None:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{self._settings.neo4j_http_url.rstrip('/')}/db/{self._settings.neo4j_database}/tx/commit",
                        headers=self._neo4j_headers(),
                        json={"statements": [{"statement": "RETURN 1 AS ok"}]},
                    )
                    response.raise_for_status()
                    return
            except Exception as exc:  # pragma: no cover - exercised via tests through monkeypatch
                last_error = exc
                await asyncio.sleep(delay_seconds)
        raise RuntimeError(f"Neo4j did not become healthy at {self._settings.neo4j_http_url}") from last_error

    async def _fetch_graph_counts(self) -> dict[str, int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._settings.neo4j_http_url.rstrip('/')}/db/{self._settings.neo4j_database}/tx/commit",
                headers=self._neo4j_headers(),
                json={
                    "statements": [
                        {"statement": "MATCH (n) RETURN count(n) AS count"},
                        {"statement": "MATCH ()-[r]->() RETURN count(r) AS count"},
                    ]
                },
            )
            response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        node_count = int(((results[0].get("data") or [{}])[0].get("row") or [0])[0]) if len(results) > 0 else 0
        relationship_count = int(((results[1].get("data") or [{}])[0].get("row") or [0])[0]) if len(results) > 1 else 0
        return {"nodes": node_count, "relationships": relationship_count}

    def _neo4j_headers(self) -> dict[str, str]:
        auth = b64encode(
            f"{self._settings.neo4j_user}:{self._settings.neo4j_password}".encode("utf-8")
        ).decode("ascii")
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }

    def _default_bundle_dir(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return self._settings.archive_root / "graph-import" / timestamp

    async def _count_lines(self, path: Path) -> int:
        def _count() -> int:
            with path.open("rb") as handle:
                return sum(1 for _ in handle)

        return await asyncio.to_thread(_count)


def default_bulk_graph_threads() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, int(cpu_count * 0.8))


def _normalize_postgres_dsn(database_url: str) -> str:
    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if not normalized.startswith(("postgresql://", "postgres://")):
        raise ValueError("Graph bulk export requires a Postgres SKRISK_DATABASE_URL")
    return normalized
