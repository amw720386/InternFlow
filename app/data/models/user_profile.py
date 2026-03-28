from typing import Any, Optional

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profile"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    school: Optional[str] = None
    program: Optional[str] = None
    grad_year: Optional[int] = None
    target_roles: Optional[list[Any]] = Field(default=None, sa_column=Column(JSON))
    skills: Optional[list[Any]] = Field(default=None, sa_column=Column(JSON))
    projects: Optional[list[Any]] = Field(default=None, sa_column=Column(JSON))
    resume_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    preferences: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
