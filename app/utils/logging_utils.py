import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

from app.utils.path_utils import PROJECT_ROOT

_LOG_NAME = re.compile(r"^Internflow(-\d{4}-\d{2}-\d{2})?\.log$")


def get_logs_dir() -> Path:
    return PROJECT_ROOT / "logs"


def is_allowed_log_filename(filename: str) -> bool:
    return bool(_LOG_NAME.match(filename))


class InternflowDailyFileHandler(logging.Handler):
    def __init__(self, logs_dir: Path) -> None:
        super().__init__()
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: date | None = None
        self.stream = None
        self._open_for_today()

    def _open_for_today(self) -> None:
        if self.stream:
            self.stream.flush()
            self.stream.close()
            self.stream = None
        path = self.logs_dir / "Internflow.log"
        if path.exists():
            mtime_date = datetime.fromtimestamp(path.stat().st_mtime).date()
            if mtime_date < date.today() and path.stat().st_size > 0:
                arch = self.logs_dir / f"Internflow-{mtime_date.isoformat()}.log"
                if arch.exists():
                    os.remove(arch)
                path.rename(arch)
        self.stream = open(self.logs_dir / "Internflow.log", "a", encoding="utf-8")
        self._current_date = date.today()

    def _rotate_if_needed(self) -> None:
        today = date.today()
        if self._current_date is None:
            self._open_for_today()
            return
        if today == self._current_date:
            return
        if self.stream:
            self.stream.flush()
            self.stream.close()
            self.stream = None
        active = self.logs_dir / "Internflow.log"
        if active.exists() and active.stat().st_size > 0 and self._current_date is not None:
            arch = self.logs_dir / f"Internflow-{self._current_date.isoformat()}.log"
            if arch.exists():
                os.remove(arch)
            active.rename(arch)
        self._open_for_today()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._rotate_if_needed()
            msg = self.format(record)
            if self.stream:
                self.stream.write(msg + "\n")
                self.stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self.stream:
            self.stream.flush()
            self.stream.close()
            self.stream = None
        super().close()


def configure_logging(logs_dir: Path | None = None) -> Path:
    ld = logs_dir or (PROJECT_ROOT / "logs")
    ld.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger("internflow")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = InternflowDailyFileHandler(ld)
    fh.setFormatter(fmt)
    log.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    log.addHandler(ch)

    return ld


__all__ = [
    "InternflowDailyFileHandler",
    "configure_logging",
    "get_logs_dir",
    "is_allowed_log_filename",
]
