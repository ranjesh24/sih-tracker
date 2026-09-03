"""``refresh_tokens`` table (schema.md section 3.2)."""
from typing import Optional

from sqlalchemy import Column, ForeignKey, Index, String
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_hash", "token_hash", unique=True),
        Index("idx_refresh_user", "user_id", "revoked_at"),
        Index("idx_refresh_expires", "expires_at"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(
        sa_column=Column(
            String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        )
    )
    token_hash: str = Field(nullable=False)
    issued_at: str = Field(nullable=False)
    expires_at: str = Field(nullable=False)
    revoked_at: Optional[str] = Field(default=None)
    replaced_by: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    user_agent: Optional[str] = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
