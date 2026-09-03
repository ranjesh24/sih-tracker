"""Camera and topology database access (rules.md section 2 layering).

All camera and camera-edge queries live here; services build the networkx graph
from what these functions return and never query the tables directly.
"""
from collections.abc import Sequence

from sqlmodel import Session, select

from app.models import Camera, CameraEdge


def get_all_cameras(session: Session) -> Sequence[Camera]:
    """Return every camera, active or soft-deleted."""
    return session.exec(select(Camera)).all()


def get_active_cameras(session: Session) -> Sequence[Camera]:
    """Return only cameras with ``is_active = 1``."""
    return session.exec(select(Camera).where(Camera.is_active == True)).all()  # noqa: E712


def get_by_id(session: Session, camera_id: str) -> Camera | None:
    """Return the camera with the given id, or None."""
    return session.get(Camera, camera_id)


def get_by_code(session: Session, code: str) -> Camera | None:
    """Return the camera with the given human code, or None."""
    return session.exec(select(Camera).where(Camera.code == code)).first()


def get_all_edges(session: Session) -> Sequence[CameraEdge]:
    """Return every camera edge (the topology graph)."""
    return session.exec(select(CameraEdge)).all()
