"""Spatio-temporal gate (techspec.md section 5.6).

The differentiator. Given a source camera, a destination camera, and the elapsed
time between two sightings, it decides whether the transit is physically
feasible and returns the numbers behind the decision so a rejection can be shown
to an operator and persisted to ``match_decisions``.

Four rejection reasons plus FEASIBLE (TASK-118):
    SAME_CAMERA_TOO_SOON, NO_PATH, TEMPORAL_TOO_FAST, TEMPORAL_EXPIRED, FEASIBLE.

An absent camera is a configuration error, not a match outcome: the gate raises
:class:`CameraNotFoundError` rather than returning a status for it.

Pure in the sense of no I/O and no database — it reads only the in-memory camera
graph passed to it, which keeps it unit-testable (rules.md section 6).
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.core.exceptions import CameraNotFoundError
from app.services.camera_graph import CameraGraph, PathResult


class GateStatus(str, Enum):
    """Outcome of the spatio-temporal gate: FEASIBLE plus four rejections."""

    FEASIBLE = "FEASIBLE"
    SAME_CAMERA_TOO_SOON = "SAME_CAMERA_TOO_SOON"
    NO_PATH = "NO_PATH"
    TEMPORAL_TOO_FAST = "TEMPORAL_TOO_FAST"
    TEMPORAL_EXPIRED = "TEMPORAL_EXPIRED"


@dataclass(frozen=True)
class GateDecision:
    """Immutable gate outcome plus the numbers behind it.

    ``reason`` is ``None`` when ``passed`` is True; otherwise it is the rejection
    reason string. The transit numbers and ``path_camera_codes`` populate the
    matching columns in ``match_decisions`` (schema.md section 3.7).
    """

    status: GateStatus
    passed: bool
    reason: Optional[str]
    elapsed_seconds: int
    min_transit_seconds: Optional[int]
    max_transit_seconds: Optional[int]
    path_distance_m: Optional[float]
    path_camera_codes: Optional[list[str]]


def _feasible(elapsed_seconds: int, path: PathResult) -> GateDecision:
    return GateDecision(
        status=GateStatus.FEASIBLE,
        passed=True,
        reason=None,
        elapsed_seconds=elapsed_seconds,
        min_transit_seconds=path.min_transit_seconds,
        max_transit_seconds=path.max_transit_seconds,
        path_distance_m=path.distance_m,
        path_camera_codes=path.camera_codes,
    )


def _reject(
    status: GateStatus, elapsed_seconds: int, path: Optional[PathResult]
) -> GateDecision:
    return GateDecision(
        status=status,
        passed=False,
        reason=status.value,
        elapsed_seconds=elapsed_seconds,
        min_transit_seconds=path.min_transit_seconds if path else None,
        max_transit_seconds=path.max_transit_seconds if path else None,
        path_distance_m=path.distance_m if path else None,
        path_camera_codes=path.camera_codes if path else None,
    )


def evaluate_gate(
    from_camera_id: str,
    to_camera_id: str,
    elapsed_seconds: int,
    graph: CameraGraph,
    min_revisit_seconds: int,
) -> GateDecision:
    """Decide whether a transit between two cameras is physically feasible.

    Args:
        from_camera_id: camera of the earlier (candidate) sighting.
        to_camera_id: camera of the later sighting.
        elapsed_seconds: seconds between the two sightings, from ``first_frame_at``.
        graph: the camera graph supplying the shortest path and transit window.
        min_revisit_seconds: minimum gap to accept a revisit of the same camera.

    Returns:
        A :class:`GateDecision` — ``passed`` with FEASIBLE, or one of four
        rejection reasons — carrying the numbers behind the decision.

    Raises:
        CameraNotFoundError: if either camera is absent from the graph.
    """
    if not graph.has_camera(from_camera_id):
        raise CameraNotFoundError(from_camera_id)
    if not graph.has_camera(to_camera_id):
        raise CameraNotFoundError(to_camera_id)

    path = graph.shortest_path(from_camera_id, to_camera_id)

    if from_camera_id == to_camera_id:
        if elapsed_seconds < min_revisit_seconds:
            return _reject(GateStatus.SAME_CAMERA_TOO_SOON, elapsed_seconds, path)
        return _feasible(elapsed_seconds, path)

    if not path.exists:
        return _reject(GateStatus.NO_PATH, elapsed_seconds, None)

    if elapsed_seconds < path.min_transit_seconds:
        return _reject(GateStatus.TEMPORAL_TOO_FAST, elapsed_seconds, path)

    if elapsed_seconds > path.max_transit_seconds:
        return _reject(GateStatus.TEMPORAL_EXPIRED, elapsed_seconds, path)

    return _feasible(elapsed_seconds, path)
