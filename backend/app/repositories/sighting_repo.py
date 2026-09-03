"""Sighting database access (rules.md section 2 layering)."""
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Sighting


def get_by_id(session: Session, sighting_id: str) -> Optional[Sighting]:
    """Return the sighting with the given id, or None."""
    return session.get(Sighting, sighting_id)


def list_sightings(
    session: Session,
    *,
    from_at: Optional[str] = None,
    to_at: Optional[str] = None,
    camera_id: Optional[str] = None,
    limit: int,
    offset: int,
) -> tuple[list[Sighting], int]:
    """Filtered, paginated sighting list (techspec.md 5.4 GET /sightings)."""
    filters = []
    if from_at is not None:
        filters.append(Sighting.first_frame_at >= from_at)
    if to_at is not None:
        filters.append(Sighting.first_frame_at <= to_at)
    if camera_id is not None:
        filters.append(Sighting.camera_id == camera_id)
    total = session.exec(
        select(func.count()).select_from(Sighting).where(*filters)
    ).one()
    items = session.exec(
        select(Sighting)
        .where(*filters)
        .order_by(Sighting.first_frame_at.desc())  # type: ignore[union-attr]
        .offset(offset)
        .limit(limit)
    ).all()
    return list(items), int(total)


def get_by_vehicle(session: Session, vehicle_id: str) -> Sequence[Sighting]:
    """Return a vehicle's sightings, oldest first (trajectory order)."""
    return session.exec(
        select(Sighting)
        .where(Sighting.vehicle_id == vehicle_id)
        .order_by(Sighting.first_frame_at)
    ).all()


def get_since(
    session: Session, since_at: Optional[str] = None
) -> Sequence[Sighting]:
    """Return sightings with ``first_frame_at >= since_at`` (all if None).

    Used by the vector index rebuild; ISO-8601 UTC strings sort chronologically
    so a string comparison is a time comparison (schema.md section 2).
    """
    statement = select(Sighting)
    if since_at is not None:
        statement = statement.where(Sighting.first_frame_at >= since_at)
    return session.exec(statement.order_by(Sighting.first_frame_at)).all()


def get_latest_per_vehicle(
    session: Session, since_at: Optional[str] = None
) -> list[Sighting]:
    """Return the most recent assigned sighting per vehicle within the window.

    Only sightings that carry an embedding and belong to a vehicle are returned,
    because these are the representatives the resolver scores candidates against.
    """
    statement = select(Sighting).where(
        Sighting.vehicle_id.is_not(None),  # type: ignore[union-attr]
        Sighting.embedding.is_not(None),  # type: ignore[union-attr]
    )
    if since_at is not None:
        statement = statement.where(Sighting.first_frame_at >= since_at)
    # Newest first, then keep the first row seen per vehicle.
    rows = session.exec(
        statement.order_by(Sighting.first_frame_at.desc())  # type: ignore[union-attr]
    ).all()
    latest: dict[str, Sighting] = {}
    for row in rows:
        assert row.vehicle_id is not None  # guaranteed by the WHERE clause
        if row.vehicle_id not in latest:
            latest[row.vehicle_id] = row
    return list(latest.values())
