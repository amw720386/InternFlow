from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

from app.utils.time_utils import utc_now

if TYPE_CHECKING:
    from app.data.models.lead import Lead


class OutreachLog(SQLModel, table=True):
    __tablename__ = "outreach_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="leads.id", index=True)
    action_type: Optional[str] = None
    note: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)

    lead: Mapped[Optional["Lead"]] = Relationship(back_populates="outreach_logs")
