from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from ..config import get_settings

EXTRACT_SCHEMA_HINT = """
Return ONLY valid JSON with this shape:
{
  "company": {
    "name": "string",
    "domain": "string or null",
    "description": "short string",
    "locations": "string",
    "stage_hint": "string or null",
    "careers_url": "string or null",
    "website_url": "string or null",
    "hiring_signals": "short string"
  },
  "jobs": [
    {"title": "string", "url": "string or null", "role_family": "gtm|product|bd|other", "location": "string or null"}
  ],
  "people": [
    {"name": "string", "title": "string", "category": "cofounder|hr|gtm|product|bd", "profile_url": "string or null", "confidence": 0.0}
  ]
}
Only include people relevant to hiring outreach for GTM/Product/BD roles (founders, HR/talent, GTM/product/BD leaders).
If unsure, omit. Prefer Turkey-related companies when geo is Turkey.
"""


def extract_company_bundle(
    *,
    geo: str,
    search_title: str,
    search_url: str,
    search_snippet: str,
    page_text: str,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""You are helping a job seeker scout companies in {geo} for GTM / Product / Business Development roles.

Search result title: {search_title}
URL: {search_url}
Snippet: {search_snippet}

Page text excerpt:
{page_text[:9000]}

{EXTRACT_SCHEMA_HINT}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured hiring scout data as JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict) or "company" not in data:
            return None
        return data
    except Exception:
        return None
