"""``cameras`` table (schema.md section 3.3)."""
from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class Camera(SQLModel, table=True):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_cameras_latitude"),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_cameras_longitude"
        ),
        CheckConstraint(
            "heading_deg IS NULL OR heading_deg BETWEEN 0 AND 360",
            name="ck_cameras_heading_deg",
        ),
        CheckConstraint("is_active IN (0,1)", name="ck_cameras_is_active"),
        Index("idx_cameras_code", "code", unique=True),
        Index("idx_cameras_active", "is_active"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    code: str = Field(nullable=False, max_length=32)
    name: str = Field(nullable=False)
    location_label: Optional[str] = Field(default=None)
    latitude: float = Field(nullable=False)
    longitude: float = Field(nullable=False)
    heading_deg: Optional[float] = Field(default=None)
    stream_uri: Optional[str] = Field(default=None)
    resolution_w: Optional[int] = Field(default=None)
    resolution_h: Optional[int] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    last_seen_at: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=utcnow, nullable=False)
    updated_at: str = Field(default_factory=utcnow, nullable=False)
