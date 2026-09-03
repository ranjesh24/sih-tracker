"""``vehicles`` table (schema.md section 3.5).

A vehicle is a hypothesis about identity — the set of sightings the system
currently believes belong to one physical object — not a registered vehicle.
"""
from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, text
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class Vehicle(SQLModel, table=True):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            "plate_confidence IS NULL OR plate_confidence BETWEEN 0 AND 1",
            name="ck_vehicles_plate_confidence",
        ),
        CheckConstraint("plate_is_valid IN (0,1)", name="ck_vehicles_plate_is_valid"),
        CheckConstraint(
            "vehicle_class IS NULL OR vehicle_class IN "
            "('car','motorcycle','bus','truck','auto','other')",
            name="ck_vehicles_class",
        ),
        CheckConstraint("sighting_count >= 0", name="ck_vehicles_sighting_count"),
        CheckConstraint("camera_count >= 0", name="ck_vehicles_camera_count"),
        CheckConstraint(
            "status IN ('active','merged','archived')", name="ck_vehicles_status"
        ),
        Index("idx_vehicles_ref", "display_ref", unique=True),
        Index("idx_vehicles_plate", "canonical_plate"),
        Index("idx_vehicles_last_seen", text("last_seen_at DESC")),
        Index("idx_vehicles_status", "status"),
        Index("idx_vehicles_class_seen", "vehicle_class", text("last_seen_at DESC")),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    display_ref: str = Field(nullable=False)
    canonical_plate: Optional[str] = Field(default=None)
    plate_confidence: Optional[float] = Field(default=None)
    plate_is_valid: bool = Field(default=False, nullable=False)
    vehicle_class: Optional[str] = Field(default=None)
    dominant_color: Optional[str] = Field(default=None)
    sighting_count: int = Field(default=0, nullable=False)
    camera_count: int = Field(default=0, nullable=False)
    first_seen_at: Optional[str] = Field(default=None)
    last_seen_at: Optional[str] = Field(default=None)
    status: str = Field(default="active", nullable=False)
    merged_into_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
        ),
    )
    created_at: str = Field(default_factory=utcnow, nullable=False)
    updated_at: str = Field(default_factory=utcnow, nullable=False)
