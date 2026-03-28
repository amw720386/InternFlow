from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse

from app import config
from app.utils.logging_utils import get_logs_dir, is_allowed_log_filename

router = APIRouter()


@router.get("/")
def home():
    return RedirectResponse(url="/search", status_code=302)


@router.get("/logs/{filename}", response_class=PlainTextResponse)
def log_file_plain(filename: str):
    if not is_allowed_log_filename(filename):
        raise HTTPException(status_code=404)
    path: Path = get_logs_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    config.logger.info("route GET /logs/%s", filename)
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
