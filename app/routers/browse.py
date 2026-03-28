from fastapi import APIRouter, Request

from app import config
from app.routers.configure import browse_session_flags
from app.services import db_service
from app.templating import templates

router = APIRouter()


@router.get("/browse")
def browse(request: Request):
    qp = request.query_params
    sort = qp.get("sort") or "created_desc"
    company_name = (qp.get("company_name") or "").strip() or None
    min_score_raw = qp.get("min_score")
    min_score: float | None = None
    if min_score_raw not in (None, ""):
        try:
            min_score = float(min_score_raw)
        except ValueError:
            min_score = None
    show_done_deleted = qp.get("show_done_deleted") == "1"

    config.logger.info("route GET /browse sort=%s company=%s", sort, company_name)

    data = db_service.get_browse_page(
        sort=sort,
        company_name=company_name,
        min_score=min_score,
        show_done_deleted=show_done_deleted,
    )

    ctx = {
        **browse_session_flags(request),
        **data,
    }
    return templates.TemplateResponse(request, "pages/browse.html", ctx)
