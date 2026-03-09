from __future__ import annotations

import httpx
import pytest

from skrisk.collectors.skillsmp import SkillsMpClient


def test_skillsmp_client_builds_bearer_headers_and_normalizes_search_page() -> None:
    client = SkillsMpClient(api_key="test-key")

    headers = client.request_headers()
    page = client.parse_search_payload(
        {
            "success": True,
            "data": {
                "skills": [
                    {
                        "id": "openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
                        "name": "prose",
                        "author": "openclaw",
                        "description": "Open prose skill",
                        "githubUrl": "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose",
                        "skillUrl": "https://skillsmp.com/fr/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
                        "stars": 42,
                        "updatedAt": "1772794212",
                    }
                ],
                "pagination": {
                    "page": 2,
                    "limit": 20,
                    "total": 21,
                    "totalPages": 2,
                    "hasNext": False,
                    "hasPrev": True,
                    "totalIsExact": False,
                },
                "filters": {
                    "search": "security",
                    "sortBy": "recent",
                },
            },
            "meta": {"requestId": "req-123", "responseTimeMs": 371},
        }
    )

    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("skrisk/")
    assert page.query == "security"
    assert page.page == 2
    assert page.has_next is False
    assert page.total_is_exact is False
    assert len(page.entries) == 1

    entry = page.entries[0]
    assert entry.source == "skillsmp"
    assert entry.source_native_id == "openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
    assert entry.url == "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
    assert entry.repo_url == "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose"
    assert entry.publisher == "openclaw"
    assert entry.repo == "openclaw"
    assert entry.skill_slug == "prose"
    assert entry.author == "openclaw"
    assert entry.description == "Open prose skill"
    assert entry.stars == 42
    assert entry.updated_at == "1772794212"


def test_skillsmp_client_canonicalizes_skill_urls() -> None:
    client = SkillsMpClient(api_key="test-key")

    assert (
        client.canonicalize_skill_url(
            "https://skillsmp.com/fr/skills/example-agent-tools/"
        )
        == "https://skillsmp.com/skills/example-agent-tools"
    )
    assert (
        client.canonicalize_skill_url("https://skillsmp.com/skills/example-agent-tools")
        == "https://skillsmp.com/skills/example-agent-tools"
    )


@pytest.mark.asyncio
async def test_skillsmp_client_rejects_invalid_enumeration_queries() -> None:
    client = SkillsMpClient(api_key="test-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))

    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(ValueError, match="non-empty search query"):
            await client.fetch_search_page("", client=http_client)

        with pytest.raises(ValueError, match="non-empty search query"):
            await client.fetch_search_page("*", client=http_client)
