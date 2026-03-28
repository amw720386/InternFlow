import json
from types import SimpleNamespace
from typing import Any

from sqlmodel import Session

from app import config
from app.ai import prompts
from app.data import repository
from app.data.database import get_engine
from app.data.models.company import Company
from app.data.models.lead import Lead
from app.data.models.pending_lead import PendingLead
from app.services.pdl_service import (
    PDLService,
    best_email,
    build_person_search_query,
    linkedin_url_from_username,
    pdl_person_to_lead_payload,
)
from app.utils.outreach_text import fill_outreach_placeholders, format_email_body


def initialize() -> None:
    config.logger.info("database initialize")
    repository.initialize()


def count_pending_leads() -> int:
    with Session(get_engine()) as session:
        return repository.count_pending_leads(session)


def _lead_view(lead: Lead) -> SimpleNamespace:
    return SimpleNamespace(
        id=lead.id,
        pending=False,
        status=lead.status,
        full_name=lead.full_name,
        first_name=lead.first_name,
        last_name=lead.last_name,
        title=lead.title,
        linkedin_username=lead.linkedin_username,
        linkedin_url=linkedin_url_from_username(lead.linkedin_username),
        pdl_profile_updated_at=lead.pdl_profile_updated_at,
        fit_score=lead.fit_score,
        score_web_activity=lead.score_web_activity,
        score_hiring_signals=lead.score_hiring_signals,
        score_company_size=lead.score_company_size,
        reasoning=lead.reasoning,
        outreach_linkedin_template=lead.outreach_linkedin_template,
        outreach_message_score=lead.outreach_message_score,
        ai_input_tokens=lead.ai_input_tokens,
        ai_output_tokens=lead.ai_output_tokens,
        ai_total_tokens=lead.ai_total_tokens,
        created_at=lead.created_at,
    )


def _pending_view(pending: PendingLead) -> SimpleNamespace:
    return SimpleNamespace(
        id=pending.id,
        pending=True,
        status=None,
        full_name=pending.full_name,
        first_name=pending.first_name,
        last_name=pending.last_name,
        title=pending.title,
        linkedin_username=pending.linkedin_username,
        linkedin_url=linkedin_url_from_username(pending.linkedin_username),
        pdl_profile_updated_at=pending.pdl_profile_updated_at,
        fit_score=None,
        score_web_activity=None,
        score_hiring_signals=None,
        score_company_size=None,
        reasoning=None,
        outreach_linkedin_template=None,
        outreach_message_score=None,
        ai_input_tokens=None,
        ai_output_tokens=None,
        ai_total_tokens=None,
        created_at=pending.created_at,
    )


def _company_view(company: Company) -> SimpleNamespace:
    return SimpleNamespace(
        id=company.id,
        name=company.name,
        domain=company.domain,
        size_range=company.size_range,
        industry=company.industry,
        location=company.location,
    )


def _email_from_raw(raw_json: str | None) -> str | None:
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return best_email(data) if isinstance(data, dict) else None


def run_pdl_person_search(
    *,
    size: int,
    job_company_name: str | None = None,
    location_country: str | None = None,
    location_region: str | None = None,
    industry: str | None = None,
    require_linkedin: bool = False,
    include_founders_executives: bool = True,
    dataset: str = "resume",
    scroll_token: str | None = None,
) -> tuple[list[tuple[SimpleNamespace, SimpleNamespace]], str | None, str | None]:
    """Returns ``(results, error, new_scroll_token)``."""
    results: list[tuple[SimpleNamespace, SimpleNamespace]] = []
    try:
        pdl = PDLService()
        query = build_person_search_query(
            job_company_name=job_company_name,
            location_country=location_country,
            location_region=location_region,
            industry=industry,
            require_linkedin=require_linkedin,
            include_founders_executives=include_founders_executives,
        )
        try:
            response = pdl.person_search(
                query=query, size=size, scroll_token=scroll_token, dataset=dataset,
            )
        except RuntimeError as exc:
            err_s = str(exc)
            if err_s.startswith("PDL HTTP 404") and (
                "not_found" in err_s.lower()
                or "no records were found" in err_s.lower()
            ):
                config.logger.info(
                    "pdl person search: no matching profiles (industry must be a PDL canonical value, "
                    "or search is too narrow)"
                )
                return [], None, scroll_token
            raise
        people = response.get("data") or []
        new_scroll_token = response.get("scroll_token")
        config.logger.info(
            "pdl person search total=%s returned=%s scroll_token=%s",
            response.get("total"), len(people), bool(new_scroll_token),
        )

        with Session(get_engine()) as session:
            pending_items: list[PendingLead] = []
            for person in people:
                payload = pdl_person_to_lead_payload(person)
                pending, _is_new, existing_lead = repository.upsert_pending_lead(
                    session, payload
                )
                if existing_lead:
                    company = session.get(Company, existing_lead.company_id)
                    if company:
                        results.append((_lead_view(existing_lead), _company_view(company)))
                elif pending:
                    pending_items.append(pending)

            for pending in pending_items:
                company = session.get(Company, pending.company_id)
                if not company:
                    config.logger.warning(
                        "skip pending id=%s: missing company_id=%s",
                        pending.id,
                        pending.company_id,
                    )
                    continue
                try:
                    email = _email_from_raw(pending.raw_pdl_json)
                    li_url = linkedin_url_from_username(pending.linkedin_username)

                    ai = prompts.research_and_draft_linkedin_outreach(
                        full_name=pending.full_name,
                        first_name=pending.first_name,
                        title=pending.title,
                        company_name=company.name,
                        company_domain=company.domain,
                        company_industry=company.industry,
                        company_size_range=company.size_range,
                        company_location=company.location,
                        linkedin_url=li_url,
                        recipient_email=email,
                        target_industry=industry,
                    )

                    lead = repository.graduate_pending_to_lead(
                        session,
                        pending.id,
                        fit_score=ai.fit_score,
                        reasoning=ai.reasoning,
                        score_web_activity=ai.score_web_activity,
                        score_hiring_signals=ai.score_hiring_signals,
                        score_company_size=ai.score_company_size,
                        outreach_linkedin_template=ai.linkedin_message,
                        outreach_message_score=ai.message_score,
                        ai_input_tokens=ai.ai_input_tokens,
                        ai_output_tokens=ai.ai_output_tokens,
                        ai_total_tokens=ai.ai_total_tokens,
                    )
                    if lead:
                        results.append((_lead_view(lead), _company_view(company)))
                        config.logger.info(
                            "graduated pdl_id=%s fit=%s",
                            lead.pdl_person_id,
                            ai.fit_score,
                        )
                except Exception:
                    config.logger.exception(
                        "AI graduate failed pending_id=%s pdl_person_id=%s — left in pending_leads",
                        pending.id,
                        pending.pdl_person_id,
                    )

        return results, None, new_scroll_token
    except Exception as exc:
        config.logger.exception("run_pdl_person_search failed")
        return [], str(exc), None


