"""``sightings`` table (schema.md section 3.6) — one row per completed tracklet.

Four time columns exist deliberately (schema.md section 3.6): ``first_frame_at``
is the authoritative time used for gating; ``received_at`` is the server clock,
kept solely for clock-skew detection. ``vehicle_id`` is nullable during
resolution (SET NULL on delete); ``camera_id`` is RESTRICT so deleting a camera
cannot silently destroy trajectory history.
"""
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    text,
)
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class Sighting(SQLModel, table=True):
    __tablename__ = "sightings"
    __table_args__ = (
        CheckConstraint("frame_count > 0", name="ck_sightings_frame_count"),
        CheckConstraint("bbox_w > 0", name="ck_sightings_bbox_w"),
        CheckConstraint("bbox_h > 0", name="ck_sightings_bbox_h"),
        CheckConstraint(
            "detection_confidence BETWEEN 0 AND 1",
            name="ck_sightings_detection_confidence",
        ),
        CheckConstraint(
            "vehicle_class IN ('car','motorcycle','bus','truck','auto','other')",
            name="ck_sightings_vehicle_class",
        ),
        CheckConstraint(
            "plate_confidence IS NULL OR plate_confidence BETWEEN 0 AND 1",
            name="ck_sightings_plate_confidence",
        ),
        CheckConstraint("plate_is_valid IN (0,1)", name="ck_sightings_plate_is_valid"),
        CheckConstraint("in_vector_index IN (0,1)", name="ck_sightings_in_index"),
        CheckConstraint(
            "resolution_status IN ('pending','matched','ambiguous','new_vehicle')",
            name="ck_sightings_resolution_status",
        ),
        CheckConstraint(
            "match_method IS NULL OR match_method IN "
            "('PLATE_EXACT','PLATE_FUZZY','VISUAL','MANUAL','NEW')",
            name="ck_sightings_match_method",
        ),
        CheckConstraint(
            "match_score IS NULL OR match_score BETWEEN 0 AND 1",
            name="ck_sightings_match_score",
        ),
        CheckConstraint(
            "last_frame_at >= first_frame_at", name="ck_sightings_frame_order"
        ),
        Index("idx_sightings_vehicle", "vehicle_id", "first_frame_at"),
        Index("idx_sightings_camera_time", "camera_id", text("first_frame_at DESC")),
        Index(
            "idx_sightings_plate",
            "plate_text_norm",
            sqlite_where=text("plate_text_norm IS NOT NULL"),
        ),
        Index("idx_sightings_time", text("first_frame_at DESC")),
        Index(
            "idx_sightings_status",
            "resolution_status",
            sqlite_where=text("resolution_status IN ('pending','ambiguous')"),
        ),
        Index(
            "idx_sightings_index_flag",
            "in_vector_index",
            sqlite_where=text("in_vector_index = 0"),
        ),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    vehicle_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
        ),
    )
    camera_id: str = Field(
        sa_column=Column(
            String, ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False
        )
    )
    local_track_id: int = Field(nullable=False)

    first_frame_at: str = Field(nullable=False)
    last_frame_at: str = Field(nullable=False)
    best_frame_at: str = Field(nullable=False)
    received_at: str = Field(nullable=False)
    frame_count: int = Field(nullable=False)

    bbox_x: int = Field(nullable=False)
    bbox_y: int = Field(nullable=False)
    bbox_w: int = Field(nullable=False)
    bbox_h: int = Field(nullable=False)
    detection_confidence: float = Field(nullable=False)
    vehicle_class: str = Field(nullable=False)

    plate_text_raw: Optional[str] = Field(default=None)
    plate_text_norm: Optional[str] = Field(default=None)
    plate_confidence: Optional[float] = Field(default=None)
    plate_is_valid: bool = Field(default=False, nullable=False)
    plate_bbox: Optional[str] = Field(default=None)

    embedding: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    embedding_dim: int = Field(default=512, nullable=False)
    in_vector_index: bool = Field(default=False, nullable=False)

    crop_path: Optional[str] = Field(default=None)
    plate_crop_path: Optional[str] = Field(default=None)
    sharpness_score: Optional[float] = Field(default=None)

    resolution_status: str = Field(default="pending", nullable=False)
    match_method: Optional[str] = Field(default=None)
    match_score: Optional[float] = Field(default=None)

    created_at: str = Field(default_factory=utcnow, nullable=False)
