from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..db import Company, Job, Person, PipelineItem, ScoutRun, get_db
from ..schemas import (
    PIPELINE_STATUSES,
    CompanyDetail,
    CompanyOut,
    JobOut,
    PersonOut,
    PipelineOut,
    PipelineUpdate,
    ScoutRunOut,
    ScoutTriggerRequest,
)
from ..scout.runner import run_scout

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Company).order_by(Company.last_seen_at.desc())
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Company.name.ilike(like), Company.domain.ilike(like)))
    return query.limit(200).all()


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .options(joinedload(Company.people), joinedload(Company.jobs), joinedload(Company.pipeline))
        .filter(Company.id == company_id)
        .one_or_none()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyDetail(
        id=company.id,
        name=company.name,
        domain=company.domain,
        description=company.description,
        locations=company.locations,
        stage_hint=company.stage_hint,
        careers_url=company.careers_url,
        website_url=company.website_url,
        hiring_signals=company.hiring_signals,
        source=company.source,
        created_at=company.created_at,
        last_seen_at=company.last_seen_at,
        people=[PersonOut.model_validate(p) for p in company.people],
        jobs=[JobOut.model_validate(j) for j in company.jobs],
        pipeline_status=company.pipeline.status if company.pipeline else None,
    )


@router.get("/people", response_model=List[PersonOut])
def list_people(
    category: Optional[str] = None,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Person).join(Company).order_by(Person.created_at.desc())
    if category:
        query = query.filter(Person.category == category)
    if company_id:
        query = query.filter(Person.company_id == company_id)
    rows = query.limit(300).all()
    out: List[PersonOut] = []
    for p in rows:
        item = PersonOut.model_validate(p)
        item.company_name = p.company.name if p.company else None
        out.append(item)
    return out


@router.get("/jobs", response_model=List[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.created_at.desc()).limit(300).all()


@router.get("/pipeline", response_model=List[PipelineOut])
def list_pipeline(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(PipelineItem)
        .options(joinedload(PipelineItem.company))
        .order_by(PipelineItem.updated_at.desc())
    )
    if status:
        query = query.filter(PipelineItem.status == status)
    return query.limit(300).all()


@router.patch("/pipeline/{company_id}", response_model=PipelineOut)
def update_pipeline(company_id: int, body: PipelineUpdate, db: Session = Depends(get_db)):
    item = (
        db.query(PipelineItem)
        .options(joinedload(PipelineItem.company))
        .filter(PipelineItem.company_id == company_id)
        .one_or_none()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    if body.status is not None:
        if body.status not in PIPELINE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        item.status = body.status
    if body.notes is not None:
        item.notes = body.notes
    if body.next_action_at is not None:
        item.next_action_at = body.next_action_at
    db.commit()
    db.refresh(item)
    return item


@router.get("/scout/runs", response_model=List[ScoutRunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.query(ScoutRun).order_by(ScoutRun.started_at.desc()).limit(30).all()


@router.post("/scout/run")
async def trigger_scout(body: Optional[ScoutTriggerRequest] = None):
    body = body or ScoutTriggerRequest()
    result = await run_scout(
        geo=body.geo,
        max_companies=body.max_companies,
        role_families=body.role_families,
    )
    return result


@router.get("/meta")
def meta():
    from ..config import get_settings

    s = get_settings()
    return {
        "geo": s.scout_geo,
        "role_families": s.role_families,
        "cron_hour": s.scout_cron_hour,
        "cron_minute": s.scout_cron_minute,
        "pipeline_statuses": PIPELINE_STATUSES,
        "has_openai": bool(s.openai_api_key),
        "has_tavily": bool(s.tavily_api_key),
        "has_hunter": bool(s.hunter_api_key),
    }
