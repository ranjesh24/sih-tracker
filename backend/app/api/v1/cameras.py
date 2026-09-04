"""Camera read routes — the frontend needs the camera list for the map and filters."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_session
from app.repositories import camera_repo


class CameraRead(BaseModel):
    id: str
    code: str
    name: str
    location_label: Optional[str]
    latitude: float
    longitude: float
    heading_deg: Optional[float]
    stream_uri: Optional[str]
    is_active: bool
    last_seen_at: Optional[str]
    created_at: str
    updated_at: str


router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
def list_cameras(session: Session = Depends(get_session)) -> list[CameraRead]:
    cameras = camera_repo.get_active_cameras(session)
    return [
        CameraRead(
            id=c.id,
            code=c.code,
            name=c.name,
            location_label=c.location_label,
            latitude=c.latitude,
            longitude=c.longitude,
            heading_deg=c.heading_deg,
            stream_uri=c.stream_uri,
            is_active=c.is_active,
            last_seen_at=c.last_seen_at,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in cameras
    ]
