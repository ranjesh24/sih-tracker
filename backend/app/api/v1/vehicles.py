"""Vehicle read routes (techspec.md 5.4). Response models only, never tables."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_session
from app.core.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.core.exceptions import NotFoundError
from app.models import Camera, MatchDecision, Sighting
from app.repositories import (
    camera_repo,
    match_decision_repo,
    sighting_repo,
    vehicle_repo,
)
from app.schemas.common import PaginatedResponse
from app.schemas.match_decision import MatchDecisionRead
from app.schemas.vehicle import (
    TrajectoryHop,
    TrajectoryPoint,
    TrajectoryRead,
    VehicleRead,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

_OUTCOME_ACCEPTED = "accepted"


@router.get("", response_model=PaginatedResponse[VehicleRead])
def list_vehicles(
    session: Session = Depends(get_session),
    plate: Optional[str] = None,
    plate_partial: Optional[str] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    camera_id: Optional[str] = None,
    vehicle_class: Optional[str] = None,
    min_sightings: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[VehicleRead]:
    items, total = vehicle_repo.search(
        session,
        plate=plate,
        plate_partial=plate_partial,
        from_at=from_,
        to_at=to,
        camera_id=camera_id,
        vehicle_class=vehicle_class,
        min_sightings=min_sightings,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[VehicleRead](
        items=[VehicleRead.from_model(v) for v in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(vehicle_id: str, session: Session = Depends(get_session)) -> VehicleRead:
    vehicle = vehicle_repo.get_by_id(session, vehicle_id)
    if vehicle is None:
        raise NotFoundError(f"No vehicle with id {vehicle_id}.")
    return VehicleRead.from_model(vehicle)


def _accepted_decision(
    session: Session, sighting_id: str
) -> Optional[MatchDecision]:
    for decision in match_decision_repo.get_by_sighting(session, sighting_id):
        if decision.outcome == _OUTCOME_ACCEPTED:
            return decision
    return None


@router.get("/{vehicle_id}/trajectory", response_model=TrajectoryRead)
def get_trajectory(
    vehicle_id: str, session: Session = Depends(get_session)
) -> TrajectoryRead:
    if vehicle_repo.get_by_id(session, vehicle_id) is None:
        raise NotFoundError(f"No vehicle with id {vehicle_id}.")
    sightings: list[Sighting] = list(sighting_repo.get_by_vehicle(session, vehicle_id))
    cameras: dict[str, Camera] = {c.id: c for c in camera_repo.get_all_cameras(session)}

    points: list[TrajectoryPoint] = []
    polyline: list[list[float]] = []
    for sighting in sightings:
        camera = cameras.get(sighting.camera_id)
        points.append(
            TrajectoryPoint(
                sighting_id=sighting.id,
                camera_id=sighting.camera_id,
                camera_code=camera.code if camera else None,
                lat=camera.latitude if camera else None,
                lng=camera.longitude if camera else None,
                timestamp=sighting.first_frame_at,
            )
        )
        if camera is not None:
            polyline.append([camera.latitude, camera.longitude])

    hops: list[TrajectoryHop] = []
    for prev, curr in zip(sightings[:-1], sightings[1:]):
        decision = _accepted_decision(session, curr.id)
        hops.append(
            TrajectoryHop(
                from_camera_code=(
                    cameras[prev.camera_id].code if prev.camera_id in cameras else None
                ),
                to_camera_code=(
                    cameras[curr.camera_id].code if curr.camera_id in cameras else None
                ),
                decision=MatchDecisionRead.from_model(decision) if decision else None,
            )
        )

    return TrajectoryRead(
        vehicle_id=vehicle_id, points=points, polyline=polyline, hops=hops
    )
