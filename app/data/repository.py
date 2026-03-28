import json
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.data import database
from app.data.models.company import Company
from app.data.models.lead import Lead
from app.data.models.outreach_log import OutreachLog
from app.data.models.pending_lead import PendingLead


def initialize() -> None:
    database.initialize()


def get_or_create_company_by_name(
    session: Session,
    *,
    name: str,
    domain: str | None = None,
    industry: str | None = None,
    size_range: str | None = None,
    location: str | None = None,
) -> Company:
    name_clean = (name or "").strip() or "Unknown"
    existing = session.exec(select(Company).where(Company.name == name_clean)).first()
    if existing:
        changed = False
        if domain and not existing.domain:
            existing.domain = domain
            changed = True
        if industry and not existing.industry:
            existing.industry = industry
            changed = True
        if size_range and not existing.size_range:
            existing.size_range = size_range
            changed = True
        if location and not existing.location:
            existing.location = location
            changed = True
        if changed:
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing

    company = Company(
        name=name_clean,
        domain=domain,
        industry=industry,
        size_range=size_range,
        location=location,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def _company_from_payload(session: Session, payload: dict[str, Any]) -> Company:
    cp = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    org_name = (cp.get("name") or "").strip() or "Unknown"
    return get_or_create_company_by_name(
        session,
        name=org_name,
        domain=cp.get("domain"),
        industry=cp.get("industry"),
        size_range=cp.get("size_range"),
        location=cp.get("location"),
    )


def _raw_json_str(payload: dict[str, Any]) -> str:
    raw = payload.get("raw_pdl")
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str) and raw:
        return raw
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# PendingLead operations
# ---------------------------------------------------------------------------

def upsert_pending_lead(
    session: Session, payload: dict[str, Any]
) -> tuple[PendingLead | None, bool, Lead | None]:
    """Create or update a PendingLead from a PDL payload.

    Returns ``(pending, is_new, existing_lead)``.
    If the person already has a full Lead row, returns ``(None, False, lead)``.
    """
    pdl_id = payload.get("pdl_person_id")
    if not pdl_id:
        raise ValueError("payload missing pdl_person_id")

    existing_lead = session.exec(
        select(Lead).where(Lead.pdl_person_id == pdl_id)
    ).first()
    if existing_lead:
        return None, False, existing_lead

    company = _company_from_payload(session, payload)
    raw_str = _raw_json_str(payload)

    first = (payload.get("first_name") or "").strip()
    last = (payload.get("last_name") or "").strip()
    full_name = payload.get("full_name") or (f"{first} {last}".strip() or None)

    existing_pending = session.exec(
        select(PendingLead).where(PendingLead.pdl_person_id == pdl_id)
    ).first()
    if existing_pending:
        existing_pending.company_id = company.id
        existing_pending.full_name = full_name or existing_pending.full_name
        existing_pending.first_name = first or existing_pending.first_name
        existing_pending.last_name = last or existing_pending.last_name
        existing_pending.title = payload.get("title") or existing_pending.title
        if payload.get("linkedin_username"):
            existing_pending.linkedin_username = payload["linkedin_username"]
        existing_pending.raw_pdl_json = raw_str
        if payload.get("pdl_profile_updated_at") is not None:
            existing_pending.pdl_profile_updated_at = payload["pdl_profile_updated_at"]
        session.add(existing_pending)
        session.commit()
        session.refresh(existing_pending)
        return existing_pending, False, None

    pending = PendingLead(
        pdl_person_id=pdl_id,
        company_id=company.id,
        full_name=full_name,
        first_name=first or None,
        last_name=last or None,
        title=payload.get("title"),
        linkedin_username=payload.get("linkedin_username"),
        raw_pdl_json=raw_str,
        pdl_profile_updated_at=payload.get("pdl_profile_updated_at"),
    )
    session.add(pending)
    session.commit()
    session.refresh(pending)
    return pending, True, None


