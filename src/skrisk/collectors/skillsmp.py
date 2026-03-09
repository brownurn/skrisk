"""Collection helpers for the authenticated skillsmp.com API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from skrisk.collectors.skills_sh import SkillSitemapEntry

_DEFAULT_USER_AGENT = "skrisk/0.1"


@dataclass(slots=True, frozen=True)
class SkillsMpSearchPage:
    """A normalized page from the skillsmp search API."""

    query: str
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool
    total_is_exact: bool
    entries: list[SkillSitemapEntry]


class SkillsMpClient:
    """API client for the skillsmp authenticated search endpoints."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://skillsmp.com",
        user_agent: str = _DEFAULT_USER_AGENT,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout = timeout

    def request_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ValueError("SKILLSMP_API_KEY is required to fetch skillsmp registry data")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "Referer": self._base_url,
            "Origin": self._base_url,
        }

    async def fetch_search_page(
        self,
        query: str,
        *,
        page: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> SkillsMpSearchPage:
        normalized_query = _normalize_query(query)
        if client is None:
            async with httpx.AsyncClient(timeout=self._timeout) as managed_client:
                return await self.fetch_search_page(normalized_query, page=page, client=managed_client)

        response = await client.get(
            f"{self._base_url}/api/v1/skills/search",
            params={"q": normalized_query, "page": page},
            headers=self.request_headers(),
        )
        response.raise_for_status()
        return self.parse_search_payload(response.json())

    def parse_search_payload(self, payload: dict[str, Any]) -> SkillsMpSearchPage:
        data = payload.get("data") or {}
        pagination = data.get("pagination") or {}
        filters = data.get("filters") or {}
        entries: list[SkillSitemapEntry] = []

        for raw_skill in data.get("skills", []):
            github_url = _normalized_text(raw_skill.get("githubUrl"))
            publisher, repo, skill_slug = _parse_github_coordinates(
                github_url,
                fallback_slug=_normalized_text(raw_skill.get("name")),
            )
            source_native_id = _normalized_text(raw_skill.get("id"))
            skill_url = self.canonicalize_skill_url(_normalized_text(raw_skill.get("skillUrl")))
            if not publisher or not repo or not skill_slug or not source_native_id or not skill_url:
                continue

            entries.append(
                SkillSitemapEntry(
                    publisher=publisher,
                    repo=repo,
                    skill_slug=skill_slug,
                    url=skill_url,
                    source="skillsmp",
                    source_native_id=source_native_id,
                    repo_url=github_url,
                    author=_normalized_text(raw_skill.get("author")),
                    description=_normalized_text(raw_skill.get("description")),
                    stars=_coerce_int(raw_skill.get("stars")),
                    updated_at=_normalized_text(raw_skill.get("updatedAt")),
                )
            )

        return SkillsMpSearchPage(
            query=_normalized_text(filters.get("search")) or "",
            page=_coerce_int(pagination.get("page")) or 1,
            page_size=_coerce_int(pagination.get("limit")) or len(entries),
            total=_coerce_int(pagination.get("total")) or len(entries),
            total_pages=_coerce_int(pagination.get("totalPages")) or 1,
            has_next=bool(pagination.get("hasNext")),
            has_prev=bool(pagination.get("hasPrev")),
            total_is_exact=bool(pagination.get("totalIsExact")),
            entries=entries,
        )

    def canonicalize_skill_url(self, url: str | None) -> str | None:
        normalized = _normalized_text(url)
        if not normalized:
            return None

        split_url = urlsplit(normalized)
        path_parts = [part for part in split_url.path.split("/") if part]
        if len(path_parts) >= 2 and _looks_like_locale(path_parts[0]) and path_parts[1] == "skills":
            path_parts = path_parts[1:]
        normalized_path = "/" + "/".join(path_parts)
        return urlunsplit((split_url.scheme, split_url.netloc, normalized_path, "", ""))


def _normalize_query(query: str) -> str:
    normalized_query = query.strip()
    if not normalized_query or set(normalized_query) == {"*"}:
        raise ValueError("skillsmp search requires a non-empty search query")
    return normalized_query


def _parse_github_coordinates(
    github_url: str | None,
    *,
    fallback_slug: str | None,
) -> tuple[str, str, str]:
    normalized_url = _normalized_text(github_url)
    if not normalized_url:
        return "", "", fallback_slug or ""

    split_url = urlsplit(normalized_url)
    path_parts = [part for part in split_url.path.split("/") if part]
    if len(path_parts) < 2:
        return "", "", fallback_slug or ""

    publisher = path_parts[0]
    repo = path_parts[1]
    if len(path_parts) >= 5 and path_parts[2] in {"tree", "blob"}:
        skill_slug = path_parts[-1]
    elif len(path_parts) >= 3:
        skill_slug = path_parts[-1]
    else:
        skill_slug = fallback_slug or ""
    return publisher, repo, skill_slug


def _looks_like_locale(value: str) -> bool:
    lowered = value.casefold()
    if len(lowered) == 2 and lowered.isalpha():
        return True
    if len(lowered) == 5 and lowered[2] == "-" and lowered[:2].isalpha() and lowered[3:].isalpha():
        return True
    return False


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
