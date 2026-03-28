"""Background PDL + AI search (one in-flight job per process)."""

from __future__ import annotations

import hashlib
import threading

from app import config

_state_lock = threading.Lock()
_running = False
_scroll_tokens: dict[str, str | None] = {}
_scroll_lock = threading.Lock()
_last_job_error: str | None = None


def is_search_running() -> bool:
    with _state_lock:
        return _running


def take_last_job_error() -> str | None:
    global _last_job_error
    with _state_lock:
        err = _last_job_error
        _last_job_error = None
        return err


def peek_last_job_error() -> str | None:
    with _state_lock:
        return _last_job_error


def build_scroll_key(
    *,
    industry: str,
    company: str,
    country: str,
    region: str,
    dataset: str,
    require_linkedin: bool,
    include_founders: bool,
) -> str:
    raw = (
        f"{industry}|{company}|{country}|{region}|{dataset}|"
        f"{int(require_linkedin)}|{int(include_founders)}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_scroll_token(scroll_key: str) -> str | None:
    with _scroll_lock:
        return _scroll_tokens.get(scroll_key)


def _set_scroll_token(scroll_key: str, token: str | None) -> None:
    with _scroll_lock:
        _scroll_tokens[scroll_key] = token


def try_start_search(
    *,
    scroll_key: str,
    scroll_token: str | None,
    size: int,
    job_company_name: str | None,
    location_country: str | None,
    location_region: str | None,
    industry: str | None,
    require_linkedin: bool,
    include_founders_executives: bool,
    dataset: str,
) -> tuple[bool, str | None]:
    global _running, _last_job_error

    with _state_lock:
        if _running:
            return False, "A search is already running. Wait for it to finish, then try again."
        _running = True
        _last_job_error = None

    def run() -> None:
        global _running, _last_job_error
        try:
            from app.services import db_service

            _results, err, new_token = db_service.run_pdl_person_search(
                size=size,
                job_company_name=job_company_name,
                location_country=location_country,
                location_region=location_region,
                industry=industry,
                require_linkedin=require_linkedin,
                include_founders_executives=include_founders_executives,
                dataset=dataset,
                scroll_token=scroll_token,
            )
            if err:
                with _state_lock:
                    _last_job_error = err
                config.logger.error("background search failed: %s", err)
            _set_scroll_token(scroll_key, new_token)
            if not err:
                config.logger.info("background search finished (%s rows)", len(_results))
        except Exception:
            config.logger.exception("background search crashed")
            with _state_lock:
                _last_job_error = "Search failed with an unexpected error. Check logs."
        finally:
            with _state_lock:
                _running = False

    threading.Thread(target=run, name="internflow-pdl-search", daemon=True).start()
    return True, None
