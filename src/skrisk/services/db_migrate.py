"""Utilities for migrating SK Risk data from SQLite into Postgres."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from sqlalchemy import DateTime, JSON, func, select, text

from skrisk.storage.database import create_session_factory, init_db
from skrisk.storage.models import Base


class DatabaseMigrationService:
    def __init__(self, *, target_database_url: str) -> None:
        self._target_session_factory = create_session_factory(target_database_url)

    async def migrate_from_sqlite(
        self,
        *,
        source_sqlite_path: Path,
        reset_target: bool,
        batch_size: int,
    ) -> dict[str, int]:
        await init_db(self._target_session_factory)
        source = sqlite3.connect(source_sqlite_path)
        source.row_factory = sqlite3.Row
        rows_copied = 0
        tables_copied = 0

        try:
            indicator_id_remap: dict[int, int] = {}
            indicator_identity_to_id: dict[tuple[str | None, str | None], int] = {}
            source_tables = {
                row["name"]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            source_columns_by_table = {
                table_name: {
                    row["name"]
                    for row in source.execute(f'PRAGMA table_info("{table_name}")').fetchall()
                }
                for table_name in source_tables
            }
            engine = getattr(self._target_session_factory, "engine")
            async with engine.begin() as conn:
                if reset_target:
                    for table in reversed(Base.metadata.sorted_tables):
                        await conn.execute(table.delete())

                for table in Base.metadata.sorted_tables:
                    if table.name not in source_tables:
                        continue
                    source_columns = source_columns_by_table.get(table.name, set())
                    selected_columns = [
                        column.name
                        for column in table.columns
                        if column.name in source_columns
                    ]
                    if not selected_columns:
                        continue
                    quoted_columns = ", ".join(f'"{column_name}"' for column_name in selected_columns)
                    order_by_clause = ' ORDER BY "id"' if "id" in selected_columns else ""
                    cursor = source.execute(
                        f'SELECT {quoted_columns} FROM "{table.name}"{order_by_clause}'
                    )
                    batch: list[dict[str, Any]] = []
                    copied_for_table = 0
                    for row in cursor:
                        payload = _coerce_sqlite_row(
                            table,
                            row,
                            selected_columns=selected_columns,
                        )
                        payload = _remap_foreign_keys(
                            table_name=table.name,
                            payload=payload,
                            indicator_id_remap=indicator_id_remap,
                        )
                        if payload is None:
                            continue
                        if table.name == "indicators":
                            indicator_id = payload.get("id")
                            indicator_identity = (
                                payload.get("indicator_type"),
                                payload.get("normalized_value"),
                            )
                            canonical_id = indicator_identity_to_id.get(indicator_identity)
                            if canonical_id is None:
                                if isinstance(indicator_id, int):
                                    indicator_identity_to_id[indicator_identity] = indicator_id
                            elif isinstance(indicator_id, int):
                                indicator_id_remap[indicator_id] = canonical_id
                                continue
                        batch.append(payload)
                        if len(batch) >= batch_size:
                            await conn.execute(table.insert(), batch)
                            copied_for_table += len(batch)
                            batch.clear()
                    if batch:
                        await conn.execute(table.insert(), batch)
                        copied_for_table += len(batch)
                    if copied_for_table > 0:
                        tables_copied += 1
                        rows_copied += copied_for_table

                if conn.dialect.name == "postgresql":
                    for table in Base.metadata.sorted_tables:
                        if "id" not in table.c:
                            continue
                        max_id = await conn.scalar(select(func.max(table.c.id)))
                        await conn.execute(
                            text(
                                """
                                SELECT setval(
                                    pg_get_serial_sequence(:table_name, 'id'),
                                    :sequence_value,
                                    :is_called
                                )
                                """
                            ),
                            {
                                "table_name": table.name,
                                "sequence_value": max_id if max_id and max_id > 0 else 1,
                                "is_called": bool(max_id and max_id > 0),
                            },
                        )
        finally:
            source.close()

        return {
            "tables_copied": tables_copied,
            "rows_copied": rows_copied,
        }


def _coerce_sqlite_row(
    table,
    row: sqlite3.Row,
    *,
    selected_columns: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    selected_column_names = set(selected_columns)
    for column in table.columns:
        if column.name not in selected_column_names:
            continue
        value = row[column.name]
        if value is None:
            if column.server_default is not None and column.nullable is False:
                continue
            payload[column.name] = None
            continue
        if isinstance(value, str):
            value = _sanitize_text(value)
            value = _truncate_text_for_column(column, value)
        if isinstance(column.type, JSON) and isinstance(value, str):
            payload[column.name] = _sanitize_json_strings(json.loads(value))
            continue
        if isinstance(column.type, DateTime) and isinstance(value, str):
            payload[column.name] = datetime.fromisoformat(value)
            continue
        payload[column.name] = value
    return payload


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", "")


def _truncate_text_for_column(column, value: str) -> str:
    max_length = getattr(column.type, "length", None)
    if max_length is None:
        return value
    if len(value) <= max_length:
        return value
    return value[:max_length]


def _sanitize_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_text(str(key)): _sanitize_json_strings(item)
            for key, item in value.items()
        }
    return value


def _remap_foreign_keys(
    *,
    table_name: str,
    payload: dict[str, Any],
    indicator_id_remap: dict[int, int],
) -> dict[str, Any] | None:
    if not indicator_id_remap:
        return payload
    if table_name not in {
        "indicator_observations",
        "skill_indicator_links",
        "indicator_enrichments",
        "vt_lookup_queue",
    }:
        return payload
    indicator_id = payload.get("indicator_id")
    if not isinstance(indicator_id, int):
        return payload
    canonical_id = indicator_id_remap.get(indicator_id)
    if canonical_id is None:
        return payload
    remapped_payload = dict(payload)
    remapped_payload["indicator_id"] = canonical_id
    if "raw_value" in remapped_payload and isinstance(remapped_payload["raw_value"], str):
        remapped_payload["raw_value"] = _sanitize_text(remapped_payload["raw_value"])
    return remapped_payload
