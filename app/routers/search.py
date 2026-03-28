from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import config
from app.services import db_service, search_job_service
from app.services.pdl_service import INDUSTRY_SEARCH_OPTIONS, INDUSTRY_SEARCH_OPTIONS_SET
from app.templating import templates

router = APIRouter()

_SESSION_FORM = "search_form_draft"


def _default_search_form() -> dict:
    return {
        "size": 10,
        "dataset": "resume",
        "require_linkedin": True,
        "include_founders": True,
        "industry": "",
        "job_company_name": "",
        "location_country": "",
        "location_region": "",
        "details_open": False,
    }


@router.api_route("/search", methods=["GET", "POST"])
async def search_page(request: Request):
    error = None
    success = None
    search_form = dict(_default_search_form())
    saved = request.session.get(_SESSION_FORM)
    if isinstance(saved, dict):
        search_form.update({k: saved[k] for k in search_form if k in saved})
    ind0 = search_form.get("industry")
    if not ind0 or ind0 not in INDUSTRY_SEARCH_OPTIONS_SET:
        search_form["industry"] = ""

    if request.method == "POST":
        form = await request.form()
        form_dict = {k: v for k, v in form.multi_items()}
        try:
            size = max(1, min(100, int(form_dict.get("size") or 10)))
        except (TypeError, ValueError):
            config.logger.warning("search rejected: invalid size parameter %r", form_dict.get("size"))
            return RedirectResponse(url="/search?err=invalid_size", status_code=303)
        dataset = (str(form_dict.get("dataset") or "resume")).strip() or "resume"
        require_linkedin = (form_dict.get("require_linkedin") or "").strip().lower() in (
            "1", "true", "on", "yes",
        )
        include_founders = form_dict.get("include_founders") == "1"
        industry = (str(form_dict.get("industry") or "")).strip()
        if not industry or industry not in INDUSTRY_SEARCH_OPTIONS_SET:
            industry = ""
        job_company_name = (str(form_dict.get("job_company_name") or "")).strip()
        location_country = (str(form_dict.get("location_country") or "")).strip()
        location_region = (str(form_dict.get("location_region") or "")).strip()

        search_form = {
            "size": size,
            "dataset": dataset,
            "require_linkedin": require_linkedin,
            "include_founders": include_founders,
            "industry": industry,
            "job_company_name": job_company_name,
            "location_country": location_country,
            "location_region": location_region,
            "details_open": bool(job_company_name or location_country or location_region),
        }
        request.session[_SESSION_FORM] = search_form

        sk = search_job_service.build_scroll_key(
            industry=industry,
            company=job_company_name,
            country=location_country,
            region=location_region,
            dataset=dataset,
            require_linkedin=require_linkedin,
            include_founders=include_founders,
        )
        scroll_token = search_job_service.get_scroll_token(sk)

        started, busy_err = search_job_service.try_start_search(
            scroll_key=sk,
            scroll_token=scroll_token,
            size=size,
            job_company_name=job_company_name or None,
            location_country=location_country or None,
            location_region=location_region or None,
            industry=industry or None,
            require_linkedin=require_linkedin,
            include_founders_executives=include_founders,
            dataset=dataset,
        )

        if not started:
            config.logger.warning("search rejected: %s", busy_err)
            return RedirectResponse(url="/search?err=busy", status_code=303)

        config.logger.info("search queued background size=%s dataset=%s", size, dataset)
        return RedirectResponse(url="/search?started=1", status_code=303)

    qp = request.query_params
    if qp.get("started") == "1":
        success = (
            "Search started in the background. Open Browse to see rows as they finish; "
            "pending people appear first while AI runs."
        )
    if qp.get("err") == "busy":
        error = "A search is already running. Wait for it to finish, then try again."
    if qp.get("err") == "invalid_size":
        error = "Enter a valid number of people to fetch (1–100)."

    job_err = search_job_service.take_last_job_error()
    if job_err:
        error = job_err

    pending_count = db_service.count_pending_leads()
    search_busy = search_job_service.is_search_running()

    return templates.TemplateResponse(
        request,
        "pages/search.html",
        {
            "error": error,
            "success": success,
            "search_form": search_form,
            "industry_options": INDUSTRY_SEARCH_OPTIONS,
            "pending_count": pending_count,
            "search_busy": search_busy,
            "poll_job_status": bool(success or search_busy) and not error,
        },
    )


@router.get("/search/job-status")
def search_job_status():
    return JSONResponse(
        {
            "running": search_job_service.is_search_running(),
            "error": search_job_service.peek_last_job_error(),
        }
    )
