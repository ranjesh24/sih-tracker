"""WebSocket events endpoint (techspec.md 5.5).

Auth is cut for this demo, so there is no handshake token check. The client
sends ``{"type": "ping"}`` periodically and receives ``{"type": "pong"}``; all
server events are pushed by the broadcaster.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.broadcaster import Broadcaster

router = APIRouter(tags=["ws"])

_PING = "ping"
_PONG = {"type": "pong"}


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    broadcaster: Broadcaster = websocket.app.state.broadcaster
    await broadcaster.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == _PING:
                await websocket.send_json(_PONG)
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
