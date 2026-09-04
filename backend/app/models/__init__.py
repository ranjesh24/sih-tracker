"""SQLModel table models (schema.md section 3), one class per file (techspec §8)."""
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_edge import CameraEdge
from app.models.match_decision import MatchDecision
from app.models.refresh_token import RefreshToken
from app.models.sighting import Sighting
from app.models.user import User
from app.models.video import Video
from app.models.vehicle import Vehicle

__all__ = [
    "AuditLog",
    "Camera",
    "CameraEdge",
    "MatchDecision",
    "RefreshToken",
    "Sighting",
    "User",
    "Video",
    "Vehicle",
]
