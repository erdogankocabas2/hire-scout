from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Company, Job, Person, PipelineItem, ScoutRun, SessionLocal
from .llm import extract_company_bundle
from .providers import (
    build_scout_queries,
    categorize_title,
    extract_domain,
    fetch_page_text,
    guess_company_name,
    hunter_domain_search,
    tavily_search,
)


def _upsert_company(db: Session, payload: dict[str, Any], source: str) -> tuple[Company, bool]:
    domain = payload.get("domain") or extract_domain(payload.get("website_url") or payload.get("careers_url"))
    company: Optional[Company] = None
    created = False

    if domain:
        company = db.query(Company).filter(Company.domain == domain).one_or_none()

    if company is None and payload.get("name"):
        company = (
            db.query(Company)
            .filter(Company.name.ilike(payload["name"]))
            .one_or_none()
        )

    if company is None:
        company = Company(
            name=payload.get("name") or "Unknown",
            domain=domain,
            description=payload.get("description"),
            locations=payload.get("locations"),
            stage_hint=payload.get("stage_hint"),
            careers_url=payload.get("careers_url"),
            website_url=payload.get("website_url"),
            hiring_signals=payload.get("hiring_signals"),
            source=source,
        )
        db.add(company)
        db.flush()
        db.add(PipelineItem(company_id=company.id, status="new"))
        created = True
    else:
        company.last_seen_at = datetime.utcnow()
        for field in (
            "description",
            "locations",
            "stage_hint",
            "careers_url",
            "website_url",
            "hiring_signals",
        ):
            val = payload.get(field)
            if val and not getattr(company, field):
                setattr(company, field, val)
        if domain and not company.domain:
            company.domain = domain

    return company, created


def _upsert_job(db: Session, company: Company, job: dict[str, Any]) -> bool:
    title = (job.get("title") or "").strip()
    if not title:
        return False
    existing = (
        db.query(Job)
        .filter(Job.company_id == company.id, Job.title == title)
        .one_or_none()
    )
    if existing:
        return False
    db.add(
        Job(
            company_id=company.id,
            title=title,
            url=job.get("url"),
            role_family=job.get("role_family"),
            location=job.get("location"),
            posted_at=job.get("posted_at"),
        )
    )
    return True


def _upsert_person(db: Session, company: Company, person: dict[str, Any], source: str) -> bool:
    name = (person.get("name") or "").strip()
    if not name:
        return False
    category = person.get("category") or categorize_title(person.get("title")) or "hr"
    existing = (
        db.query(Person)
        .filter(
            Person.company_id == company.id,
            Person.name == name,
            Person.category == category,
        )
        .one_or_none()
    )
    if existing:
        if person.get("email") and not existing.email:
            existing.email = person["email"]
        if person.get("profile_url") and not existing.profile_url:
            existing.profile_url = person["profile_url"]
        return False

    db.add(
        Person(
            company_id=company.id,
            name=name,
            title=person.get("title"),
            category=category,
            email=person.get("email"),
            profile_url=person.get("profile_url"),
            source=source,
            confidence=person.get("confidence"),
        )
    )
    return True


async def enrich_people_from_hunter(db: Session, company: Company) -> int:
    if not company.domain:
        return 0
    emails = await hunter_domain_search(company.domain, limit=12)
    added = 0
    for row in emails:
        title = row.get("position") or ""
        category = categorize_title(title)
        # Prefer relevant categories; always keep founders/hr if present
        if category is None:
            # keep senior-ish contacts lightly
            if not any(
                k in (title or "").lower()
                for k in ("founder", "ceo", "head", "director", "vp", "chief", "talent", "hr")
            ):
                continue
            category = "hr"
        first = row.get("first_name") or ""
        last = row.get("last_name") or ""
        name = f"{first} {last}".strip() or row.get("value") or "Unknown"
        created = _upsert_person(
            db,
            company,
            {
                "name": name,
                "title": title,
                "category": category,
                "email": row.get("value"),
                "confidence": (row.get("confidence") or 0) / 100.0,
            },
            source="hunter",
        )
        if created:
            added += 1
    return added