def get_browse_page(
    *,
    sort: str,
    company_name: str | None,
    min_score: float | None,
    show_done_deleted: bool = False,
) -> dict[str, Any]:
    with Session(get_engine()) as session:
        lead_rows = repository.list_leads_with_company(
            session,
            sort=sort,
            company_name=company_name,
            min_score=min_score,
            show_done_deleted=show_done_deleted,
        )
        pending_rows = repository.list_pending_leads_with_company(
            session, company_name=company_name,
        )

    leads = [(_lead_view(a), _company_view(b)) for a, b in lead_rows]
    pending = [(_pending_view(a), _company_view(b)) for a, b in pending_rows]
    rows = pending + leads

    config.logger.info(
        "browse sort=%s company=%s leads=%s pending=%s",
        sort, company_name, len(leads), len(pending),
    )
    return {
        "rows": rows,
        "sort": sort,
        "company_name": company_name or "",
        "min_score": min_score,
        "show_done_deleted": show_done_deleted,
    }


def configure_set_lead_status(
    lead_id: int, status: str, export_lead_ids: list[int]
) -> tuple[bool, str | None]:
    if lead_id not in export_lead_ids:
        return False, "not_in_export"
    with Session(get_engine()) as session:
        lead = repository.update_lead_status(session, lead_id, status)
    if lead is None:
        return False, "not_found"
    return True, None


def build_configure_cards(
    lead_ids: list[int], profile: dict[str, str] | None
) -> list[dict[str, Any]]:
    profile = profile or {}
    sender_name = (profile.get("sender_name") or "").strip() or "Your name"
    portfolio_url = (profile.get("portfolio_url") or "").strip() or None

    with Session(get_engine()) as session:
        rows = repository.get_leads_with_companies_ordered(session, lead_ids)

    cards: list[dict[str, Any]] = []
    for lead, company in rows:
        if lead.status in (repository.LEAD_STATUS_DONE, repository.LEAD_STATUS_DELETED):
            continue
        fn = (lead.first_name or "").strip()
        if not fn and lead.full_name:
            fn = lead.full_name.split()[0]
        if not fn:
            fn = "there"
        co_name = (company.name or "").strip() or "your company"
        tit = (lead.title or "").strip() or "your role"
        tmpl = lead.outreach_linkedin_template or ""
        linkedin_filled = fill_outreach_placeholders(
            tmpl, first_name=fn, company_name=co_name, their_title=tit
        )

        email_addr = _email_from_raw(lead.raw_pdl_json)
        email_body = None
        if email_addr:
            email_body = format_email_body(
                linkedin_filled, sender_name=sender_name, portfolio_url=portfolio_url
            )

        li_url = linkedin_url_from_username(lead.linkedin_username)

        cards.append(
            {
                "lead_id": lead.id,
                "full_name": lead.full_name,
                "first_name": lead.first_name,
                "title": lead.title,
                "company_name": company.name,
                "email": email_addr,
                "linkedin_url": li_url,
                "linkedin_filled": linkedin_filled,
                "email_body": email_body,
                "email_subject": f"Internship outreach — {co_name}",
                "fit_score": lead.fit_score,
                "score_web_activity": lead.score_web_activity,
                "score_hiring_signals": lead.score_hiring_signals,
                "score_company_size": lead.score_company_size,
                "message_score": lead.outreach_message_score,
                "reasoning": lead.reasoning or "",
            }
        )
    return cards
