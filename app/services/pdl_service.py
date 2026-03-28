import json
import re
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app import config

# Curated for the search UI — must match PDL keyword slugs
# (https://docs.peopledatalabs.com/docs/industries).
INDUSTRY_SEARCH_OPTIONS: tuple[str, ...] = tuple(
    sorted(
        {
            "accounting",
            "banking",
            "biotechnology",
            "broadcast media",
            "computer & network security",
            "computer games",
            "computer hardware",
            "computer networking",
            "computer software",
            "construction",
            "consumer electronics",
            "design",
            "e-learning",
            "education management",
            "electrical/electronic manufacturing",
            "entertainment",
            "financial services",
            "higher education",
            "hospital & health care",
            "information technology and services",
            "internet",
            "investment banking",
            "legal services",
            "management consulting",
            "marketing and advertising",
            "mechanical or industrial engineering",
            "media production",
            "non-profit organization management",
            "pharmaceuticals",
            "real estate",
            "retail",
            "telecommunications",
        }
    )
)
INDUSTRY_SEARCH_OPTIONS_SET: frozenset[str] = frozenset(INDUSTRY_SEARCH_OPTIONS)

PDL_BASE_URL = "https://api.peopledatalabs.com/v5"

_PDL_REQUEST_HEADERS_BASE: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "InternFlow/1.0 (+https://peopledatalabs.com/)",
}


