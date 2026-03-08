"""Collection helpers for skills.sh discovery surfaces."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree


SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
AUDIT_ROWS_PATTERN = re.compile(r'"rows"\s*:\s*(\[[\s\S]*?\])\s*,\s*"totalRows"')


@dataclass(slots=True, frozen=True)
class SkillSitemapEntry:
    """A single skill URL discovered from the public sitemap."""

    publisher: str
    repo: str
    skill_slug: str
    url: str
    weekly_installs: int | None = None


@dataclass(slots=True, frozen=True)
class PartnerVerdict:
    """Normalized partner verdict extracted from the audits payload."""

    partner: str
    verdict: str | None = None
    summary: str | None = None
    alert_count: int = 0
    analyzed_at: str | None = None


@dataclass(slots=True, frozen=True)
class AuditRow:
    """A single skill row from the public audits leaderboard."""

    rank: int
    publisher: str
    repo: str
    skill_slug: str
    name: str
    partners: dict[str, PartnerVerdict] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DirectoryPage:
    """A single paginated directory response from the skills.sh API."""

    page: int
    total: int
    has_more: bool
    entries: list[SkillSitemapEntry]


def parse_sitemap(xml: str) -> list[SkillSitemapEntry]:
    """Parse the public skills.sh sitemap into skill coordinates."""

    root = ElementTree.fromstring(xml)
    entries: list[SkillSitemapEntry] = []

    for loc in root.findall("sm:url/sm:loc", SITEMAP_NAMESPACE):
        url = (loc.text or "").strip()
        parts = [part for part in url.removeprefix("https://skills.sh/").split("/") if part]
        if len(parts) < 3:
            continue
        entries.append(
            SkillSitemapEntry(
                publisher=parts[0],
                repo=parts[1],
                skill_slug=parts[2],
                url=url,
            )
        )

    return entries


def extract_audit_rows(html: str) -> list[AuditRow]:
    """Extract the audit leaderboard payload embedded in the page HTML."""

    match = AUDIT_ROWS_PATTERN.search(html)
    if not match:
        return []

    raw_rows = json.loads(match.group(1))
    rows: list[AuditRow] = []
    for raw_row in raw_rows:
        source = raw_row.get("source", "")
        publisher, repo = _split_source(source)
        partners = {
            "agent_trust_hub": _partner_verdict("agent_trust_hub", raw_row.get("agentTrustHub")),
            "socket": _partner_verdict("socket", raw_row.get("socket")),
            "snyk": _partner_verdict("snyk", raw_row.get("snyk")),
        }
        rows.append(
            AuditRow(
                rank=int(raw_row.get("rank", 0)),
                publisher=publisher,
                repo=repo,
                skill_slug=raw_row.get("skillId", ""),
                name=raw_row.get("name", ""),
                partners=partners,
            )
        )

    return rows


def parse_directory_page(
    payload: dict[str, Any],
    *,
    base_url: str = "https://skills.sh",
) -> DirectoryPage:
    """Normalize a paginated `/api/skills/<view>/<page>` response."""

    base_url = base_url.rstrip("/")
    entries: list[SkillSitemapEntry] = []

    for raw_skill in payload.get("skills", []):
        source = str(raw_skill.get("source") or "")
        publisher, repo = _split_source(source)
        skill_slug = str(raw_skill.get("skillId") or "").strip()
        if not publisher or not repo or not skill_slug:
            continue

        raw_installs = raw_skill.get("installs")
        weekly_installs = int(raw_installs) if raw_installs is not None else None
        entries.append(
            SkillSitemapEntry(
                publisher=publisher,
                repo=repo,
                skill_slug=skill_slug,
                url=f"{base_url}/{publisher}/{repo}/{skill_slug}",
                weekly_installs=weekly_installs,
            )
        )

    return DirectoryPage(
        page=int(payload.get("page") or 0),
        total=int(payload.get("total") or len(entries)),
        has_more=bool(payload.get("hasMore")),
        entries=entries,
    )


def _split_source(source: str) -> tuple[str, str]:
    parts = source.split("/", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return source, ""


def _partner_verdict(partner: str, payload: dict | None) -> PartnerVerdict:
    if not payload:
        return PartnerVerdict(partner=partner)

    result = payload.get("result") or {}
    verdict = result.get("overall_risk_level")
    if verdict is None and "alertCount" in result:
        verdict = "ALERTS" if int(result.get("alertCount") or 0) else "SAFE"

    return PartnerVerdict(
        partner=partner,
        verdict=verdict,
        summary=result.get("summary"),
        alert_count=int(result.get("alertCount") or 0),
        analyzed_at=payload.get("analyzedAt"),
    )
