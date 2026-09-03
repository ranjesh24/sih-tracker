"""``users`` table (schema.md section 3.1)."""
from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin','operator','viewer')", name="ck_users_role"
        ),
        CheckConstraint("is_active IN (0,1)", name="ck_users_is_active"),
        Index("idx_users_email", "email", unique=True),
        Index("idx_users_role", "role"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    email: str = Field(nullable=False)
    full_name: str = Field(nullable=False)
    password_hash: str = Field(nullable=False)
    role: str = Field(default="viewer", nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    last_login_at: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=utcnow, nullable=False)
    updated_at: str = Field(default_factory=utcnow, nullable=False)