def _pdl_text(value: Any) -> str:
    """Strip a scalar PDL field to str; None and bool become '' (API may use false for text fields)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def linkedin_url_from_username(username: str | None) -> str | None:
    u = _pdl_text(username) if not isinstance(username, str) else (username or "").strip()
    if not u:
        return None
    u = u.lstrip("/").removeprefix("in/").removeprefix("linkedin.com/in/")
    return f"https://www.linkedin.com/in/{u}"


def _parse_pdl_date(value: Any) -> datetime | None:
    s = _pdl_text(value)
    if not s:
        return None
    if "T" in s:
        s2 = s.replace("Z", "")
        try:
            return datetime.fromisoformat(s2)
        except ValueError:
            pass
    try:
        d = date.fromisoformat(s[:10])
        return datetime(d.year, d.month, d.day)
    except ValueError:
        return None


# Match any of these in `job_title`. PDL rejects explicit `minimum_should_match`; use a must-wrapped
# bool whose inner clause is should-only (ES still requires ≥1 should to match).
PRESET_RECRUITER_HR_TITLE_PHRASES: list[str] = [
    "recruiter",
    "talent acquisition",
    "talent partner",
    "human resources",
    "people operations",
    "people & culture",
    "people and culture",
    "head of people",
    "head of talent",
    "chief people officer",
    "vp people",
    "vp human resources",
    "vp talent",
    "director of talent",
    "director of people",
    "hr business partner",
    "hr manager",
    "hr director",
    "university recruiter",
    "campus recruiter",
    "technical recruiter",
    "staffing",
    "workforce",
    "people partner",
    "talent coordinator",
    "hiring coordinator",
    "people operations manager",
]


def _recruiter_title_query() -> dict[str, Any]:
    return {
        "bool": {
            "must": [
                {
                    "bool": {
                        "should": [
                            {"match": {"job_title": phrase}}
                            for phrase in PRESET_RECRUITER_HR_TITLE_PHRASES
                        ],
                    }
                }
            ],
        }
    }


# Startups often have no dedicated HR — founders / execs handle hiring outreach.
PRESET_FOUNDER_EXEC_TITLE_PHRASES: list[str] = [
    "founder",
    "co-founder",
    "cofounder",
    "chief executive officer",
    "ceo",
    "president",
    "managing director",
    "chief technology officer",
    "cto",
    "head of engineering",
    "vp engineering",
    "vp of engineering",
]


def _founder_exec_title_query() -> dict[str, Any]:
    return {
        "bool": {
            "must": [
                {
                    "bool": {
                        "should": [
                            {"match": {"job_title": phrase}}
                            for phrase in PRESET_FOUNDER_EXEC_TITLE_PHRASES
                        ],
                    }
                }
            ],
        }
    }


def _job_title_query(*, include_founders_executives: bool) -> dict[str, Any]:
    r = _recruiter_title_query()
    if not include_founders_executives:
        return r
    return {
        "bool": {
            "should": [
                r,
                _founder_exec_title_query(),
            ],
        }
    }


def best_email(person: dict[str, Any]) -> str | None:
    work = _pdl_text(person.get("work_email"))
    if work:
        return work
    rec = _pdl_text(person.get("recommended_personal_email"))
    if rec:
        return rec
    emails = person.get("emails")
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, dict):
            addr = _pdl_text(first.get("address"))
            if addr:
                return addr
    personal = person.get("personal_emails")
    if isinstance(personal, list) and personal:
        addr = _pdl_text(personal[0])
        if addr:
            return addr
    return None


def normalize_canonical_industry(industry: str | None) -> str | None:
    if not industry or not str(industry).strip():
        return None
    s = re.sub(r"\s+", " ", str(industry).strip().lower())
    return s if s in INDUSTRY_SEARCH_OPTIONS_SET else None


def build_person_search_query(
    *,
    job_company_name: str | None = None,
    location_country: str | None = None,
    location_region: str | None = None,
    industry: str | None = None,
    require_linkedin: bool = False,
    include_founders_executives: bool = True,
) -> dict[str, Any]:
    must: list[dict[str, Any]] = [
        _job_title_query(include_founders_executives=include_founders_executives)
    ]
    if job_company_name and job_company_name.strip():
        must.append({"match": {"job_company_name": job_company_name.strip()}})
    if location_country and location_country.strip():
        must.append({"term": {"location_country": location_country.strip().lower()}})
    if location_region and location_region.strip():
        must.append({"match": {"location_region": location_region.strip()}})
    canonical = normalize_canonical_industry(industry)
    if canonical:
        # PDL rejects explicit minimum_should_match; ES defaults to ≥1 match for should-only bools.
        must.append(
            {
                "bool": {
                    "should": [
                        {"term": {"industry": canonical}},
                        {"term": {"job_company_industry": canonical}},
                    ]
                }
            }
        )
    if require_linkedin:
        must.append({"exists": {"field": "linkedin_username"}})
    return {"bool": {"must": must}}


class PDLService:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or config.PDL_API_KEY
        if not self.api_key:
            raise ValueError(
                "PDL API key missing: set PDL_API_KEY in the environment."
            )

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{PDL_BASE_URL}{path}"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            **_PDL_REQUEST_HEADERS_BASE,
            "X-Api-Key": self.api_key,
        }
        req = Request(url, method="POST", data=payload, headers=headers)
        try:
            with urlopen(req, timeout=90) as resp:
                raw = resp.read().decode()
        except HTTPError as e:
            err_body = e.read().decode(errors="replace")
            raise RuntimeError(f"PDL HTTP {e.code}: {err_body}") from e
        except URLError as e:
            raise RuntimeError(f"PDL request failed: {e}") from e

        data = json.loads(raw)
        status = data.get("status")
        if status is not None and status != 200:
            err = data.get("error") or data.get("message") or data
            raise RuntimeError(f"PDL API status {status}: {err}")
        return data

    def person_search(
        self,
        *,
        query: dict[str, Any],
        size: int = 10,
        scroll_token: str | None = None,
        dataset: str = "resume",
    ) -> dict[str, Any]:
        """
        POST /v5/person/search — Elasticsearch `query` + `size` (1–100).
        See https://docs.peopledatalabs.com/docs/reference-person-search-api
        """
        n = max(1, min(100, int(size)))
        body: dict[str, Any] = {
            "query": query,
            "size": n,
            "dataset": dataset,
            "titlecase": False,
        }
        if scroll_token:
            body["scroll_token"] = scroll_token
        return self._post_json("/person/search", body)


def pdl_person_to_lead_payload(person: dict[str, Any]) -> dict[str, Any]:
    """Map a PDL Person Search record to `upsert_lead_from_payload`."""
    pid = person.get("id")
    org_name = _pdl_text(person.get("job_company_name")) or "Unknown"
    website = _pdl_text(person.get("job_company_website")) or None
    domain = None
    if website:
        domain = website.lower().removeprefix("http://").removeprefix("https://").split("/")[0]

    first = _pdl_text(person.get("first_name"))
    last = _pdl_text(person.get("last_name"))
    full = _pdl_text(person.get("full_name"))
    if not full:
        full = f"{first} {last}".strip() or None

    li_username = _pdl_text(person.get("linkedin_username")) or None
    verified = _parse_pdl_date(
        person.get("job_last_verified") or person.get("location_last_updated")
    )

    return {
        "pdl_person_id": pid,
        "company": {
            "name": org_name,
            "domain": domain,
            "industry": _pdl_text(
                person.get("job_company_industry") or person.get("industry")
            )
            or None,
            "size_range": _pdl_text(person.get("job_company_size")) or None,
            "location": _pdl_text(person.get("job_company_location_name")) or None,
        },
        "raw_pdl": person,
        "first_name": first or None,
        "last_name": last or None,
        "full_name": full,
        "title": _pdl_text(person.get("job_title")) or None,
        "linkedin_username": li_username,
        "pdl_profile_updated_at": verified,
        "status": "new",
    }
