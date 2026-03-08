from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from skrisk.collectors.abusech import (
    parse_threatfox_archive,
    parse_threatfox_recent_payload,
    parse_urlhaus_archive,
    parse_urlhaus_recent_payload,
    write_archive_manifest,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_urlhaus_archive_extracts_urls_domains_and_payload_metadata() -> None:
    archive_path = FIXTURES / "urlhaus_full.json.zip"

    parsed = parse_urlhaus_archive(archive_path)

    assert parsed.provider == "abusech"
    assert parsed.feed_name == "urlhaus"
    assert any(item.indicator_type == "url" for item in parsed.indicators)
    assert any(item.indicator_type == "domain" for item in parsed.indicators)
    assert any(item.indicator_type == "ip" for item in parsed.indicators)
    assert any(item.indicator_type == "sha256" for item in parsed.indicators)
    assert parsed.row_count == 2


def test_parse_threatfox_archive_skips_comment_lines_and_reads_iocs() -> None:
    archive_path = FIXTURES / "threatfox_full.csv.zip"

    parsed = parse_threatfox_archive(archive_path)

    assert parsed.provider == "abusech"
    assert parsed.feed_name == "threatfox"
    assert parsed.row_count == 2
    assert parsed.indicators[0].indicator_value == "bad.example"
    assert parsed.indicators[0].observation["reporter"] == "unit-test"


def test_parse_urlhaus_recent_payload_reads_recent_urls() -> None:
    parsed = parse_urlhaus_recent_payload(
        {
            "query_status": "ok",
            "urls": [
                {
                    "id": 3791294,
                    "url": "http://110.37.118.241:46513/i",
                    "url_status": "online",
                    "host": "110.37.118.241",
                    "threat": "malware_download",
                    "payloads": [{"response_sha256": "ab" * 32, "filename": "dropper.bin"}],
                }
            ],
        }
    )

    assert parsed.feed_name == "urlhaus_recent"
    assert parsed.row_count == 1
    assert any(item.indicator_type == "url" for item in parsed.indicators)
    assert any(item.indicator_type == "ip" for item in parsed.indicators)
    assert any(item.indicator_type == "sha256" for item in parsed.indicators)


def test_parse_threatfox_recent_payload_reads_iocs() -> None:
    parsed = parse_threatfox_recent_payload(
        {
            "query_status": "ok",
            "data": [
                {
                    "id": "1760828",
                    "ioc": "thorntrue.draniercismn.in.net",
                    "threat_type": "payload_delivery",
                    "ioc_type": "domain",
                    "confidence_level": "100",
                    "malware": "js.clearfake",
                    "malware_printable": "ClearFake",
                    "reporter": "unit-test",
                }
            ],
        }
    )

    assert parsed.feed_name == "threatfox_recent"
    assert parsed.row_count == 1
    assert parsed.indicators[0].indicator_type == "domain"
    assert parsed.indicators[0].indicator_value == "thorntrue.draniercismn.in.net"
    assert parsed.indicators[0].observation["malware_family"] == "js.clearfake"


def test_write_archive_manifest_records_sha256_and_row_count(tmp_path: Path) -> None:
    destination = tmp_path / "archive"

    result = write_archive_manifest(
        provider="abusech",
        feed_name="threatfox",
        fetched_at=datetime(2026, 3, 6, tzinfo=UTC),
        raw_bytes=b"feed",
        row_count=7,
        destination=destination,
        source_url="https://threatfox-api.abuse.ch/files/exports/full.csv.zip",
        artifact_name="full.csv.zip",
    )

    assert result.archive_path.exists()
    assert result.manifest_path.exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider"] == "abusech"
    assert manifest["feed_name"] == "threatfox"
    assert manifest["row_count"] == 7
    assert manifest["archive_sha256"] == result.archive_sha256
