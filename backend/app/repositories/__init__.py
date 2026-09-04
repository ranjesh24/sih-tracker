"""Repository layer — explicit re-exports for clean imports."""

from app.repositories import (  # noqa: F401
    camera_repo,
    match_decision_repo,
    sighting_repo,
    vehicle_repo,
)
