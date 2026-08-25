from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: Optional[str] = None
    description: Optional[str] = None
    locations: Optional[str] = None
    stage_hint: Optional[str] = None
    careers_url: Optional[str] = None
    website_url: Optional[str] = None
    hiring_signals: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    title: Optional[str] = None
    category: str
    email: Optional[str] = None
    profile_url: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    company_name: Optional[str] = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    title: str
    url: Optional[str] = None
    role_family: Optional[str] = None
    location: Optional[str] = None
    posted_at: Optional[str] = None


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    status: str
    notes: Optional[str] = None
    next_action_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    company: Optional[CompanyOut] = None


class PipelineUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    next_action_at: Optional[datetime] = None


class ScoutRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str
    stats_json: Optional[str] = None
    error: Optional[str] = None


class ScoutTriggerRequest(BaseModel):
    geo: Optional[str] = Field(default=None, description="Override geo, e.g. Turkey")
    max_companies: Optional[int] = None
    role_families: Optional[List[str]] = None


class CompanyDetail(CompanyOut):
    people: List[PersonOut] = []
    jobs: List[JobOut] = []
    pipeline_status: Optional[str] = None


PIPELINE_STATUSES = [
    "new",
    "researching",
    "to_contact",
    "contacted",
    "replied",
    "interview",
    "rejected",
    "offer",
]
