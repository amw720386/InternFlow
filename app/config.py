import logging
import os

import yaml
from dotenv import load_dotenv

from app.path_utils import PROJECT_ROOT
from app.utils.logging_utils import configure_logging

load_dotenv()

_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _load_yaml() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return data


_cfg = _load_yaml()
_db = _cfg.get("database") or {}

_sqlite_path = PROJECT_ROOT / _db.get("sqlite_path")

DATABASE_URL = f"sqlite:///{_sqlite_path.resolve().as_posix()}"
SQL_ECHO = bool(_db.get("echo", False))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDL_API_KEY = os.getenv("PDL_API_KEY")

LOGS_DIR = configure_logging(PROJECT_ROOT / "logs")
logger = logging.getLogger("internflow")
