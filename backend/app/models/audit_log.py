"""``audit_logs`` table (schema.md section 3.8).

``user_id`` is nullable so system-generated entries have somewhere to live, and
``ON DELETE RESTRICT`` prevents deleting a user whose actions are on record — an
audit log with the actor removed is not an audit log.
"""
from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, text
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ("
            "'LOGIN_SUCCESS','LOGIN_FAILURE','LOGOUT',"
            "'SEARCH_PLATE','SEARCH_PARTIAL','SEARCH_TIME',"
            "'VIEW_TRAJECTORY','VIEW_CROP','EXPORT',"
            "'CONFIRM_MATCH','REJECT_MATCH','MERGE_VEHICLES',"
            "'SPLIT_VEHICLE','CREATE_CAMERA','UPDATE_CAMERA',"
            "'DELETE_CAMERA','CREATE_EDGE','UPDATE_EDGE',"
            "'DELETE_EDGE','RESET_DEMO','SECURITY')",
            name="ck_audit_action",
        ),
        Index("idx_audit_user", "user_id", text("created_at DESC")),
        Index("idx_audit_action", "action", text("created_at DESC")),
        Index("idx_audit_time", text("created_at DESC")),
        Index("idx_audit_entity", "entity_type", "entity_id"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
        ),
    )
    action: str = Field(nullable=False)
    entity_type: Optional[str] = Field(default=None)
    entity_id: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    user_agent: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=utcnow, nullable=False)
