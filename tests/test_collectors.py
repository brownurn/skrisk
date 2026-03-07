from __future__ import annotations

from pathlib import Path

from skrisk.collectors.github import discover_skills_in_checkout
from skrisk.collectors.skills_sh import extract_audit_rows, parse_sitemap


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

