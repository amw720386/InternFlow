from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, event
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from app import config

_engine: Engine | None = None


def _attach_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _sqlite_enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        if engine.dialect.name == "sqlite":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def _ensure_sqlite_parent_dir(url_str: str) -> None:
    u = make_url(url_str)
    if u.drivername != "sqlite" or not u.database:
        return
    db_path = Path(u.database)
    if not db_path.is_absolute():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)


def initialize() -> None:
    global _engine

    import app.data.models  # noqa: F401 — register models with SQLModel metadata

    _ensure_sqlite_parent_dir(config.DATABASE_URL)

    if _engine is None:
        _engine = create_engine(
            config.DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=config.SQL_ECHO,
        )
        _attach_sqlite_foreign_keys(_engine)

    SQLModel.metadata.create_all(_engine)


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError(
            "Database not initialized. Call app.data.repository.initialize() first."
        )
    return _engine


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
