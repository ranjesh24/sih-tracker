"""Shared route dependencies.

Long-lived resources (the camera graph, the vector index, the broadcaster and
the ingest lock) are built once in the app lifespan and read from ``app.state``.
"""
import asyncio

from fastapi import Request

from app.services.broadcaster import Broadcaster
from app.services.camera_graph import CameraGraph
from app.services.vector_index import VectorIndex

# Re-exported so routers depend on one place for a DB session.
from app.db.session import get_session  # noqa: F401


def get_graph(request: Request) -> CameraGraph:
    return request.app.state.graph


def get_index(request: Request) -> VectorIndex:
    return request.app.state.index


def get_broadcaster(request: Request) -> Broadcaster:
    return request.app.state.broadcaster


def get_ingest_lock(request: Request) -> asyncio.Lock:
    return request.app.state.ingest_lock