def graduate_pending_to_lead(
    session: Session,
    pending_lead_id: int,
    *,
    fit_score: float,
    reasoning: str,
    score_web_activity: float,
    score_hiring_signals: float,
    score_company_size: float,
    outreach_linkedin_template: str | None = None,
    outreach_message_score: float | None = None,
    ai_input_tokens: int | None = None,
    ai_output_tokens: int | None = None,
    ai_total_tokens: int | None = None,
) -> Lead | None:
    """Promote a PendingLead to a full Lead with AI enrichment data."""
    pending = session.get(PendingLead, pending_lead_id)
    if not pending:
        return None

    lead = Lead(
        pdl_person_id=pending.pdl_person_id,
        company_id=pending.company_id,
        full_name=pending.full_name,
        first_name=pending.first_name,
        last_name=pending.last_name,
        title=pending.title,
        linkedin_username=pending.linkedin_username,
        raw_pdl_json=pending.raw_pdl_json,
        pdl_profile_updated_at=pending.pdl_profile_updated_at,
        fit_score=fit_score,
        score_web_activity=score_web_activity,
        score_hiring_signals=score_hiring_signals,
        score_company_size=score_company_size,
        reasoning=reasoning,
        outreach_linkedin_template=outreach_linkedin_template,
        outreach_message_score=outreach_message_score,
        ai_input_tokens=ai_input_tokens,
        ai_output_tokens=ai_output_tokens,
        ai_total_tokens=ai_total_tokens,
        status="new",
    )
    session.add(lead)
    session.delete(pending)
    session.commit()
    session.refresh(lead)
    return lead


LEAD_STATUS_DONE = "DONE"
LEAD_STATUS_DELETED = "DELETED"


def update_lead_status(session: Session, lead_id: int, status: str) -> Lead | None:
    lead = session.get(Lead, lead_id)
    if not lead:
        return None
    lead.status = status
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def get_leads_with_companies_ordered(
    session: Session, lead_ids: list[int]
) -> list[tuple[Lead, Company]]:
    if not lead_ids:
        return []
    stmt = (
        select(Lead, Company)
        .join(Company, Lead.company_id == Company.id)
        .where(Lead.id.in_(lead_ids))
    )
    rows = list(session.exec(stmt).all())
    by_id: dict[int, tuple[Lead, Company]] = {
        lead.id: (lead, co) for lead, co in rows if lead.id is not None
    }
    return [by_id[i] for i in lead_ids if i in by_id]


def list_recent_outreach_logs(
    session: Session, *, limit: int = 20
) -> list[tuple[OutreachLog, Lead]]:
    stmt = (
        select(OutreachLog, Lead)
        .join(Lead, OutreachLog.lead_id == Lead.id)
        .order_by(OutreachLog.timestamp.desc())
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def list_leads_with_company(
    session: Session,
    *,
    sort: str = "created_desc",
    company_name: str | None = None,
    min_score: float | None = None,
    show_done_deleted: bool = False,
) -> list[tuple[Lead, Company]]:
    stmt = select(Lead, Company).join(Company, Lead.company_id == Company.id)
    if not show_done_deleted:
        stmt = stmt.where(
            or_(
                Lead.status.is_(None),
                Lead.status.not_in([LEAD_STATUS_DONE, LEAD_STATUS_DELETED]),
            )
        )
    if company_name:
        n = company_name.strip()
        if n:
            pat = f"%{n.lower()}%"
            stmt = stmt.where(func.lower(Company.name).like(pat))
    if min_score is not None:
        stmt = stmt.where(Lead.fit_score >= min_score)

    if sort == "created_desc":
        stmt = stmt.order_by(Lead.created_at.desc())
    elif sort == "created_asc":
        stmt = stmt.order_by(Lead.created_at.asc())
    elif sort == "company":
        stmt = stmt.order_by(Company.name.asc())
    elif sort == "company_size":
        stmt = stmt.order_by(
            func.coalesce(Company.size_range, "").asc(), Company.name.asc()
        )
    elif sort == "score_desc":
        stmt = stmt.order_by(Lead.fit_score.desc(), Lead.created_at.desc())
    elif sort == "score_asc":
        stmt = stmt.order_by(Lead.fit_score.asc(), Lead.created_at.desc())
    else:
        stmt = stmt.order_by(Lead.created_at.desc())

    return list(session.exec(stmt).all())


def list_pending_leads_with_company(
    session: Session,
    *,
    company_name: str | None = None,
) -> list[tuple[PendingLead, Company]]:
    stmt = (
        select(PendingLead, Company)
        .join(Company, PendingLead.company_id == Company.id)
    )
    if company_name:
        n = company_name.strip()
        if n:
            pat = f"%{n.lower()}%"
            stmt = stmt.where(func.lower(Company.name).like(pat))
    stmt = stmt.order_by(PendingLead.created_at.desc())
    return list(session.exec(stmt).all())


def count_pending_leads(session: Session) -> int:
    n = session.exec(select(func.count(PendingLead.id))).one()
    return int(n)
