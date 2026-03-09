from __future__ import annotations

import httpx
import pytest

from skrisk.collectors.skillsmp import SkillsMpClient, canonicalize_skillsmp_skill_url


def test_canonicalize_skillsmp_skill_url_strips_locale_and_query() -> None:
    assert canonicalize_skillsmp_skill_url(
        "https://skillsmp.com/fr/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md?ref=home#details"
    ) == "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"


@pytest.mark.asyncio
async def test_skillsmp_client_normalizes_search_results_and_auth_headers() -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Authorization"))
        assert request.url.path == "/api/v1/skills/search"
        assert request.url.params["q"] == "prose"
        assert request.url.params["page"] == "1"
        assert request.url.params["limit"] == "100"
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "skills": [
                        {
                            "id": "openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
                            "name": "prose",
                            "author": "openclaw",
                            "description": "Write long-form prose.",
                            "githubUrl": "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose",
                            "skillUrl": "https://skillsmp.com/fr/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md?ref=home",
                            "stars": 123,
                            "updatedAt": "1772792453",
                        }
                    ],
                    "pagination": {
                        "page": 1,
                        "limit": 20,
                        "total": 21,
                        "totalPages": 2,
                        "hasNext": True,
                        "hasPrev": False,
                        "totalIsExact": False,
                    },
                    "filters": {
                        "search": "prose",
                        "sortBy": "recent",
                    },
                },
                "meta": {
                    "requestId": "abc123",
                    "responseTimeMs": 1,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://skillsmp.com") as client:
        page = await SkillsMpClient(
            api_key="test-key",
            base_url="https://skillsmp.com",
        ).search("prose", page=1, page_size=100, client=client)

    assert seen_headers == ["Bearer test-key"]
    assert page.query == "prose"
    assert page.page == 1
    assert page.total == 21
    assert page.total_pages == 2
    assert page.has_next is True
    assert page.total_is_exact is False
    assert len(page.entries) == 1

    entry = page.entries[0]
    assert entry.source == "skillsmp"
    assert entry.source_native_id == "openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
    assert (
        entry.url
        == "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
    )
    assert (
        entry.repo_url
        == "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose"
    )
    assert entry.publisher == "openclaw"
    assert entry.repo == "openclaw"
    assert entry.skill_slug == "prose"
    assert entry.author == "openclaw"
    assert entry.description == "Write long-form prose."
    assert entry.stars == 123
    assert entry.updated_at == "1772792453"
    assert entry.view == "search"


@pytest.mark.asyncio
async def test_skillsmp_client_rejects_invalid_wildcard_queries_cleanly() -> None:
    client = SkillsMpClient(api_key="test-key", base_url="https://skillsmp.com")

    with pytest.raises(ValueError, match="at least one letter or number"):
        await client.search("*", page=1)
