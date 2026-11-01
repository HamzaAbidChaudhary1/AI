"""CrawlProvider adapters (docs/CRAWLING.md): Firecrawl (primary), Apify (JS-heavy/blocked),
Fixture (tests and offline development — content is clearly marked as test data)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from ..config import get_settings

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pages"


@dataclass
class CrawlResult:
    url: str
    markdown: str
    http_status: int
    provider: str


class CrawlError(RuntimeError):
    pass


class CrawlProvider(Protocol):
    name: str

    def fetch(self, url: str, *, actor: str | None = None) -> CrawlResult: ...


def domain_allowed(url: str, allowed_domains: list[str]) -> bool:
    """Exact domain or subdomain match, https only."""
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in (x.lower() for x in allowed_domains))


class FirecrawlProvider:
    name = "firecrawl"

    def __init__(self, api_key: str, base_url: str = "https://api.firecrawl.dev") -> None:
        self.api_key = api_key
        self.base_url = base_url

    def fetch(self, url: str, *, actor: str | None = None) -> CrawlResult:
        try:
            r = httpx.post(
                f"{self.base_url}/v2/scrape",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True, "maxAge": 0},
                timeout=90,
            )
        except httpx.HTTPError as e:
            raise CrawlError(f"firecrawl: {e}") from e
        if r.status_code != 200:
            raise CrawlError(f"firecrawl http {r.status_code}")
        data = r.json().get("data") or {}
        md = data.get("markdown") or ""
        status = int((data.get("metadata") or {}).get("statusCode") or 200)
        if not md.strip():
            raise CrawlError("firecrawl returned empty content")
        return CrawlResult(url, md, status, self.name)


class ApifyProvider:
    name = "apify"
    default_actor = "apify~website-content-crawler"

    def __init__(self, token: str) -> None:
        self.token = token

    def fetch(self, url: str, *, actor: str | None = None) -> CrawlResult:
        actor_id = (actor or self.default_actor).replace("/", "~")
        try:
            r = httpx.post(
                f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
                params={"token": self.token, "timeout": 120},
                json={"startUrls": [{"url": url}], "maxCrawlPages": 1, "crawlerType": "playwright:adaptive"},
                timeout=150,
            )
        except httpx.HTTPError as e:
            raise CrawlError(f"apify: {e}") from e
        if r.status_code not in (200, 201):
            raise CrawlError(f"apify http {r.status_code}")
        items = r.json() or []
        if not items:
            raise CrawlError("apify returned no items")
        md = items[0].get("markdown") or items[0].get("text") or ""
        if not md.strip():
            raise CrawlError("apify returned empty content")
        return CrawlResult(url, md, int(items[0].get("statusCode") or 200), self.name)


def fixture_path(url: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower().removeprefix("https://")).strip("-")
    return FIXTURE_DIR / f"{slug}.md"


class FixtureProvider:
    """Serves markdown from fixtures/pages/<slug>.md. Used in tests and offline dev only."""

    name = "fixture"

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self.overrides = overrides if overrides is not None else {}

    def fetch(self, url: str, *, actor: str | None = None, prefer: str = "fixture") -> CrawlResult:
        if url in self.overrides:
            return CrawlResult(url, self.overrides[url], 200, self.name)
        p = fixture_path(url)
        if not p.exists():
            raise CrawlError(f"no fixture for {url}")
        return CrawlResult(url, p.read_text(encoding="utf-8"), 200, self.name)


class FallbackProvider:
    """Firecrawl first, Apify on failure or when the source asks for Apify."""

    name = "firecrawl+apify"

    def __init__(self, primary: CrawlProvider | None, secondary: CrawlProvider | None) -> None:
        self.primary, self.secondary = primary, secondary

    def fetch(self, url: str, *, actor: str | None = None, prefer: str = "firecrawl") -> CrawlResult:
        order = [self.primary, self.secondary] if prefer == "firecrawl" else [self.secondary, self.primary]
        errors: list[str] = []
        for p in order:
            if p is None:
                continue
            try:
                return p.fetch(url, actor=actor)
            except CrawlError as e:
                errors.append(str(e))
        raise CrawlError("; ".join(errors) or "no crawl provider configured")


_provider_override: object | None = None


def set_crawl_provider(p: object | None) -> None:
    global _provider_override
    _provider_override = p


def get_crawl_provider() -> FallbackProvider | FixtureProvider:
    if _provider_override is not None:
        return _provider_override  # type: ignore[return-value]
    s = get_settings()
    live = s.crawl_provider == "live" or (s.crawl_provider == "auto" and (s.firecrawl_api_key or s.apify_token))
    if not live:
        return FixtureProvider()
    return FallbackProvider(
        FirecrawlProvider(s.firecrawl_api_key) if s.firecrawl_api_key else None,
        ApifyProvider(s.apify_token) if s.apify_token else None,
    )
