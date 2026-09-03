"""Ingest orchestration (techspec.md 5.4; appflow.md 6.3/6.4).

Turns an :class:`IngestSighting` payload into a persisted, resolved sighting:
resolve the camera by code, normalise the plate, encode the embedding, stamp the
server clock, run the resolver against the long-lived graph and index, then add
the new embedding to the index. Pure synchronous DB work — the async lock and
broadcasting live in the route.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import CameraNotFoundError, MargError
from app.models import Camera, MatchDecision, Sighting
from app.repositories import camera_repo
from app.schemas.ingest import IngestSighting
from app.services import plate_matcher
from app.services.camera_graph import CameraGraph
from app.services.identity_resolver import resolve as resolve_sighting
from app.services.vector_index import VectorIndex, decode_embedding, encode_embedding


@dataclass
class IngestOutcome:
    """Everything the route needs to build a response and broadcast events."""

    sighting: Sighting
    camera: Camera
    assigned_vehicle_id: Optional[str]
    decisions: list[MatchDecision]
    skew_seconds: float


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ingest_one(
    session,
    payload: IngestSighting,
    graph: CameraGraph,
    index: VectorIndex,
    *,
    gate_enabled: bool = True,
) -> IngestOutcome:
    """Persist and resolve one sighting. Raises CameraNotFoundError (404) if the
    camera code is unregistered (appflow.md 6.4)."""
    settings = get_settings()
    camera = camera_repo.get_by_code(session, payload.camera_code)
    if camera is None:
        raise CameraNotFoundError(payload.camera_code)

    received_dt = datetime.now(timezone.utc)
    received_at = _iso(received_dt)
    skew_seconds = abs(
        (received_dt - _parse_iso(payload.first_frame_at)).total_seconds()
    )

    plate_norm: Optional[str] = None
    plate_is_valid = False
    if payload.plate_text_raw:
        plate_norm = plate_matcher.normalise(payload.plate_text_raw)
        plate_is_valid = plate_matcher.is_structurally_valid(plate_norm)

    embedding_blob: Optional[bytes] = None
    if payload.embedding is not None:
        if len(payload.embedding) != settings.EMBEDDING_DIM:
            raise MargError(
                f"Embedding has {len(payload.embedding)} dims, "
                f"expected {settings.EMBEDDING_DIM}.",
                details={"expected_dim": settings.EMBEDDING_DIM},
            )
        embedding_blob = encode_embedding(
            np.asarray(payload.embedding, dtype=np.float32)
        )

    sighting = Sighting(
        camera_id=camera.id,
        local_track_id=payload.local_track_id,
        first_frame_at=payload.first_frame_at,
        last_frame_at=payload.last_frame_at,
        best_frame_at=payload.best_frame_at,
        received_at=received_at,
        frame_count=payload.frame_count,
        bbox_x=payload.bbox_x,
        bbox_y=payload.bbox_y,
        bbox_w=payload.bbox_w,
        bbox_h=payload.bbox_h,
        detection_confidence=payload.detection_confidence,
        vehicle_class=payload.vehicle_class,
        plate_text_raw=payload.plate_text_raw,
        plate_text_norm=plate_norm,
        plate_confidence=payload.plate_confidence,
        plate_is_valid=plate_is_valid,
        plate_bbox=payload.plate_bbox,
        embedding=embedding_blob,
        embedding_dim=settings.EMBEDDING_DIM,
        crop_path=payload.crop_path,
        plate_crop_path=payload.plate_crop_path,
        sharpness_score=payload.sharpness_score,
    )
    session.add(sighting)
    session.flush()

    assigned, decisions = resolve_sighting(
        session, sighting, graph=graph, index=index, gate_enabled=gate_enabled
    )

    # Add to the long-lived index AFTER resolution, so a sighting is never a
    # candidate for itself, and mark it present in the index.
    if embedding_blob is not None:
        index.add(
            sighting.id, decode_embedding(embedding_blob, settings.EMBEDDING_DIM)
        )
        sighting.in_vector_index = True
        session.add(sighting)
        session.flush()

    return IngestOutcome(sighting, camera, assigned, decisions, skew_seconds)
