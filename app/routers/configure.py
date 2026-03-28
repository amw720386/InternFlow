from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import config
from app.data import repository
from app.services import db_service
from app.templating import templates

router = APIRouter(prefix="/configure", tags=["configure"])

_SESSION_IDS = "configure_lead_ids"
_SESSION_PROFILE = "configure_profile"


def _int_ids(raw: list[Any]) -> list[int]:
    out: list[int] = []
    for x in raw or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    seen: set[int] = set()
    uniq: list[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def browse_session_flags(request: Request) -> dict[str, bool]:
    ids = request.session.get(_SESSION_IDS)
    profile = request.session.get(_SESSION_PROFILE)
    return {
        "configure_awaiting_profile": bool(ids) and not profile,
        "configure_ready": bool(ids) and bool(profile),
    }


@router.post("/export")
async def export_leads(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ids = _int_ids(data.get("lead_ids"))
    if not ids:
        return JSONResponse({"ok": False, "error": "no lead ids"}, status_code=400)
    request.session[_SESSION_IDS] = ids
    request.session.pop(_SESSION_PROFILE, None)
    config.logger.info("configure export count=%s", len(ids))
    return JSONResponse({"ok": True, "count": len(ids)})


@router.post("/profile")
async def save_profile(request: Request):
    form = await request.form()
    request.session[_SESSION_PROFILE] = {
        "sender_name": (form.get("sender_name") or "").strip(),
        "sender_first_name": (form.get("sender_first_name") or "").strip(),
        "portfolio_url": (form.get("portfolio_url") or "").strip(),
    }
    return RedirectResponse(url="/configure", status_code=303)


@router.post("/clear")
def clear_session(request: Request):
    request.session.pop(_SESSION_IDS, None)
    request.session.pop(_SESSION_PROFILE, None)
    return RedirectResponse(url="/configure", status_code=303)


_VALID_STATUSES = frozenset({repository.LEAD_STATUS_DONE, repository.LEAD_STATUS_DELETED})


@router.post("/lead/status")
async def update_lead_status(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    lead_id = data.get("lead_id")
    status = data.get("status")
    if lead_id is None:
        return JSONResponse({"ok": False, "error": "missing lead_id"}, status_code=400)
    try:
        lead_id = int(lead_id)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "invalid lead_id"}, status_code=400)
    if status not in _VALID_STATUSES:
        return JSONResponse({"ok": False, "error": "invalid status"}, status_code=400)
    export_ids: list[int] = list(request.session.get(_SESSION_IDS) or [])
    ok, err = db_service.configure_set_lead_status(lead_id, status, export_ids)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return JSONResponse({"ok": True})


@router.get("/")
def configure_page(request: Request):
    ids: list[int] = list(request.session.get(_SESSION_IDS) or [])
    profile = request.session.get(_SESSION_PROFILE)

    pending = bool(ids) and not profile
    ready = bool(ids) and bool(profile)

    cards: list[dict] = []
    if ready and profile and isinstance(profile, dict):
        cards = db_service.build_configure_cards(ids, profile)

    return templates.TemplateResponse(
        request,
        "pages/configure.html",
        {
            "has_export": bool(ids),
            "pending_profile": pending,
            "ready": ready,
            "cards": cards,
            "queue_empty": ready and bool(profile) and bool(ids) and len(cards) == 0,
            "profile": profile or {},
        },
    )
