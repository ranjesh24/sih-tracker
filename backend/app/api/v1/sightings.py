"""Sighting read routes (techspec.md 5.4). Response models only, never tables."""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.core.exceptions import NotFoundError
from app.models import Camera
from app.repositories import camera_repo, match_decision_repo, sighting_repo
from app.schemas.common import PaginatedResponse
from app.schemas.match_decision import MatchDecisionRead
from app.schemas.sighting import SightingDetailRead, SightingRead

router = APIRouter(prefix="/sightings", tags=["sightings"])

_JPEG_MEDIA_TYPE = "image/jpeg"


def _camera_map(session: Session) -> dict[str, Camera]:
    return {camera.id: camera for camera in camera_repo.get_all_cameras(session)}


@router.get("", response_model=PaginatedResponse[SightingRead])
def list_sightings(
    session: Session = Depends(get_session),
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    camera_id: Optional[str] = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[SightingRead]:
    items, total = sighting_repo.list_sightings(
        session, from_at=from_, to_at=to, camera_id=camera_id, limit=limit, offset=offset
    )
    cameras = _camera_map(session)
    return PaginatedResponse[SightingRead](
        items=[SightingRead.from_model(s, cameras.get(s.camera_id)) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{sighting_id}", response_model=SightingDetailRead)
def get_sighting(
    sighting_id: str, session: Session = Depends(get_session)
) -> SightingDetailRead:
    sighting = sighting_repo.get_by_id(session, sighting_id)
    if sighting is None:
        raise NotFoundError(f"No sighting with id {sighting_id}.")
    camera = camera_repo.get_by_id(session, sighting.camera_id)
    decisions = match_decision_repo.get_by_sighting(session, sighting_id)
    base = SightingRead.from_model(sighting, camera).model_dump()
    return SightingDetailRead(
        **base, decisions=[MatchDecisionRead.from_model(d) for d in decisions]
    )


@router.get("/{sighting_id}/candidates", response_model=list[MatchDecisionRead])
def get_candidates(
    sighting_id: str, session: Session = Depends(get_session)
) -> list[MatchDecisionRead]:
    """Every candidate evaluated, with scores and gate results — the evidence
    panel's "also considered" block."""
    if sighting_repo.get_by_id(session, sighting_id) is None:
        raise NotFoundError(f"No sighting with id {sighting_id}.")
    decisions = match_decision_repo.get_by_sighting(session, sighting_id)
    return [MatchDecisionRead.from_model(d) for d in decisions]


@router.get("/{sighting_id}/crop")
def get_crop(sighting_id: str, session: Session = Depends(get_session)) -> FileResponse:
    """Serve the best-shot JPEG from CROP_STORAGE_PATH."""
    sighting = sighting_repo.get_by_id(session, sighting_id)
    if sighting is None or not sighting.crop_path:
        raise NotFoundError(f"No crop for sighting {sighting_id}.")
    path = Path(sighting.crop_path)
    if not path.is_absolute():
        path = Path(get_settings().CROP_STORAGE_PATH) / sighting.crop_path
    if not path.is_file():
        raise NotFoundError(f"Crop file missing for sighting {sighting_id}.")
    return FileResponse(path, media_type=_JPEG_MEDIA_TYPE)
