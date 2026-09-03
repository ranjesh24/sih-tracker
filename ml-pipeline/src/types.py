"""Frozen data structures passed between pipeline stages.

Naming note. `Detection`, `FrameSample` and `Tracklet` are pipeline-internal and
follow the units-in-names convention from rules.md section 3. `Sighting` does
not: its field names mirror the `sightings` columns in schema.md section 3.6
character for character, because it is serialised straight onto the ingest wire
and a close-enough name there is a defect (rules.md R9.6). That is a deliberate
, localised exception to the units convention, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

# Mirrors the CHECK constraints on the sightings table (schema.md section 3.6).
VehicleClass = Literal["car", "motorcycle", "bus", "truck", "auto", "other"]
ResolutionStatus = Literal["pending", "matched", "ambiguous", "new_vehicle"]
MatchMethod = Literal["PLATE_EXACT", "PLATE_FUZZY", "VISUAL", "MANUAL", "NEW"]


@dataclass(frozen=True, slots=True)
class Detection:
    """One vehicle detected in one frame.

    `class_name` carries the COCO label through from the detector unchanged. The
    backend gates matches on vehicle class, so this must survive into the
    Sighting rather than being collapsed to an id.
    """

    bbox_x_px: int
    bbox_y_px: int
    bbox_w_px: int
    bbox_h_px: int
    det_conf: float
    class_id: int
    class_name: str

    @property
    def area_px(self) -> int:
        """Bounding-box area in pixels."""
        return self.bbox_w_px * self.bbox_h_px


# eq=False on the two crop-carrying types: the default __eq__ would compare
# ndarray fields elementwise and raise "truth value of an array is ambiguous"
# the first time anything compares two samples. Identity equality is what these
# actually need.
@dataclass(frozen=True, slots=True, eq=False)
class FrameSample:
    """A single buffered crop of one tracked vehicle, from one frame.

    Tier 1 appends these and does nothing else with them. `area_px`, `det_conf`
    and `blur_var` are precomputed here so best-shot scoring never has to touch
    the pixel data of every buffered sample.
    """

    crop_bgr: np.ndarray
    frame_at: str
    frame_index: int
    detection: Detection
    area_px: int
    det_conf: float
    blur_var: float


@dataclass(frozen=True, slots=True, eq=False)
class Tracklet:
    """A finalised track: every buffered sample for one vehicle at one camera.

    Emitted only once the track id has been absent for TRACK_LOST_FRAMES and the
    sample count has cleared TRACKLET_MIN_FRAMES. Tier-2 work (best-shot, OCR,
    embedding) begins here and never before.
    """

    track_id: int
    camera_id: str
    samples: tuple[FrameSample, ...]
    first_frame_at: str
    last_frame_at: str

    @property
    def frame_count(self) -> int:
        """Number of buffered samples in this tracklet."""
        return len(self.samples)


@dataclass(frozen=True, slots=True, eq=False)
class Sighting:
    """One completed tracklet, shaped for POST /api/v1/ingest/sightings.

    Field names and order follow the `sightings` table in schema.md section 3.6
    exactly. Fields the backend owns are optional here and left unset by the
    worker: `vehicle_id`, `received_at`, `in_vector_index`, `resolution_status`,
    `match_method` and `match_score` are all assigned during identity
    resolution, and `received_at` specifically must come from the server clock —
    it exists to detect worker clock drift, so a worker-supplied value would
    defeat its only purpose.
    """

    # Identity and provenance
    id: str
    camera_id: str
    local_track_id: int

    # Time. first_frame_at is the authoritative time for spatio-temporal gating.
    first_frame_at: str
    last_frame_at: str
    best_frame_at: str
    frame_count: int

    # Geometry of the best shot
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    detection_confidence: float
    vehicle_class: VehicleClass

    created_at: str

    # Backend-assigned; the worker leaves these alone.
    vehicle_id: str | None = None
    received_at: str | None = None

    # Plate tier
    plate_text_raw: str | None = None
    plate_text_norm: str | None = None
    plate_confidence: float | None = None
    plate_is_valid: bool = False
    plate_bbox: str | None = None

    # Visual tier. 512 float32, L2-normalised exactly once, at encode time.
    embedding: np.ndarray | None = None
    embedding_dim: int = 512
    in_vector_index: bool = False

    # Evidence
    crop_path: str | None = None
    plate_crop_path: str | None = None
    sharpness_score: float | None = None

    # Resolution outcome, filled by the backend.
    resolution_status: ResolutionStatus = "pending"
    match_method: MatchMethod | None = None
    match_score: float | None = None
