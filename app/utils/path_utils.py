"""Repository-root path helpers (single definition for the project tree)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
