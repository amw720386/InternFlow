from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.data.models.lead import Lead


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    size_range: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None

    leads: Mapped[list["Lead"]] = Relationship(back_populates="company")
