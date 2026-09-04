"""Vehicle response schemas (schema.md 3.5)."""
from typing import Optional

from pydantic import BaseModel

from app.models import Vehicle
from app.schemas.match_decision import MatchDecisionRead


class VehicleRead(BaseModel):
    """A vehicle summary."""

    id: str
    display_ref: str
    canonical_plate: Optional[str]
    plate_confidence: Optional[float]
    plate_is_valid: bool
    vehicle_class: Optional[str]
    dominant_color: Optional[str]
    sighting_count: int
    camera_count: int
    first_seen_at: Optional[str]
    last_seen_at: Optional[str]
    status: str
    merged_into_id: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, vehicle: Vehicle) -> "VehicleRead":
        return cls(
            id=vehicle.id,
            display_ref=vehicle.display_ref,
            canonical_plate=vehicle.canonical_plate,
            plate_confidence=vehicle.plate_confidence,
            plate_is_valid=vehicle.plate_is_valid,
            vehicle_class=vehicle.vehicle_class,
            dominant_color=vehicle.dominant_color,
            sighting_count=vehicle.sighting_count,
            camera_count=vehicle.camera_count,
            first_seen_at=vehicle.first_seen_at,
            last_seen_at=vehicle.last_seen_at,
            status=vehicle.status,
            merged_into_id=vehicle.merged_into_id,
            created_at=vehicle.created_at,
            updated_at=vehicle.updated_at,
        )


class TrajectoryPoint(BaseModel):
    """One stop on a reconstructed trajectory."""

    sighting_id: str
    camera_id: str
    camera_code: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    timestamp: str


class TrajectoryHop(BaseModel):
    """A camera-to-camera hop and the decision that bridged it."""

    from_camera_code: Optional[str]
    to_camera_code: Optional[str]
    decision: Optional[MatchDecisionRead]


class TrajectoryRead(BaseModel):
    """A vehicle's ordered path, polyline and per-hop decisions."""

    vehicle_id: str
    display_ref: str
    canonical_plate: Optional[str]
    points: list[TrajectoryPoint]
    polyline: list[list[float]]
    hops: list[TrajectoryHop]
