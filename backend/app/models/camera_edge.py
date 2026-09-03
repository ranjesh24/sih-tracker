"""``camera_edges`` table (schema.md section 3.4) — the topology graph.

This is the differentiator table. ``min_transit_seconds`` / ``max_transit_seconds``
bound the physically plausible travel time along the segment; the gate rejects
any candidate whose elapsed time falls outside the summed window along the
shortest path. ``is_bidirectional`` at 1 means the edge is traversable in both
directions (``camera_graph`` adds the reverse edge).
"""
from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class CameraEdge(SQLModel, table=True):
    __tablename__ = "camera_edges"
    __table_args__ = (
        CheckConstraint("distance_m > 0", name="ck_edges_distance_m"),
        CheckConstraint("min_transit_seconds >= 0", name="ck_edges_min_transit"),
        CheckConstraint("max_transit_seconds > 0", name="ck_edges_max_transit"),
        CheckConstraint("is_bidirectional IN (0,1)", name="ck_edges_bidirectional"),
        CheckConstraint("is_estimated IN (0,1)", name="ck_edges_estimated"),
        CheckConstraint(
            "from_camera_id <> to_camera_id", name="ck_edges_distinct_cameras"
        ),
        CheckConstraint(
            "max_transit_seconds > min_transit_seconds", name="ck_edges_window_order"
        ),
        Index("idx_edges_pair", "from_camera_id", "to_camera_id", unique=True),
        Index("idx_edges_from", "from_camera_id"),
        Index("idx_edges_to", "to_camera_id"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    from_camera_id: str = Field(
        sa_column=Column(
            String, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        )
    )
    to_camera_id: str = Field(
        sa_column=Column(
            String, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        )
    )
    distance_m: float = Field(nullable=False)
    min_transit_seconds: int = Field(nullable=False)
    max_transit_seconds: int = Field(nullable=False)
    is_bidirectional: bool = Field(default=True, nullable=False)
    road_name: Optional[str] = Field(default=None)
    is_estimated: bool = Field(default=True, nullable=False)
    created_at: str = Field(default_factory=utcnow, nullable=False)
    updated_at: str = Field(default_factory=utcnow, nullable=False)
