from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from skrisk.collectors.github import discover_skills_in_checkout
from skrisk.collectors.skills_sh import extract_audit_rows, parse_directory_page, parse_sitemap
from skrisk.services.sync import SkillsShClient


def test_parse_sitemap_extracts_skill_coordinates() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://skills.sh/vercel-labs/skills/find-skills</loc></url>
      <url><loc>https://skills.sh/tul-sh/skills/agent-tools</loc></url>
    </urlset>
    """

    entries = parse_sitemap(xml)

    assert [entry.publisher for entry in entries] == ["vercel-labs", "tul-sh"]
    assert [entry.repo for entry in entries] == ["skills", "skills"]
    assert [entry.skill_slug for entry in entries] == ["find-skills", "agent-tools"]
    assert entries[1].url == "https://skills.sh/tul-sh/skills/agent-tools"


def test_extract_audit_rows_reads_partner_verdicts_from_html_payload() -> None:
    html = """
    <html>
      <body>
        <script>
          window.__DATA__ = {
            "rows": [
              {
                "rank": 1,
                "source": "tul-sh/skills",
                "skillId": "agent-tools",
                "name": "agent-tools",
                "agentTrustHub": {
                  "result": { "overall_risk_level": "HIGH" },
                  "analyzedAt": "2026-03-05T08:31:39.748Z"
                },
                "socket": {
                  "result": { "alertCount": 1 },
                  "analyzedAt": "2026-03-05T08:32:02.979Z"
                },
                "snyk": {
                  "result": {
                    "overall_risk_level": "CRITICAL",
                    "summary": "Suspicious download URL"
                  },
                  "analyzedAt": "2026-03-05T08:31:28.415042+00:00"
                }
              }
            ],
            "totalRows": 1000
          };
        </script>
      </body>
    </html>
    """

    rows = extract_audit_rows(html)

    assert len(rows) == 1
    row = rows[0]
    assert row.rank == 1
    assert row.publisher == "tul-sh"
    assert row.repo == "skills"
    assert row.skill_slug == "agent-tools"
    assert row.partners["agent_trust_hub"].verdict == "HIGH"
    assert row.partners["socket"].alert_count == 1
    assert row.partners["snyk"].verdict == "CRITICAL"


def test_parse_directory_page_extracts_registry_entries() -> None:
    payload = {
        "page": 0,
        "total": 401,
        "hasMore": True,
        "skills": [
            {
                "source": "tul-sh/skills",
                "skillId": "agent-tools",
                "name": "agent-tools",
                "installs": 1234,
            },
            {
                "source": "vercel-labs/agent-skills",
                "skillId": "frontend-design",
                "name": "frontend-design",
                "installs": 567,
            },
        ],
    }

    page = parse_directory_page(payload)

    assert page.page == 0
    assert page.total == 401
    assert page.has_more is True
    assert [entry.publisher for entry in page.entries] == ["tul-sh", "vercel-labs"]
    assert [entry.repo for entry in page.entries] == ["skills", "agent-skills"]
    assert [entry.skill_slug for entry in page.entries] == ["agent-tools", "frontend-design"]
    assert page.entries[0].url == "https://skills.sh/tul-sh/skills/agent-tools"


@pytest.mark.asyncio
async def test_skills_sh_client_fetch_snapshot_pages_through_directory_api() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/api/skills/all-time/0":
            return httpx.Response(
                200,
                json={
                    "page": 0,
                    "total": 3,
                    "hasMore": True,
                    "skills": [
                        {
                            "source": "tul-sh/skills",
                            "skillId": "agent-tools",
                            "name": "agent-tools",
                            "installs": 100,
                        },
                        {
                            "source": "vercel-labs/skills",
                            "skillId": "find-skills",
                            "name": "find-skills",
                            "installs": 90,
                        },
                    ],
                },
            )
        if request.url.path == "/api/skills/all-time/1":
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total": 3,
                    "hasMore": False,
                    "skills": [
                        {
                            "source": "anthropics/skills",
                            "skillId": "frontend-design",
                            "name": "frontend-design",
                            "installs": 80,
                        }
                    ],
                },
            )
        if request.url.path == "/audits":
            return httpx.Response(
                200,
                text="""
                <script>
                window.__DATA__ = {
                  "rows": [
                    {
                      "rank": 1,
                      "source": "tul-sh/skills",
                      "skillId": "agent-tools",
                      "name": "agent-tools",
                      "snyk": {
                        "result": { "overall_risk_level": "HIGH" },
                        "analyzedAt": "2026-03-05T08:31:28.415042+00:00"
                      }
                    }
                  ],
                  "totalRows": 1
                };
                </script>
                """,
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://skills.sh") as client:
        snapshot = await SkillsShClient("https://skills.sh").fetch_snapshot(client)

    assert requested_paths[0] in {"/api/skills/all-time/0", "/audits"}
    assert set(requested_paths) == {
        "/api/skills/all-time/0",
        "/api/skills/all-time/1",
        "/audits",
    }
    assert snapshot.total_skills == 3
    assert [entry.skill_slug for entry in snapshot.sitemap_entries] == [
        "agent-tools",
        "find-skills",
        "frontend-design",
    ]
    assert snapshot.audit_rows[0].partners["snyk"].verdict == "HIGH"


@pytest.mark.asyncio
async def test_skills_sh_client_retries_rate_limited_directory_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"page_0": 0}
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/skills/all-time/0":
            attempts["page_0"] += 1
            if attempts["page_0"] == 1:
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(
                200,
                json={
                    "page": 0,
                    "total": 1,
                    "hasMore": False,
                    "skills": [
                        {
                            "source": "tul-sh/skills",
                            "skillId": "agent-tools",
                            "name": "agent-tools",
                            "installs": 100,
                        }
                    ],
                },
            )
        if request.url.path == "/audits":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(404)

    monkeypatch.setattr("skrisk.services.sync.asyncio.sleep", fake_sleep)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://skills.sh") as client:
        snapshot = await SkillsShClient("https://skills.sh").fetch_snapshot(client)

    assert attempts["page_0"] == 2
    assert slept == [30.0]
    assert snapshot.total_skills == 1
    assert [entry.skill_slug for entry in snapshot.sitemap_entries] == ["agent-tools"]


def test_discover_skills_in_checkout_finds_supported_skill_locations(
    tmp_path: Path,
) -> None:
    (tmp_path / "skills" / ".system" / "skill-a").mkdir(parents=True)
    (tmp_path / "skills" / ".system" / "skill-a" / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: system skill\n---\n",
        encoding="utf-8",
    )
    (tmp_path / ".agents" / "skills" / "skill-b").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "skill-b" / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: agent skill\n---\n",
        encoding="utf-8",
    )

    discovered = discover_skills_in_checkout(tmp_path)

    assert [skill.slug for skill in discovered] == ["skill-a", "skill-b"]
    assert discovered[0].relative_path == "skills/.system/skill-a"
    assert discovered[1].relative_path == ".agents/skills/skill-b"
