"""Uploaded-video database access.

Answers the one question the live wall needs: which cameras have an uploaded
video in the current batch, and where is that file.
"""
from collections.abc import Sequence
from typing import Optional

from sqlmodel import Session, col, select

from app.models import Camera, Video


def create_video(
    session: Session,
    camera_id: str,
    filename: str,
    batch_id: str,
    job_id: Optional[str] = None,
) -> Video:
    """Record that a video was uploaded for a camera."""
    video = Video(
        camera_id=camera_id,
        filename=filename,
        batch_id=batch_id,
        job_id=job_id,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


def get_current_batch_id(session: Session) -> Optional[str]:
    """Return the batch id of the most recent upload, or None if there are none.

    "Current batch" is the newest one: a fresh round of uploads replaces the
    previous wall rather than accumulating with it.
    """
    newest = session.exec(
        select(Video).order_by(col(Video.uploaded_at).desc(), col(Video.id).desc())
    ).first()
    return newest.batch_id if newest else None


def get_videos_in_current_batch(session: Session) -> Sequence[Video]:
    """Return every video belonging to the current batch."""
    batch_id = get_current_batch_id(session)
    if batch_id is None:
        return []
    return session.exec(select(Video).where(Video.batch_id == batch_id)).all()


def get_cameras_with_video(session: Session) -> list[tuple[Camera, Video]]:
    """Return (camera, video) for every camera with a video in the current batch.

    A camera with seeded sightings but no uploaded video is absent by
    construction: the query starts from ``videos``, never from ``sightings``.
    """
    videos = get_videos_in_current_batch(session)
    if not videos:
        return []

    camera_ids = {video.camera_id for video in videos}
    cameras = session.exec(
        select(Camera).where(col(Camera.id).in_(camera_ids))
    ).all()
    cameras_by_id = {camera.id: camera for camera in cameras}

    # Newest video wins if a camera was uploaded to twice in one batch.
    newest_by_camera: dict[str, Video] = {}
    for video in sorted(videos, key=lambda v: (v.uploaded_at, v.id)):
        newest_by_camera[video.camera_id] = video

    pairs = [
        (cameras_by_id[camera_id], video)
        for camera_id, video in newest_by_camera.items()
        if camera_id in cameras_by_id
    ]
    pairs.sort(key=lambda pair: pair[0].code)
    return pairs


def delete_all(session: Session) -> int:
    """Remove every video row. Used by the demo reset."""
    videos = session.exec(select(Video)).all()
    for video in videos:
        session.delete(video)
    session.commit()
    return len(videos)
