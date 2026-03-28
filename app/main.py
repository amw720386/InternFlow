import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import app.config  # noqa: F401
from app import config
from app.utils.path_utils import PROJECT_ROOT
from app.routers import browse, configure, index, search
from app.services import db_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.logger.info("database initialize (lifespan)")
    db_service.initialize()
    yield


app = FastAPI(lifespan=lifespan, title="InternFlow")

_static_dir = PROJECT_ROOT / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.add_middleware(
    SessionMiddleware,
    # YES I KNOW THIS PROJECT IS NOT MEANT TO BE USED IN PRODUCTION, 
    # IF YOU DO WANT TO EVENTUALLY USE THIS IN PRODUCTION PLEASE CHANGE THIS
    secret_key=os.environ.get("SECRET_KEY", "internflow-change-me"), 
    session_cookie="internflow_session",
    https_only=False,
)

app.include_router(index.router)
app.include_router(search.router)
app.include_router(browse.router)
app.include_router(configure.router)
