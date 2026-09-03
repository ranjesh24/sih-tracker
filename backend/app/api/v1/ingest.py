"""Ingest routes (techspec.md 5.4). Machine-only, X-Ingest-Key.

The route validates the key, serialises resolution behind a single async lock
(FAISS is not safe for concurrent add and search, and the resolver reads the
index it is about to write), then broadcasts the resulting events.
"""
import asyncio
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlmodel import Session

from app.api.deps import (
    get_broadcaster,
    get_graph,
    get_index,
    get_ingest_lock,
    get_session,
)
from app.core.config import get_settings
from app.core.constants import CLOCK_SKEW_WARN_SECONDS
from app.core.exceptions import IngestKeyError
from app.schemas.ingest import (
    IngestBatch,
    IngestBatchResult,
    IngestResult,
    IngestSighting,
)
from app.schemas.sighting import crop_url_for
from app.services import broadcaster as bc
from app.services.broadcaster import Broadcaster
from app.services.camera_graph import CameraGraph
from app.services.ingest_service import IngestOutcome, ingest_one
from app.services.vector_index import VectorIndex

logger = logging.getLogger("marg.ingest")
router = APIRouter(prefix="/ingest", tags=["ingest"])

_GATE_REJECTION_REASONS = {
    "TEMPORAL_TOO_FAST",
    "TEMPORAL_EXPIRED",
    "NO_PATH",
    "SAME_CAMERA_TOO_SOON",
}
_SYSTEM_ERROR_CLOCK_SKEW = "CLOCK_SKEW"


def _check_ingest_key(provided: Optional[str]) -> None:
    """Reject unless the provided key matches, compared in constant time."""
    expected = get_settings().INGEST_API_KEY
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise IngestKeyError("Invalid or missing ingest key.")


def _to_result(outcome: IngestOutcome) -> IngestResult:
    s = outcome.sighting
    return IngestResult(
        sighting_id=s.id,
        vehicle_id=outcome.assigned_vehicle_id,
        resolution_status=s.resolution_status,
        match_method=s.match_method,
        match_score=s.match_score,
        decision_count=len(outcome.decisions),
    )


async def _broadcast_outcome(
    broadcaster: Broadcaster, outcome: IngestOutcome
) -> None:
    s = outcome.sighting
    camera = outcome.camera

    if outcome.skew_seconds > CLOCK_SKEW_WARN_SECONDS:
        logger.warning(
            "Clock skew above threshold",
            extra={"camera_code": camera.code, "skew_seconds": outcome.skew_seconds},
        )
        await broadcaster.broadcast(
            bc.system_error(
                code=_SYSTEM_ERROR_CLOCK_SKEW,
                message=(
                    f"Clock skew {outcome.skew_seconds:.1f}s at camera {camera.code}"
                ),
                camera_id=camera.id,
            )
        )

    await broadcaster.broadcast(
        bc.sighting_created(
            sighting_id=s.id,
            vehicle_id=s.vehicle_id,
            camera_id=s.camera_id,
            camera_code=camera.code,
            lat=camera.latitude,
            lng=camera.longitude,
            timestamp=s.first_frame_at,
            vehicle_class=s.vehicle_class,
            plate=s.plate_text_norm,
            plate_confidence=s.plate_confidence,
            match_method=s.match_method,
            match_score=s.match_score,
            crop_url=crop_url_for(s.id),
        )
    )

    for decision in outcome.decisions:
        if decision.outcome == "ambiguous":
            margin = None
            if decision.fused_score is not None and decision.runner_up_score is not None:
                margin = decision.fused_score - decision.runner_up_score
            await broadcaster.broadcast(
                bc.match_ambiguous(
                    sighting_id=s.id,
                    candidate_count=len(outcome.decisions),
                    top_score=decision.fused_score,
                    runner_up_score=decision.runner_up_score,
                    margin=margin,
                )
            )
        elif decision.rejection_reason in _GATE_REJECTION_REASONS:
            await broadcaster.broadcast(
                bc.match_rejected(
                    sighting_id=s.id,
                    candidate_vehicle_id=decision.candidate_vehicle_id,
                    reason=decision.rejection_reason,
                    visual_score=decision.visual_score,
                    elapsed_seconds=decision.elapsed_seconds,
                    min_transit_seconds=decision.min_transit_seconds,
                )
            )


@router.post("/sightings", response_model=IngestResult)
async def ingest_sighting(
    payload: IngestSighting,
    x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key"),
    session: Session = Depends(get_session),
    graph: CameraGraph = Depends(get_graph),
    index: VectorIndex = Depends(get_index),
    broadcaster: Broadcaster = Depends(get_broadcaster),
    lock: asyncio.Lock = Depends(get_ingest_lock),
) -> IngestResult:
    _check_ingest_key(x_ingest_key)
    async with lock:
        outcome = ingest_one(session, payload, graph, index)
        session.commit()
    await _broadcast_outcome(broadcaster, outcome)
    return _to_result(outcome)


@router.post("/sightings/batch", response_model=IngestBatchResult)
async def ingest_batch(
    payload: IngestBatch,
    x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key"),
    session: Session = Depends(get_session),
    graph: CameraGraph = Depends(get_graph),
    index: VectorIndex = Depends(get_index),
    broadcaster: Broadcaster = Depends(get_broadcaster),
    lock: asyncio.Lock = Depends(get_ingest_lock),
) -> IngestBatchResult:
    _check_ingest_key(x_ingest_key)
    outcomes: list[IngestOutcome] = []
    async with lock:
        for one in payload.sightings:
            outcomes.append(ingest_one(session, one, graph, index))
        session.commit()
    for outcome in outcomes:
        await _broadcast_outcome(broadcaster, outcome)
    return IngestBatchResult(
        results=[_to_result(o) for o in outcomes], count=len(outcomes)
    )
