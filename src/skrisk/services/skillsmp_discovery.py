"""Browser-assisted discovery for skillsmp pages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from skrisk.collectors.abusech import ArchiveManifestResult, write_archive_manifest
from skrisk.collectors.skills_sh import SkillSitemapEntry
from skrisk.collectors.skillsmp import SkillsMpClient
from skrisk.config import Settings

_HREF_RE = re.compile(r"""href=["'](?P<href>[^"']+)["']""", re.IGNORECASE)
_GITHUB_LINK_RE = re.compile(r"""https://github\.com/[^"'\s<]+""", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class ArchivedSkillsMpPage:
    source_url: str
    archive_path: Path
    manifest_path: Path


@dataclass(slots=True, frozen=True)
class SkillsMpDiscoveryResult:
    entries: list[SkillSitemapEntry]
    archived_pages: list[ArchivedSkillsMpPage]


class SkillsMpDiscoveryService:
    """Discover skill detail pages from skillsmp category/detail URLs."""

    def __init__(
        self,
        *,
        settings: Settings,
        fetch_html: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._settings = settings
        self._fetch_html = fetch_html or self._fetch_with_scrapling
        self._client = SkillsMpClient(
            api_key=settings.skillsmp_api_key,
            base_url=settings.skillsmp_base_url,
        )

    async def discover_from_urls(
        self,
        urls: list[str],
        *,
        fetched_at: datetime | None = None,
    ) -> SkillsMpDiscoveryResult:
        fetched_at = fetched_at or datetime.now(UTC)
        queue = [self._normalize_url(url) for url in urls]
        seen_urls: set[str] = set()
        archived_pages: list[ArchivedSkillsMpPage] = []
        entries_by_url: dict[str, SkillSitemapEntry] = {}

        while queue:
            url = queue.pop(0)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            html = await self._fetch_html(url)
            archive = self._archive_page(url=url, html=html, fetched_at=fetched_at)
            archived_pages.append(
                ArchivedSkillsMpPage(
                    source_url=url,
                    archive_path=archive.archive_path,
                    manifest_path=archive.manifest_path,
                )
            )

            if self._is_listing_url(url):
                for listing_url in self._extract_listing_links(html):
                    normalized_listing_url = self._normalize_url(listing_url)
                    if normalized_listing_url not in seen_urls:
                        queue.append(normalized_listing_url)
                for skill_url in self._extract_skill_links(html):
                    normalized_skill_url = self._normalize_url(skill_url)
                    if normalized_skill_url not in seen_urls:
                        queue.append(normalized_skill_url)
                continue

            entry = self._normalize_detail_page(url=url, html=html)
            if entry is not None:
                entries_by_url[entry.url] = entry

        return SkillsMpDiscoveryResult(
            entries=list(entries_by_url.values()),
            archived_pages=archived_pages,
        )

    async def _fetch_with_scrapling(self, url: str) -> str:
        try:
            from scrapling.fetchers import StealthyFetcher
        except ImportError as exc:
            raise RuntimeError(
                "scrapling browser fetchers are required for skillsmp discovery; "
                "install project dependencies and run `scrapling install`"
            ) from exc

        response = await StealthyFetcher.async_fetch(
            url,
            headless=True,
            network_idle=True,
        )
        return str(response.html_content)

    def _archive_page(
        self,
        *,
        url: str,
        html: str,
        fetched_at: datetime,
    ) -> ArchiveManifestResult:
        page_kind = "detail" if "/skills/" in urlsplit(url).path else "listing"
        destination = self._archive_destination(
            page_kind=page_kind,
            fetched_at=fetched_at,
            source_url=url,
        )
        return write_archive_manifest(
            provider="skillsmp",
            feed_name=f"skillsmp-{page_kind}",
            fetched_at=fetched_at,
            raw_bytes=html.encode("utf-8"),
            row_count=1,
            destination=destination,
            source_url=url,
            artifact_name="page.html",
        )

    def _archive_destination(
        self,
        *,
        page_kind: str,
        fetched_at: datetime,
        source_url: str,
    ) -> Path:
        timestamp = fetched_at.strftime("%H%M%SZ")
        path_slug = "-".join(part for part in urlsplit(source_url).path.split("/") if part) or "root"
        safe_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", path_slug).strip("-") or "page"
        return (
            self._settings.archive_root
            / "registries"
            / "skillsmp"
            / page_kind
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / timestamp
            / safe_slug
        )

    def _normalize_detail_page(self, *, url: str, html: str) -> SkillSitemapEntry | None:
        canonical_url = self._client.canonicalize_skill_url(url)
        github_url = _first_github_link(html)
        if canonical_url is None or github_url is None:
            return None

        publisher, repo, skill_slug = _parse_repo_coordinates(
            github_url,
            fallback_slug=Path(urlsplit(canonical_url).path).name,
        )
        if not publisher or not repo or not skill_slug:
            return None

        return SkillSitemapEntry(
            publisher=publisher,
            repo=repo,
            skill_slug=skill_slug,
            url=canonical_url,
            source="skillsmp",
            repo_url=github_url,
        )

    def _extract_skill_links(self, html: str) -> list[str]:
        skill_links: list[str] = []
        for href in _extract_same_host_links(
            html=html,
            base_url=self._settings.skillsmp_base_url,
        ):
            path = urlsplit(href).path
            if "/skills/" not in path:
                continue
            skill_links.append(href)
        return skill_links

    def _extract_listing_links(self, html: str) -> list[str]:
        listing_links: list[str] = []
        for href in _extract_same_host_links(
            html=html,
            base_url=self._settings.skillsmp_base_url,
        ):
            path = urlsplit(href).path or "/"
            if path == "/":
                listing_links.append(href)
                continue
            if path == "/categories" or path.startswith("/categories/"):
                listing_links.append(href)
                continue
            if path == "/timeline" or path.startswith("/timeline/"):
                listing_links.append(href)
                continue
        return listing_links

    def _normalize_url(self, url: str) -> str:
        normalized = urljoin(f"{self._settings.skillsmp_base_url}/", url)
        canonical_skill_url = self._client.canonicalize_skill_url(normalized)
        return canonical_skill_url if canonical_skill_url and "/skills/" in normalized else normalized.rstrip("/")

    def _is_listing_url(self, url: str) -> bool:
        return "/skills/" not in urlsplit(url).path


def _first_github_link(html: str) -> str | None:
    match = _GITHUB_LINK_RE.search(html)
    if not match:
        return None
    return match.group(0).rstrip("/")


def _parse_repo_coordinates(
    github_url: str,
    *,
    fallback_slug: str,
) -> tuple[str, str, str]:
    path_parts = [part for part in urlsplit(github_url).path.split("/") if part]
    if len(path_parts) < 2:
        return "", "", fallback_slug

    publisher = path_parts[0]
    repo = path_parts[1]
    if len(path_parts) >= 5 and path_parts[2] in {"tree", "blob"}:
        return publisher, repo, path_parts[-1]
    if len(path_parts) >= 3:
        return publisher, repo, path_parts[-1]
    return publisher, repo, fallback_slug


def _extract_same_host_links(*, html: str, base_url: str) -> list[str]:
    base_netloc = urlsplit(base_url).netloc.casefold()
    links: list[str] = []
    for match in _HREF_RE.finditer(html):
        href = urljoin(base_url, match.group("href"))
        if urlsplit(href).netloc.casefold() != base_netloc:
            continue
        links.append(href)
    return links
