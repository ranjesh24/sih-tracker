"""Camera read routes — the frontend needs the camera list for the map and filters."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_session
from app.core.constants import API_V1_PREFIX
from app.models import Camera
from app.repositories import camera_repo, video_repo


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
    # Populated only by the has_video filter. The frontend plays this directly
    # instead of inferring whether footage exists.
    video_url: Optional[str] = None


router = APIRouter(prefix="/cameras", tags=["cameras"])


def _to_read(camera: Camera, video_url: Optional[str] = None) -> CameraRead:
    """Shape one camera for the wire."""
    return CameraRead(
        id=camera.id,
        code=camera.code,
        name=camera.name,
        location_label=camera.location_label,
        latitude=camera.latitude,
        longitude=camera.longitude,
        heading_deg=camera.heading_deg,
        stream_uri=camera.stream_uri,
        is_active=camera.is_active,
        last_seen_at=camera.last_seen_at,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        video_url=video_url,
    )


@router.get("", response_model=list[CameraRead])
def list_cameras(
    has_video: bool = False,
    session: Session = Depends(get_session),
) -> list[CameraRead]:
    """List active cameras.

    Args:
        has_video: When true, return only cameras that have an uploaded video in
            the current batch, each with its playback URL. This is what the live
            wall calls, so it renders exactly one tile per uploaded video.

            Deliberately keyed on the ``videos`` table rather than on sightings:
            seeded or previously ingested sightings would make every camera look
            like it has footage, which is the bug this replaced.
    """
    if not has_video:
        return [_to_read(camera) for camera in camera_repo.get_active_cameras(session)]

    return [
        _to_read(camera, video_url=f"{API_V1_PREFIX}/upload/serve/{video.filename}")
        for camera, video in video_repo.get_cameras_with_video(session)
    ]
