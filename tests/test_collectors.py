from __future__ import annotations

from pathlib import Path

from skrisk.collectors.github import discover_skills_in_checkout
from skrisk.collectors.skills_sh import extract_audit_rows, parse_directory_page, parse_sitemap


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


def test_parse_directory_page_extracts_registry_entries() -> None:
    payload = {
        "page": 0,
        "total": 2,
        "hasMore": False,
        "skills": [
            {
                "source": "tul-sh/skills",
                "skillId": "agent-tools",
                "installs": 1234,
            },
            {
                "source": "vercel-labs/skills",
                "skillId": "find-skills",
            },
        ],
    }

    page = parse_directory_page(payload)

    assert page.total == 2
    assert page.has_more is False
    assert len(page.entries) == 2
    assert page.entries[0].publisher == "tul-sh"
    assert page.entries[0].repo == "skills"
    assert page.entries[0].skill_slug == "agent-tools"
    assert page.entries[0].url == "https://skills.sh/tul-sh/skills/agent-tools"
    assert page.entries[0].weekly_installs == 1234
    assert page.entries[1].weekly_installs is None


async def test_skills_sh_client_fetch_snapshot_pages_through_directory_api() -> None:
    import httpx

    from skrisk.services.sync import SkillsShClient

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
                            "installs": 100,
                        },
                        {
                            "source": "vercel-labs/skills",
                            "skillId": "find-skills",
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
                            "source": "melurna/skills",
                            "skillId": "impact-analyzer",
                            "installs": 80,
                        }
                    ],
                },
            )
        if request.url.path == "/audits":
            return httpx.Response(200, text="<html><body>no audits rows</body></html>")
        raise AssertionError(f"Unexpected request path: {request.url.path}")

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
        "impact-analyzer",
    ]
    assert snapshot.sitemap_entries[0].weekly_installs == 100
    assert snapshot.sitemap_entries[1].weekly_installs == 90
    assert snapshot.sitemap_entries[2].weekly_installs == 80
