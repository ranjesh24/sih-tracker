"""``videos`` table — the camera-to-uploaded-file association.

Not in schema.md: added because the live wall has to answer "which cameras have
an uploaded video *in this batch*", and nothing recorded that. The upload
endpoint previously tracked jobs only in a module-level dict, so the association
was lost on restart and invisible to any query.

Filtering the wall on sightings instead is wrong: seeded or previously ingested
sightings make every camera look like it has footage, which is exactly the bug
this table exists to fix.
"""
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class Video(SQLModel, table=True):
    __tablename__ = "videos"
    __table_args__ = (
        Index("idx_videos_camera", "camera_id"),
        Index("idx_videos_batch", "batch_id"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    camera_id: str = Field(foreign_key="cameras.id", nullable=False)

    # Name of the stored file under the upload directory, not an absolute path:
    # the backend resolves it against its own upload root when serving.
    filename: str = Field(nullable=False)

    # Groups the videos of one upload session. The live wall shows the newest
    # batch, so a fresh set of uploads replaces the previous wall rather than
    # accumulating with it.
    batch_id: str = Field(nullable=False)

    job_id: Optional[str] = Field(default=None)
    uploaded_at: str = Field(default_factory=utcnow, nullable=False)
