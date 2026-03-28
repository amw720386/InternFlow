from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Text
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

from app.utils.time_utils import utc_now

if TYPE_CHECKING:
    from app.data.models.company import Company
    from app.data.models.message_variant import MessageVariant
    from app.data.models.outreach_log import OutreachLog


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: Optional[int] = Field(default=None, primary_key=True)
    pdl_person_id: Optional[str] = Field(default=None, index=True, unique=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    linkedin_username: Optional[str] = None
    raw_pdl_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    pdl_profile_updated_at: Optional[datetime] = None
    fit_score: Optional[float] = None
    score_web_activity: Optional[float] = None
    score_hiring_signals: Optional[float] = None
    score_company_size: Optional[float] = None
    reasoning: Optional[str] = Field(default=None, sa_column=Column(Text))
    outreach_linkedin_template: Optional[str] = Field(default=None, sa_column=Column(Text))
    outreach_message_score: Optional[float] = None
    ai_input_tokens: Optional[int] = None
    ai_output_tokens: Optional[int] = None
    ai_total_tokens: Optional[int] = None
    status: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    company: Mapped[Optional["Company"]] = Relationship(back_populates="leads")
    message_variants: Mapped[list["MessageVariant"]] = Relationship(
        back_populates="lead"
    )
    outreach_logs: Mapped[list["OutreachLog"]] = Relationship(back_populates="lead")
