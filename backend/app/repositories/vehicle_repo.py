"""Vehicle database access (rules.md section 2 layering)."""
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Sighting, Vehicle

ACTIVE_STATUS: str = "active"


def get_by_id(session: Session, vehicle_id: str) -> Optional[Vehicle]:
    """Return the vehicle with the given id, or None."""
    return session.get(Vehicle, vehicle_id)


def search(
    session: Session,
    *,
    plate: Optional[str] = None,
    plate_partial: Optional[str] = None,
    from_at: Optional[str] = None,
    to_at: Optional[str] = None,
    camera_id: Optional[str] = None,
    vehicle_class: Optional[str] = None,
    min_sightings: Optional[int] = None,
    limit: int,
    offset: int,
) -> tuple[list[Vehicle], int]:
    """Filtered, paginated vehicle search (techspec.md 5.4 GET /vehicles).

    Returns the page of vehicles and the total count matching the filters.
    Time-window and camera filters are expressed as "has a sighting matching".
    """
    filters = [Vehicle.status == ACTIVE_STATUS]
    if plate is not None:
        filters.append(Vehicle.canonical_plate == plate)
    if plate_partial is not None:
        filters.append(Vehicle.canonical_plate.like(f"%{plate_partial}%"))  # type: ignore[union-attr]
    if vehicle_class is not None:
        filters.append(Vehicle.vehicle_class == vehicle_class)
    if min_sightings is not None:
        filters.append(Vehicle.sighting_count >= min_sightings)

    if from_at is not None or to_at is not None or camera_id is not None:
        sighting_filters = []
        if from_at is not None:
            sighting_filters.append(Sighting.first_frame_at >= from_at)
        if to_at is not None:
            sighting_filters.append(Sighting.first_frame_at <= to_at)
        if camera_id is not None:
            sighting_filters.append(Sighting.camera_id == camera_id)
        subquery = select(Sighting.vehicle_id).where(*sighting_filters)
        filters.append(Vehicle.id.in_(subquery))  # type: ignore[union-attr]

    total = session.exec(
        select(func.count()).select_from(Vehicle).where(*filters)
    ).one()
    items = session.exec(
        select(Vehicle)
        .where(*filters)
        .order_by(Vehicle.last_seen_at.desc())  # type: ignore[union-attr]
        .offset(offset)
        .limit(limit)
    ).all()
    return list(items), int(total)


def get_by_plate(session: Session, plate_norm: str) -> Sequence[Vehicle]:
    """Return active vehicles whose canonical plate matches exactly."""
    return session.exec(
        select(Vehicle).where(
            Vehicle.canonical_plate == plate_norm,
            Vehicle.status == ACTIVE_STATUS,
        )
    ).all()


def search_partial_plate(session: Session, partial: str) -> Sequence[Vehicle]:
    """Return active vehicles whose canonical plate contains ``partial``."""
    pattern = f"%{partial}%"
    return session.exec(
        select(Vehicle).where(
            Vehicle.canonical_plate.is_not(None),  # type: ignore[union-attr]
            Vehicle.canonical_plate.like(pattern),  # type: ignore[union-attr]
            Vehicle.status == ACTIVE_STATUS,
        )
    ).all()


def get_by_ids(session: Session, ids: Sequence[str]) -> list[Vehicle]:
    """Bulk-load vehicles by id (for scoring the feasible candidate set)."""
    if not ids:
        return []
    return list(
        session.exec(select(Vehicle).where(Vehicle.id.in_(ids))).all()  # type: ignore[union-attr]
    )


def create(session: Session, vehicle: Vehicle) -> Vehicle:
    """Persist a newly created vehicle (the NEW identity path)."""
    session.add(vehicle)
    session.flush()
    return vehicle


def update_counters(
    session: Session,
    vehicle_id: str,
    *,
    sighting_count: int,
    camera_count: int,
    last_seen_at: str,
    first_seen_at: Optional[str] = None,
) -> Optional[Vehicle]:
    """Update a vehicle's denormalised counters and seen timestamps.

    Returns the updated vehicle, or None if it does not exist.
    """
    vehicle = session.get(Vehicle, vehicle_id)
    if vehicle is None:
        return None
    vehicle.sighting_count = sighting_count
    vehicle.camera_count = camera_count
    vehicle.last_seen_at = last_seen_at
    if first_seen_at is not None and vehicle.first_seen_at is None:
        vehicle.first_seen_at = first_seen_at
    session.add(vehicle)
    session.flush()
    return vehicle
