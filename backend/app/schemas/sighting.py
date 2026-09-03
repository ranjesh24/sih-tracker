"""Sighting response schemas (schema.md 3.6). SQLModel rows are never returned
directly (rules.md 5)."""
from typing import Optional

from pydantic import BaseModel

from app.core.constants import API_V1_PREFIX
from app.models import Camera, Sighting
from app.schemas.match_decision import MatchDecisionRead


def crop_url_for(sighting_id: str) -> str:
    """The URL a client fetches the best-shot JPEG from."""
    return f"{API_V1_PREFIX}/sightings/{sighting_id}/crop"


class SightingRead(BaseModel):
    """A sighting as returned to clients."""

    id: str
    vehicle_id: Optional[str]
    camera_id: str
    camera_code: Optional[str]
    first_frame_at: str
    last_frame_at: str
    best_frame_at: str
    received_at: str
    frame_count: int
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    detection_confidence: float
    vehicle_class: str
    plate_text_norm: Optional[str]
    plate_confidence: Optional[float]
    plate_is_valid: bool
    resolution_status: str
    match_method: Optional[str]
    match_score: Optional[float]
    crop_url: str

    @classmethod
    def from_model(
        cls, sighting: Sighting, camera: Optional[Camera] = None
    ) -> "SightingRead":
        return cls(
            id=sighting.id,
            vehicle_id=sighting.vehicle_id,
            camera_id=sighting.camera_id,
            camera_code=camera.code if camera else None,
            first_frame_at=sighting.first_frame_at,
            last_frame_at=sighting.last_frame_at,
            best_frame_at=sighting.best_frame_at,
            received_at=sighting.received_at,
            frame_count=sighting.frame_count,
            bbox_x=sighting.bbox_x,
            bbox_y=sighting.bbox_y,
            bbox_w=sighting.bbox_w,
            bbox_h=sighting.bbox_h,
            detection_confidence=sighting.detection_confidence,
            vehicle_class=sighting.vehicle_class,
            plate_text_norm=sighting.plate_text_norm,
            plate_confidence=sighting.plate_confidence,
            plate_is_valid=sighting.plate_is_valid,
            resolution_status=sighting.resolution_status,
            match_method=sighting.match_method,
            match_score=sighting.match_score,
            crop_url=crop_url_for(sighting.id),
        )


class SightingDetailRead(SightingRead):
    """A sighting plus every decision considered for it (schema.md 3.7)."""

    decisions: list[MatchDecisionRead]
