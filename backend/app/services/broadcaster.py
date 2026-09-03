"""WebSocket broadcaster and message builders (techspec.md 5.5).

Holds the set of live connections and fan-outs server events to all of them.
Message builders are pure functions returning the ``{type, data}`` shapes from
techspec.md 5.5, so routes never assemble message dicts by hand.
"""
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

TYPE_SIGHTING_CREATED = "sighting.created"
TYPE_MATCH_AMBIGUOUS = "match.ambiguous"
TYPE_MATCH_REJECTED = "match.rejected"
TYPE_WORKER_STATUS = "worker.status"
TYPE_SYSTEM_ERROR = "system.error"


class Broadcaster:
    """Registry of connected clients with fan-out broadcast."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new connection."""
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection from the registry."""
        self._connections.discard(websocket)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict) -> None:
        """Send a message to every live connection, dropping dead ones."""
        dead: list[WebSocket] = []
        for websocket in list(self._connections):
            if websocket.client_state != WebSocketState.CONNECTED:
                dead.append(websocket)
                continue
            try:
                await websocket.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)


def sighting_created(
    *,
    sighting_id: str,
    vehicle_id: Optional[str],
    camera_id: str,
    camera_code: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    timestamp: str,
    vehicle_class: str,
    plate: Optional[str],
    plate_confidence: Optional[float],
    match_method: Optional[str],
    match_score: Optional[float],
    crop_url: str,
) -> dict:
    return {
        "type": TYPE_SIGHTING_CREATED,
        "data": {
            "sighting_id": sighting_id,
            "vehicle_id": vehicle_id,
            "camera_id": camera_id,
            "camera_code": camera_code,
            "lat": lat,
            "lng": lng,
            "timestamp": timestamp,
            "vehicle_class": vehicle_class,
            "plate": plate,
            "plate_confidence": plate_confidence,
            "match_method": match_method,
            "match_score": match_score,
            "crop_url": crop_url,
        },
    }


def match_ambiguous(
    *,
    sighting_id: str,
    candidate_count: int,
    top_score: Optional[float],
    runner_up_score: Optional[float],
    margin: Optional[float],
) -> dict:
    return {
        "type": TYPE_MATCH_AMBIGUOUS,
        "data": {
            "sighting_id": sighting_id,
            "candidate_count": candidate_count,
            "top_score": top_score,
            "runner_up_score": runner_up_score,
            "margin": margin,
        },
    }


def match_rejected(
    *,
    sighting_id: str,
    candidate_vehicle_id: Optional[str],
    reason: Optional[str],
    visual_score: Optional[float],
    elapsed_seconds: Optional[int],
    min_transit_seconds: Optional[int],
) -> dict:
    return {
        "type": TYPE_MATCH_REJECTED,
        "data": {
            "sighting_id": sighting_id,
            "candidate_vehicle_id": candidate_vehicle_id,
            "reason": reason,
            "visual_score": visual_score,
            "elapsed_seconds": elapsed_seconds,
            "min_transit_seconds": min_transit_seconds,
        },
    }


def worker_status(
    *, camera_id: str, status: str, fps: Optional[float], last_frame_at: Optional[str]
) -> dict:
    return {
        "type": TYPE_WORKER_STATUS,
        "data": {
            "camera_id": camera_id,
            "status": status,
            "fps": fps,
            "last_frame_at": last_frame_at,
        },
    }


def system_error(*, code: str, message: str, camera_id: Optional[str]) -> dict:
    return {
        "type": TYPE_SYSTEM_ERROR,
        "data": {"code": code, "message": message, "camera_id": camera_id},
    }
