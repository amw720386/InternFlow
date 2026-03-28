from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Text
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

from app.utils.time_utils import utc_now

if TYPE_CHECKING:
    from app.data.models.company import Company


class PendingLead(SQLModel, table=True):
    __tablename__ = "pending_leads"

    id: Optional[int] = Field(default=None, primary_key=True)
    pdl_person_id: str = Field(index=True, unique=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    linkedin_username: Optional[str] = None
    raw_pdl_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    pdl_profile_updated_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)

    company: Mapped[Optional["Company"]] = Relationship()
