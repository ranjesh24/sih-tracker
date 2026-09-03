"""Row factories for tests — build valid Camera/Vehicle/Sighting rows cheaply.

Kept in one place so the many NOT NULL columns on ``sightings`` are supplied
consistently and a test can focus on the one or two fields it actually cares
about.
"""
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sqlmodel import Session

from app.models import Camera, CameraEdge, Sighting, Vehicle
from app.services.vector_index import encode_embedding

EMBEDDING_DIM = 512


def iso(dt: datetime) -> str:
    """Format a datetime as ISO-8601 UTC with a trailing Z."""
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def unit_vector(seed: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """A deterministic pseudo-random unit vector for a given seed."""
    rng = np.random.default_rng(seed)
    return np.asarray(rng.standard_normal(dim), dtype=np.float32)


def blended_vector(base_seed: int, cosine: float, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """A unit vector whose cosine to ``unit_vector(base_seed)`` is ~``cosine``.

    Used to construct a visually near-identical candidate (the White Maruti case).
    """
    base = unit_vector(base_seed, dim)
    base = base / np.linalg.norm(base)
    noise = unit_vector(base_seed + 10_000, dim)
    noise = noise - np.dot(noise, base) * base  # orthogonal component
    noise = noise / np.linalg.norm(noise)
    out = cosine * base + float(np.sqrt(max(0.0, 1.0 - cosine * cosine))) * noise
    return np.asarray(out, dtype=np.float32)


def make_camera(session: Session, code: str, *, camera_id: Optional[str] = None) -> Camera:
    camera = Camera(
        code=code,
        name=f"Camera {code}",
        latitude=25.6,
        longitude=85.1,
    )
    if camera_id is not None:
        camera.id = camera_id
    session.add(camera)
    session.flush()
    return camera


def make_edge(
    session: Session,
    from_camera_id: str,
    to_camera_id: str,
    *,
    min_transit_seconds: int,
    max_transit_seconds: int,
    distance_m: float = 1000.0,
    is_bidirectional: bool = True,
) -> CameraEdge:
    edge = CameraEdge(
        from_camera_id=from_camera_id,
        to_camera_id=to_camera_id,
        min_transit_seconds=min_transit_seconds,
        max_transit_seconds=max_transit_seconds,
        distance_m=distance_m,
        is_bidirectional=is_bidirectional,
    )
    session.add(edge)
    session.flush()
    return edge


def make_vehicle(
    session: Session,
    *,
    display_ref: str,
    canonical_plate: Optional[str] = None,
    plate_is_valid: bool = False,
) -> Vehicle:
    vehicle = Vehicle(
        display_ref=display_ref,
        canonical_plate=canonical_plate,
        plate_is_valid=plate_is_valid,
        status="active",
    )
    session.add(vehicle)
    session.flush()
    return vehicle


def make_sighting(
    session: Session,
    *,
    camera_id: str,
    first_frame_at: str,
    vehicle_id: Optional[str] = None,
    embedding_vector: Optional[np.ndarray] = None,
    plate_text_norm: Optional[str] = None,
    plate_is_valid: bool = False,
    resolution_status: str = "pending",
) -> Sighting:
    embedding = encode_embedding(embedding_vector) if embedding_vector is not None else None
    sighting = Sighting(
        camera_id=camera_id,
        vehicle_id=vehicle_id,
        local_track_id=1,
        first_frame_at=first_frame_at,
        last_frame_at=first_frame_at,
        best_frame_at=first_frame_at,
        received_at=first_frame_at,
        frame_count=5,
        bbox_x=0,
        bbox_y=0,
        bbox_w=10,
        bbox_h=10,
        detection_confidence=0.9,
        vehicle_class="car",
        plate_text_norm=plate_text_norm,
        plate_is_valid=plate_is_valid,
        embedding=embedding,
        resolution_status=resolution_status,
    )
    session.add(sighting)
    session.flush()
    return sighting
