"""Ingest request/response schemas (techspec.md 5.4 ingest).

The worker references cameras by their human code (schema.md 3.3) and supplies
the 512-D OSNet embedding as a plain float list; the backend normalises the
plate, encodes the embedding to the BLOB layout, and stamps ``received_at``.
"""
from typing import Optional

from pydantic import BaseModel, Field


class IngestSighting(BaseModel):
    """One completed tracklet submitted by a camera worker."""

    camera_code: str
    local_track_id: int
    first_frame_at: str
    last_frame_at: str
    best_frame_at: str
    frame_count: int = Field(gt=0)
    bbox_x: int
    bbox_y: int
    bbox_w: int = Field(gt=0)
    bbox_h: int = Field(gt=0)
    detection_confidence: float = Field(ge=0.0, le=1.0)
    vehicle_class: str
    plate_text_raw: Optional[str] = None
    plate_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    embedding: Optional[list[float]] = None
    plate_bbox: Optional[str] = None
    crop_path: Optional[str] = None
    plate_crop_path: Optional[str] = None
    sharpness_score: Optional[float] = None


class IngestBatch(BaseModel):
    """Up to 50 sightings submitted together (techspec.md 5.4)."""

    sightings: list[IngestSighting] = Field(max_length=50)


class IngestResult(BaseModel):
    """The resolution outcome for one ingested sighting."""

    sighting_id: str
    vehicle_id: Optional[str]
    resolution_status: str
    match_method: Optional[str]
    match_score: Optional[float]
    decision_count: int


class IngestBatchResult(BaseModel):
    """Results for a batch submission."""

    results: list[IngestResult]
    count: int
