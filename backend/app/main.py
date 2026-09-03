"""FastAPI application (techspec.md 5.1-5.5; appflow.md 2).

Auth is cut for this demo; every route is unauthenticated except ingest, which
keeps its X-Ingest-Key check. Long-lived resources — the camera graph, the
vector index, the broadcaster and the ingest lock — are built once in the
lifespan and stored on ``app.state``.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

import app.db.session as db_session
from app.api.deps import get_index, get_session
from app.api.v1 import ingest, sightings, vehicles, ws
from app.core.config import get_settings
from app.core.constants import API_V1_PREFIX
from app.core.exceptions import REQUEST_ID_ATTR, register_exception_handlers
from app.repositories import camera_repo
from app.schemas.common import HealthRead
from app.services.broadcaster import Broadcaster
from app.services.identity_resolver import build_graph
from app.services.vector_index import VectorIndex

_settings = get_settings()
_REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: create tables, build the graph and index, prime app.state."""
    db_session.init_db()
    with Session(db_session.engine) as session:
        graph = build_graph(session)
        index = VectorIndex(dim=_settings.EMBEDDING_DIM)
        index.rebuild_from_db(session)
    app.state.graph = graph
    app.state.index = index
    app.state.broadcaster = Broadcaster()
    app.state.ingest_lock = asyncio.Lock()
    yield


app = FastAPI(title="Marg", version="1.0", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a request id to state and echo it in the X-Request-ID header."""
    request_id = str(uuid.uuid4())
    setattr(request.state, REQUEST_ID_ATTR, request_id)
    response = await call_next(request)
    response.headers[_REQUEST_ID_HEADER] = request_id
    return response


_origins = [o.strip() for o in _settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,  # explicit origins, never "*" (rules.md 8)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(ingest.router, prefix=API_V1_PREFIX)
app.include_router(vehicles.router, prefix=API_V1_PREFIX)
app.include_router(sightings.router, prefix=API_V1_PREFIX)
app.include_router(ws.router, prefix=API_V1_PREFIX)


@app.get(f"{API_V1_PREFIX}/system/health", response_model=HealthRead, tags=["system"])
def health(
    index: VectorIndex = Depends(get_index),
    session: Session = Depends(get_session),
) -> HealthRead:
    """Unauthenticated liveness check."""
    cameras = camera_repo.get_active_cameras(session)
    return HealthRead(status="ok", index_size=len(index), camera_count=len(cameras))
