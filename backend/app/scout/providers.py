from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings

ROLE_QUERY_HINTS = {
    "gtm": ["GTM", "go-to-market", "growth", "sales", "revenue"],
    "product": ["product manager", "product lead", "Head of Product"],
    "bd": ["business development", "partnerships", "BD manager"],
}


async def tavily_search(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={
                "query": query,
                "search_depth": "basic",
                "include_answer": False,
                "max_results": max_results,
            },
        )
        if resp.status_code >= 400:
            # Fallback to body api_key (older style)
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": False,
                    "max_results": max_results,
                },
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Tavily error {resp.status_code}: {resp.text[:240]}")
        data = resp.json()
        return data.get("results", [])


def build_scout_queries(geo: str, role_families: list[str]) -> list[str]:
    queries: list[str] = []
    for family in role_families:
        hints = ROLE_QUERY_HINTS.get(family, [family])
        for hint in hints[:2]:
            queries.append(f'{geo} startup hiring "{hint}" careers OR jobs')
            queries.append(f'{geo} company "{hint}" open role OR vacancy')
    queries.append(f"{geo} startup founders cofounder hiring GTM OR product OR business development")
    # de-dupe while preserving order
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        # skip job boards / aggregators as company domains
        blocked = (
            "linkedin.com",
            "indeed.com",
            "glassdoor.com",
            "lever.co",
            "greenhouse.io",
            "ashbyhq.com",
            "kariyer.net",
            "yenibiris.com",
            "secretcv.com",
            "twitter.com",
            "x.com",
            "facebook.com",
            "youtube.com",
            "medium.com",
            "notion.site",
            "google.com",
            "tavily.com",
        )
        if any(host == b or host.endswith("." + b) for b in blocked):
            return None
        return host or None
    except Exception:
        return None


def guess_company_name(title: str, url: str | None) -> str:
    # Prefer title before separators
    cleaned = re.split(r"[|\-–—:]", title or "")[0].strip()
    if cleaned and len(cleaned) < 80:
        # strip common suffixes
        cleaned = re.sub(
            r"\b(careers?|jobs?|hiring|open roles?|vacancies)\b",
            "",
            cleaned,
            flags=re.I,
        ).strip(" -|–—:")
        if cleaned:
            return cleaned
    domain = extract_domain(url)
    if domain:
        return domain.split(".")[0].replace("-", " ").title()
    return title[:80] if title else "Unknown"


async def fetch_page_text(url: str, max_chars: int = 12000) -> str:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "HireScout/1.0 (+personal job search agent)"},
            )
            if resp.status_code >= 400:
                return ""
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ").split())
            return text[:max_chars]
    except Exception:
        return ""


async def hunter_domain_search(domain: str, limit: int = 10) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.hunter_api_key or not domain:
        return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": settings.hunter_api_key,
                "limit": limit,
            },
        )
        if resp.status_code >= 400:
            return []
        data = resp.json().get("data", {})
        return data.get("emails", []) or []


def categorize_title(title: str | None) -> str | None:
    if not title:
        return None
    t = title.lower()
    if any(k in t for k in ("founder", "co-founder", "cofounder", "ceo", "cto", "coo")):
        return "cofounder"
    if any(k in t for k in ("hr", "talent", "recruiter", "people partner", "human resources")):
        return "hr"
    if any(k in t for k in ("gtm", "go-to-market", "growth", "revenue", "sales")):
        return "gtm"
    if any(k in t for k in ("product manager", "head of product", "vp product", "product lead", "cpo")):
        return "product"
    if any(k in t for k in ("business development", "partnership", "bd manager", "bizdev")):
        return "bd"
    return None