async def run_scout(
    *,
    geo: Optional[str] = None,
    max_companies: Optional[int] = None,
    role_families: Optional[list[str]] = None,
) -> dict[str, Any]:
    settings = get_settings()
    geo = geo or settings.scout_geo
    max_companies = max_companies or settings.scout_max_companies_per_run
    role_families = role_families or settings.role_families

    db = SessionLocal()
    run = ScoutRun(status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    stats = {
        "geo": geo,
        "queries": 0,
        "search_hits": 0,
        "companies_created": 0,
        "companies_updated": 0,
        "jobs_added": 0,
        "people_added": 0,
        "hunter_people_added": 0,
    }

    try:
        queries = build_scout_queries(geo, role_families)
        stats["queries"] = len(queries)

        candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for query in queries:
            try:
                results = await tavily_search(query, max_results=6)
            except Exception as exc:
                # Keep going if one query fails
                stats.setdefault("search_errors", [])
                if len(stats["search_errors"]) < 5:
                    stats["search_errors"].append(str(exc)[:200])
                continue
            for item in results:
                url = item.get("url") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(
                    {
                        "title": item.get("title") or "",
                        "url": url,
                        "snippet": item.get("content") or item.get("snippet") or "",
                        "query": query,
                    }
                )
        if not candidates and stats.get("search_errors"):
            raise RuntimeError(
                "No search results. First error: " + stats["search_errors"][0]
            )
        stats["search_hits"] = len(candidates)

        processed_domains: set[str] = set()
        companies_touched = 0

        for cand in candidates:
            if companies_touched >= max_companies:
                break

            page_text = await fetch_page_text(cand["url"])
            bundle = extract_company_bundle(
                geo=geo,
                search_title=cand["title"],
                search_url=cand["url"],
                search_snippet=cand["snippet"],
                page_text=page_text or cand["snippet"],
            )

            if not bundle:
                # Fallback minimal company from search hit
                domain = extract_domain(cand["url"])
                if not domain or domain in processed_domains:
                    continue
                bundle = {
                    "company": {
                        "name": guess_company_name(cand["title"], cand["url"]),
                        "domain": domain,
                        "description": cand["snippet"][:400],
                        "locations": geo,
                        "website_url": f"https://{domain}",
                        "careers_url": cand["url"] if "career" in cand["url"].lower() or "job" in cand["url"].lower() else None,
                        "hiring_signals": cand["snippet"][:280],
                    },
                    "jobs": [],
                    "people": [],
                }

            company_payload = bundle.get("company") or {}
            domain = company_payload.get("domain") or extract_domain(
                company_payload.get("website_url") or cand["url"]
            )
            if domain and domain in processed_domains:
                continue
            if domain:
                processed_domains.add(domain)
                company_payload["domain"] = domain
            if not company_payload.get("name"):
                company_payload["name"] = guess_company_name(cand["title"], cand["url"])
            if not company_payload.get("locations"):
                company_payload["locations"] = geo

            company, created = _upsert_company(db, company_payload, source="tavily+llm")
            if created:
                stats["companies_created"] += 1
            else:
                stats["companies_updated"] += 1
            companies_touched += 1

            for job in bundle.get("jobs") or []:
                if _upsert_job(db, company, job):
                    stats["jobs_added"] += 1

            for person in bundle.get("people") or []:
                if _upsert_person(db, company, person, source="llm"):
                    stats["people_added"] += 1

            hunter_added = await enrich_people_from_hunter(db, company)
            stats["hunter_people_added"] += hunter_added
            stats["people_added"] += hunter_added

            db.commit()

        run.status = "completed"
        run.finished_at = datetime.utcnow()
        run.stats_json = json.dumps(stats)
        db.commit()
        return {"run_id": run.id, "status": "completed", "stats": stats}
    except Exception as exc:
        db.rollback()
        run = db.query(ScoutRun).filter(ScoutRun.id == run.id).one()
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error = str(exc)
        run.stats_json = json.dumps(stats)
        db.commit()
        return {"run_id": run.id, "status": "failed", "error": str(exc), "stats": stats}
    finally:
        db.close()
