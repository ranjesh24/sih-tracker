# techspec.md — Technical Specification

**Project:** Marg (SIH26127)
**Version:** 1.0
**Companion docs:** `prd.md`, `schema.md`, `rules.md`

---

## 1. Architectural Overview

Three deployable units, deliberately separated. The separation is not ceremony — it exists because the ML pipeline needs a heavy CUDA environment that would make the API server slow to start and painful to iterate on, and because four people working in one Python environment will break each other's installs.

```
┌──────────────────────────────────────────────────────────────────┐
│  ml-pipeline/   (Python 3.11 · PyTorch · CUDA)                    │
│                                                                   │
│  One worker process per camera:                                   │
│    frame → YOLOv8s detect → ByteTrack → tracklet                  │
│    tracklet ends → best-shot select → plate OCR + OSNet embed     │
│    → POST /api/v1/ingest/sightings                                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (JSON + base64 crop)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  backend/       (Python 3.11 · FastAPI · lightweight venv)        │
│                                                                   │
│  Ingest → IdentityResolver                                        │
│    plate tier  (rapidfuzz + confusion map)                        │
│    visual tier: camera graph feasible_candidates() GENERATES the  │
│      candidate set; vision (cosine) RANKS within it; FAISS is an   │
│      optimisation over the feasible set, not the generator        │
│    SpatioTemporalGate (networkx camera graph) floors infeasible   │
│           → SQLite write → WebSocket broadcast                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ REST + WebSocket
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  frontend/      (Node 22 · React 19 · Vite · TypeScript)          │
│  Camera wall · Leaflet trajectory map · search · admin            │
└──────────────────────────────────────────────────────────────────┘
```

### Why the pipeline talks to the backend over HTTP

The obvious alternative is to run the models inside FastAPI. Do not. Model inference is CPU/GPU-bound and blocks the event loop; a single slow OCR call would stall the WebSocket broadcast to every connected client. HTTP between the two keeps the API responsive and lets the pipeline be restarted independently — which matters when someone is tuning a detection threshold at 2 a.m. and the frontend developer needs the API to stay up.

---

## 2. Tech Stack

### 2.1 ML Pipeline (`ml-pipeline/`)

| Concern | Choice | Version | Licence |
|---|---|---|---|
| Language | Python | 3.11.x | PSF |
| Deep learning | PyTorch | 2.x (match CUDA) | BSD-3 |
| Detection + tracking | Ultralytics (YOLOv8s + ByteTrack) | 8.4.x | **AGPL-3.0** |
| Re-ID backbone | torchreid (`deep-person-reid`) — OSNet x1.0 | git source | MIT |
| Plate OCR | EasyOCR | 1.7.2 | Apache-2.0 |
| Video / image | opencv-python-headless | 4.9.0.80 | Apache-2.0 |
| Arrays | numpy | 1.26.x | BSD-3 |
| Tracker assignment | lap | 0.5.x | BSD-2 |
| HTTP client | httpx | 0.28.x | BSD-3 |
| Config | pydantic-settings | 2.x | MIT |

> **Licence flag — read this before the presentation.** Ultralytics YOLOv8 is AGPL-3.0. For a hackathon, research, and open-source demonstration this is fine, and the repository will be public in any case. It is *not* fine for closed-source commercial deployment without an Ultralytics Enterprise licence. If a judge asks about commercialisation, the correct answer is: the detector is swappable behind the `Detector` interface, and an Apache-2.0 alternative such as RT-DETR or YOLOX drops in without touching the rest of the pipeline. Knowing this and saying it unprompted reads as engineering maturity. Being caught not knowing it does the opposite.

> **Install note.** `pip install torchreid` fetches an unmaintained 0.2.5 package that is not the library you want. Install from source:
> `pip install git+https://github.com/KaiyangZhou/deep-person-reid.git`
> OSNet ImageNet-pretrained weights download on first use; cache them into `models/` and commit the download script, not the weights.

> **opencv version.** Pin 4.9.0.80 rather than the 5.x line. OpenCV 5 changed several Python API defaults and the tracking/video code in every tutorial and Stack Overflow answer assumes 4.x. Six-day timeline; do not spend an afternoon on this.

> **AMENDMENT 2026-09-02 (TASK-000).** Detector is **YOLOv8s**, not YOLOv8n — tested and working on our footage. Plate OCR is **EasyOCR**, not PaddleOCR: PaddleOCR raised `NotImplementedError` in testing, so `paddlepaddle`/PaddleOCR are dropped. Re-ID input size is **256×256**, not 256×128 — 256×128 is a person aspect ratio; vehicles are wide. See the `ml-pipeline/.env` block in §7.

### 2.2 Backend (`backend/`)

| Concern | Choice | Version | Licence |
|---|---|---|---|
| Language | Python | 3.11.x | PSF |
| Web framework | FastAPI | 0.141.x | MIT |
| ASGI server | uvicorn[standard] | 0.52.x | BSD-3 |
| Validation | pydantic | 2.13.x | MIT |
| Settings | pydantic-settings | 2.x | MIT |
| ORM | SQLModel | 0.0.42 | MIT |
| Migrations | alembic | 1.19.x | MIT |
| Vector search | faiss-cpu | 1.15.x | MIT |
| Graph | networkx | 3.6.x | BSD-3 |
| Fuzzy plate matching | rapidfuzz | 3.14.x | MIT |
| JWT | python-jose[cryptography] | 3.5.x | MIT |
| Password hashing | bcrypt | 4.2.x | Apache-2.0 |
| Form/file parsing | python-multipart | 0.0.x | Apache-2.0 |
| Testing | pytest, pytest-asyncio, httpx | 8.x / 0.28.x | MIT / BSD-3 |
| Arrays | numpy | 1.26.x | BSD-3 |

> `faiss-cpu`, not `faiss-gpu`. At demo scale (10k–100k vectors) a CPU flat index answers a top-50 query in single-digit milliseconds. `faiss-gpu` adds a CUDA-version-coupled install that will fight the PyTorch install in the same environment. Not worth it.

> `bcrypt` pinned to 4.2.x, not 5.x. `passlib` 1.7.4 reads `bcrypt.__about__.__version__`, which bcrypt 5 removed; the combination raises on import. Either pin bcrypt 4.2.x, or skip passlib entirely and call the `bcrypt` package directly. **This spec chooses the latter — use `bcrypt` directly, do not add passlib.** One fewer dependency and one fewer known breakage.

### 2.3 Frontend (`frontend/`)

| Concern | Choice | Version | Licence |
|---|---|---|---|
| Runtime | Node.js | 22 LTS | MIT |
| Package manager | **pnpm** 9.x | — | MIT |
| Framework | React | 19.2.x | MIT |
| Build tool | Vite | 7.3.x | MIT |
| Language | TypeScript | 5.9.x | Apache-2.0 |
| Styling | Tailwind CSS | 4.3.x | MIT |
| Map | Leaflet + react-leaflet | 1.9.4 / 5.0.x | BSD-2 / Hippocratic-2.1 |
| Server state | @tanstack/react-query | 5.x | MIT |
| Client state | zustand | 5.x | MIT |
| HTTP | axios | 1.x | MIT |
| Routing | react-router-dom | 7.x | MIT |
| Dates | date-fns | 4.x | MIT |
| Class merging | clsx + tailwind-merge | 2.x / 2.x | MIT |
| Icons | lucide-react | 0.4xx | ISC |
| Charts | recharts | 3.x | MIT |
| Testing | vitest + @testing-library/react | 4.x / 16.x | MIT |

> **Vite 7 and TypeScript 5.9, not Vite 8 / TS 7.** Both newer lines exist. Neither has the ecosystem settled around it yet, and a plugin incompatibility discovered on Wednesday is a day you do not have. Ship on the version everything is tested against.

> **Leaflet, not Mapbox GL.** Mapbox requires an API token and a network round-trip for tiles. Requirement D-6 says the demo runs offline. Leaflet with OpenStreetMap tiles in development, plus a pre-downloaded local tile cache for the demo, removes venue wifi from the critical path entirely. Mapbox is a post-MVP swap if a nicer basemap is wanted.

> **pnpm, not npm.** Faster installs and a stricter dependency tree, which enforces the zero-hallucination package policy in `rules.md` by making undeclared transitive imports fail loudly.

### 2.4 Hosting and runtime

Local-first, deliberately. Nothing in this project needs to be deployed to win the round, and time spent on cloud deployment is time not spent on the demo.

| Component | Development | Demo | Post-MVP target |
|---|---|---|---|
| ML pipeline | Local, CUDA | Local on demo laptop | Jetson at camera site |
| Backend | `uvicorn --reload`, port 8000 | `uvicorn`, 2 workers | Docker on a VM |
| Frontend | `vite dev`, port 5173 | `vite preview` on static build | Static hosting behind nginx |
| Database | SQLite, `backend/data/marg.db` | Same, pre-seeded | PostgreSQL 16 |
| Vector index | In-memory FAISS | Same, rebuilt at startup | Qdrant |
| Map tiles | OSM public tiles | **Local tile cache in `frontend/public/tiles/`** | Self-hosted tile server |

A `docker-compose.yml` exists for the backend and frontend as a convenience for anyone whose local Python install is broken. The ML pipeline is **not** containerised — GPU passthrough is a time sink and offers nothing for a demo.

---

## 3. Database and Storage

### 3.1 Primary database — SQLite

**This overrides the earlier "no database, FAISS only" position, and here is why.** FAISS is a vector index. It stores float arrays and returns integer indices. It cannot store a timestamp, a camera ID, a plate string, or a match decision, and it has no query language. Something must map FAISS index positions back to sighting records, and that something is a database whether or not it is called one.

SQLite is the right choice because it keeps every advantage that motivated avoiding Postgres:

- Zero configuration and zero running service. No Docker required, no port conflicts, no "it works on my machine."
- The entire database is one file. Committing a pre-seeded demo database means the demo works from a clean clone.
- Reads are effectively instantaneous at this scale.
- Migration to PostgreSQL is a connection-string change, because SQLModel abstracts the dialect and NFR-SC2 confines data access to a repository layer.

Configuration:
- WAL mode enabled — concurrent reads while the ingest path writes.
- `foreign_keys = ON` per connection. SQLite does not enforce foreign keys by default; this must be set explicitly in the engine's `connect` event or the cascade rules in `schema.md` are decorative.
- Path from `DATABASE_URL`, default `sqlite:///./data/marg.db`.

### 3.2 Vector index — FAISS, in-memory

- Index type: `IndexIDMap2` wrapping `IndexFlatIP`, dimension 512.
- Vectors are L2-normalised before insertion, so inner product equals cosine similarity.
- `IndexFlatIP` is exact, not approximate. At demo scale this is both faster to reason about and more accurate than IVF or HNSW, and it has no training step. Do not add an approximate index for a dataset that fits in a few megabytes.
- IDs are the `sightings.id` primary key, so a FAISS result maps directly to a row without a side table.
- **Rebuild on startup.** Embeddings are also persisted as a BLOB on `sightings`. On boot, the backend reads them and reconstructs the index. This satisfies NFR-R2 and means a backend restart mid-demo is recoverable rather than fatal.
- Access is confined to `backend/app/services/vector_index.py` behind a `VectorIndex` protocol. No route or service imports `faiss` directly.

### 3.3 Blob storage — local filesystem

| Content | Path | Retention |
|---|---|---|
| Best-shot vehicle crops | `backend/data/crops/{camera_code}/{yyyy-mm-dd}/{sighting_id}.jpg` | Per `RETENTION_DAYS`, default 30 |
| Plate crops | `backend/data/crops/{camera_code}/{yyyy-mm-dd}/{sighting_id}_plate.jpg` | Same |
| Demo source video | `datasets/videos/` | Gitignored |
| Model weights | `ml-pipeline/models/` | Gitignored; fetched by `scripts/download_models.py` |
| Map tiles | `frontend/public/tiles/{z}/{x}/{y}.png` | Committed; small bounded region |

Crops are served through an authenticated route, not as static files. `GET /api/v1/sightings/{id}/crop` checks the caller's role before returning bytes. Serving `data/crops/` as a static directory would let anyone with a URL enumerate vehicle images, which defeats NFR-PR1 entirely.

### 3.4 Caching

None. No Redis, no cache layer. At demo scale SQLite reads are sub-millisecond and a cache adds an invalidation bug surface for no measurable gain. React Query provides client-side caching, which is where caching actually helps here.

---

## 4. Authentication and Authorisation

### 4.1 Roles

| Role | Can do | Cannot do |
|---|---|---|
| `admin` | Everything: manage cameras, edges, users; view unmasked plates; export | — |
| `operator` | View feeds, search, view unmasked plates, confirm/reject links, export | Manage cameras, edges, or users |
| `viewer` | View feeds, search, view trajectories with **masked** plates | Confirm links, export, manage anything |

Roles are a fixed enum, not a permissions table. Three roles with static capabilities is the correct complexity for this system; a generic RBAC engine would be over-engineering.

### 4.2 Token strategy

**Access token** — JWT, HS256, 30-minute expiry.

```json
{
  "sub": "<user uuid>",
  "role": "operator",
  "jti": "<uuid>",
  "iat": 1756800000,
  "exp": 1756801800,
  "iss": "marg-backend"
}
```

Returned in the JSON login response. The client holds it **in memory only** (a Zustand store), never in `localStorage` or `sessionStorage`. A page refresh loses it and the app silently re-acquires one via the refresh cookie. This is the deliberate trade: a refresh costs one round-trip, and in exchange no XSS can read the token from storage.

**Refresh token** — opaque, 32 bytes from `secrets.token_urlsafe`, 7-day expiry.

- Stored server-side as a SHA-256 hash in `refresh_tokens` (see `schema.md`). The raw value never touches the database.
- Delivered as a cookie: `httpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Secure` when `ENVIRONMENT != "development"`.
- **Rotated on every use.** The old token is revoked at the moment a new one is issued.
- Reuse detection: if a token already marked revoked is presented, every active token for that user is revoked and a `SECURITY` audit entry is written. This is the standard defence against a stolen refresh token and costs about fifteen lines.

### 4.3 Login flow

```
POST /api/v1/auth/login  { email, password }
  → bcrypt.checkpw against users.password_hash
  → on success: issue access token (body) + refresh cookie (Set-Cookie)
  → update users.last_login_at, write audit entry LOGIN_SUCCESS
  → on failure: 401, generic message, write audit entry LOGIN_FAILURE

POST /api/v1/auth/refresh   (cookie only, no body)
  → hash cookie value, look up refresh_tokens
  → if not found, expired, or revoked → 401 + clear cookie
  → if revoked and reuse detected → revoke all user tokens, 401, SECURITY audit
  → else: revoke old, issue new pair

POST /api/v1/auth/logout
  → revoke current refresh token, clear cookie, 204

GET  /api/v1/auth/me
  → current user profile from access token
```

**Failed-login throttling.** After 5 failures for one email within 15 minutes, return 429 for 15 minutes. Tracked in memory — a restart clears it, which is acceptable here and avoids a table.

### 4.4 Enforcement

Server-side, via FastAPI dependencies. Route handlers do not check roles inline.

```python
# backend/app/api/deps.py
CurrentUser  = Annotated[User, Depends(get_current_user)]
AdminUser    = Annotated[User, Depends(require_role(Role.ADMIN))]
OperatorUser = Annotated[User, Depends(require_role(Role.OPERATOR, Role.ADMIN))]
```

Plate masking happens in the **serialisation layer**, not the query. `SightingRead.from_orm_for_role(sighting, role)` returns `"••••••1234"` for `viewer`. Masking in the response model rather than the SQL guarantees no route can accidentally leak an unmasked plate by forgetting a filter.

### 4.5 Ingest authentication

The ML pipeline is a machine client and does not log in. It presents a static shared secret:

```
X-Ingest-Key: <INGEST_API_KEY from environment>
```

Compared with `secrets.compare_digest`. Applies only to `/api/v1/ingest/*`. A rotating key for a pipeline that starts once per demo would be complexity without benefit — but a plain `==` comparison would be a timing-attack footgun, so use the constant-time compare.

### 4.6 Seeded accounts

`scripts/seed_users.py` creates three accounts from environment variables with no defaults. If `SEED_ADMIN_PASSWORD` is unset the script exits with an error rather than falling back to something guessable. `.env.example` documents the names and carries obvious placeholder values.

---

## 5. API Architecture

### 5.1 Conventions

- **REST over JSON.** Not GraphQL — the query shapes are known and fixed, and GraphQL would add a schema layer and a client library for no benefit at four people and six days. Not tRPC — the backend is Python, so tRPC's whole value proposition (shared TypeScript types) does not apply. Types are shared instead by generating `frontend/src/types/api.ts` from the OpenAPI schema FastAPI already produces.
- **Base path** `/api/v1`. Versioned from the first commit; retrofitting a version prefix later touches every file.
- **Plural, lowercase, hyphenated resources**: `/vehicles`, `/cameras`, `/camera-edges`, `/sightings`, `/match-decisions`.
- **Verbs only as sub-resource actions** on a specific entity: `POST /match-decisions/{id}/confirm`.
- **Timestamps** are ISO-8601, UTC, with the `Z` suffix, everywhere, in both directions. The frontend converts to local time at render only.
- **IDs** are UUIDv4 strings, generated application-side. Not integers — integer IDs make record counts guessable and make merging seeded demo data with live data awkward.
- **Pagination** is `?limit=&offset=`, `limit` default 50, max 200. Every list response is wrapped in the envelope below. Cursor pagination is not needed at this scale.

### 5.2 Response envelope

Every successful list response:

```json
{
  "items": [ ... ],
  "total": 1284,
  "limit": 50,
  "offset": 0
}
```

Single-resource responses return the object directly, unwrapped. Wrapping a single object adds a level of nesting to every client access for no information gain.

### 5.3 Error payload

One shape for every error, no exceptions. Emitted by a global exception handler in `backend/app/core/exceptions.py`.

```json
{
  "error": {
    "code": "SPATIOTEMPORAL_REJECTED",
    "message": "Match rejected: transit time below physical minimum.",
    "details": {
      "elapsed_seconds": 14,
      "min_transit_seconds": 312,
      "distance_m": 5200,
      "from_camera": "CAM-01",
      "to_camera": "CAM-04"
    },
    "request_id": "01J9X2K4M7N8P0Q1R2S3T4U5V6"
  }
}
```

- `code` — stable `SCREAMING_SNAKE_CASE`. The frontend switches on `code`, never on `message`.
- `message` — one sentence, human-readable, safe to display. Never contains a stack trace, SQL, or a file path.
- `details` — structured context, or omitted. For 422s this is Pydantic's field-level error list.
- `request_id` — also returned as the `X-Request-ID` response header and included in the corresponding server log line, so a user-reported error maps to a log entry.

Status codes: `200` OK · `201` created · `204` no content · `400` malformed · `401` unauthenticated · `403` authenticated but wrong role · `404` not found · `409` conflict (duplicate camera code) · `422` validation failure · `429` rate limited · `500` unhandled.

### 5.4 Endpoints

#### Auth — `/api/v1/auth`

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/login` | public | Credentials → token pair |
| POST | `/refresh` | cookie | Rotate token pair |
| POST | `/logout` | any | Revoke refresh token |
| GET | `/me` | any | Current user profile |

#### Cameras — `/api/v1/cameras`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/` | any | List cameras with live status |
| POST | `/` | admin | Register a camera |
| GET | `/{id}` | any | Camera detail with edges |
| PATCH | `/{id}` | admin | Update camera |
| DELETE | `/{id}` | admin | Soft-delete (`is_active = false`) |
| GET | `/{id}/sightings` | any | Recent sightings at this camera |

#### Camera edges — `/api/v1/camera-edges`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/` | any | Full topology graph |
| POST | `/` | admin | Create edge with transit window |
| PATCH | `/{id}` | admin | Update transit window |
| DELETE | `/{id}` | admin | Remove edge |
| POST | `/estimate` | admin | Derive transit window from coordinates |

#### Vehicles — `/api/v1/vehicles`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/` | any | List/search. Params: `plate`, `plate_partial`, `from`, `to`, `camera_id`, `vehicle_class`, `min_sightings`, `limit`, `offset` |
| GET | `/{id}` | any | Vehicle summary |
| GET | `/{id}/trajectory` | any | Ordered sightings + polyline + per-hop decisions |
| GET | `/{id}/sightings` | any | Raw sightings |
| POST | `/{id}/split` | operator | Detach a sighting and re-resolve |
| POST | `/merge` | operator | Merge two vehicle IDs into one |

#### Sightings — `/api/v1/sightings`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/` | any | List with filters |
| GET | `/{id}` | any | Detail with match decisions |
| GET | `/{id}/crop` | any | Best-shot JPEG, auth-gated |
| GET | `/{id}/candidates` | operator | Top-K FAISS candidates with gate results — the explainability view |

#### Match decisions — `/api/v1/match-decisions`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/` | any | List. Params: `status`, `sighting_id`, `vehicle_id` |
| GET | `/ambiguous` | operator | Review queue |
| POST | `/{id}/confirm` | operator | Confirm link |
| POST | `/{id}/reject` | operator | Reject link, trigger re-resolution |

#### Ingest — `/api/v1/ingest` (machine only, `X-Ingest-Key`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/sightings` | Submit one resolved sighting |
| POST | `/sightings/batch` | Submit up to 50 sightings |
| POST | `/heartbeat` | Worker liveness and FPS report |

#### System — `/api/v1/system`

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | public | Liveness. No auth — needed before login works |
| GET | `/stats` | any | Counts, index size, worker status |
| GET | `/metrics` | admin | IDF1, MOTA, gate rejection counts |
| POST | `/reset-demo` | admin | Wipe sightings/vehicles, keep cameras and users |

`/system/reset-demo` earns its place. Between demo runs, someone needs to clear state in one action without re-seeding cameras. Doing this by hand under presentation pressure is how demos break.

### 5.5 WebSocket

**Endpoint:** `ws://<host>/api/v1/ws/events?token=<access_token>`

The token is passed as a query parameter because the browser WebSocket API cannot set headers. It is validated at handshake; the connection is closed with code 4001 if invalid. This is a real trade-off — the token appears in server access logs — and is accepted for a local demo. The production fix is a short-lived single-use ticket from `POST /auth/ws-ticket`, noted here so the answer exists if a judge asks.

Server → client messages, discriminated on `type`:

```json
{ "type": "sighting.created",
  "data": { "sighting_id": "...", "vehicle_id": "...", "camera_id": "...",
            "camera_code": "CAM-03", "lat": 25.6119, "lng": 85.1416,
            "timestamp": "2026-09-02T10:14:33Z", "vehicle_class": "car",
            "plate": "BR01AB1234", "plate_confidence": 0.87,
            "match_method": "PLATE_EXACT", "match_score": 0.94,
            "crop_url": "/api/v1/sightings/.../crop" } }

{ "type": "vehicle.trajectory_extended",
  "data": { "vehicle_id": "...", "new_segment": { "from_camera": "CAM-01",
            "to_camera": "CAM-03", "confidence": "probable" } } }

{ "type": "match.ambiguous",
  "data": { "sighting_id": "...", "candidate_count": 2, "top_score": 0.79,
            "runner_up_score": 0.77, "margin": 0.02 } }

{ "type": "match.rejected",
  "data": { "sighting_id": "...", "candidate_vehicle_id": "...",
            "reason": "TEMPORAL_TOO_FAST", "visual_score": 0.91,
            "elapsed_seconds": 14, "min_transit_seconds": 312 } }

{ "type": "worker.status",
  "data": { "camera_id": "...", "status": "running", "fps": 18.4,
            "last_frame_at": "2026-09-02T10:14:33Z" } }

{ "type": "system.error",
  "data": { "code": "WORKER_CRASHED", "message": "...", "camera_id": "..." } }
```

`match.rejected` is broadcast deliberately. Watching the system *refuse* a high-similarity match in real time, with the numbers on screen, is the clearest possible demonstration of the spatio-temporal gate. It belongs in the live event feed, not buried in a log.

Client → server: `{"type": "ping"}` every 25 s, answered with `{"type": "pong"}`. Keeps intermediaries from closing an idle socket and gives the client a liveness signal.

### 5.6 Identity resolution — the algorithm

This is the core of the system. It lives in `backend/app/services/identity_resolver.py` and is the most heavily tested module in the repository.

```
resolve(sighting) → (vehicle_id, MatchDecision)

1. GATE PREP
   Load candidate vehicles active within LOOKBACK_WINDOW (default 3600 s).

2. PLATE TIER  — attempted only if sighting.plate_valid
   a. Exact match on plate_text_norm → candidate
   b. Else rapidfuzz over candidate plates, applying the OCR confusion map,
      accept at edit distance ≤ 1
   c. For each candidate, run SpatioTemporalGate
   d. First candidate passing the gate → assign, method PLATE_EXACT | PLATE_FUZZY
   e. Plate matches but gate fails → record decision REJECTED with the reason
      and fall through to the visual tier. Do not assign.

3. VISUAL TIER  — AMENDED 2026-09-02 (TASK-000), see note below
   a. camera_graph.feasible_candidates(camera_id, first_frame_at) returns the
      set of vehicles physically able to be at this camera at this time, derived
      from the topology graph and the summed transit windows. This is the
      candidate generator — NOT FAISS. At demo scale it is 5 to 50 vehicles.
   b. Score EVERY member of the feasible set exhaustively:
        fused = W_VISUAL   * cosine_similarity
              + W_TEMPORAL * temporal_plausibility
      Defaults: W_VISUAL 0.45, W_TEMPORAL 0.55.
      (W_PLATE 0.20 is retained for the plate tier's agreement term; the visual
      fusion itself is visual + temporal only.)
   c. temporal_plausibility = 1 - |elapsed - expected| / (max_transit - min_transit),
      clamped to [0, 1]. A vehicle arriving near the expected transit time
      scores higher than one arriving at the edge of the feasible window.
   d. VISUAL_FLOOR (0.55) rules out obviously-different candidates: drop any
      candidate whose cosine_similarity < VISUAL_FLOOR before ranking. It is a
      floor, not a decision threshold — surviving the floor is not a match.
   e. If the top two survivors are within AMBIGUITY_MARGIN (0.05) of each other
      → status AMBIGUOUS, queue for operator review, NO assignment. This is
      expected to fire often on visually identical vehicles; that is correct
      behaviour, not a bug. Otherwise assign the top candidate, method VISUAL.

   AMENDMENT (TASK-000). Measured OSNet cosine on our footage: same vehicle
   0.65–0.75, different vehicle ≈0.70 — the distributions overlap, so visual
   similarity cannot generate candidates. The feasible set from the camera
   graph generates candidates; visual similarity only scores and floors them.
   FAISS is retained as an optimisation over the feasible set once the index is
   large, not as the candidate generator; the VectorIndex interface in §3.2 is
   kept exactly as written. MATCH_THRESHOLD is removed — under exhaustive
   scoring of a physically-constrained set it has no coherent meaning.

4. NEW IDENTITY
   Create a vehicle, method NEW.

5. ALWAYS
   Write a MatchDecision per candidate evaluated — accepted and rejected alike.
   Add the embedding to FAISS keyed by sighting.id.
   Broadcast over WebSocket.
```

**Spatio-temporal gate:**

```
gate(from_camera, to_camera, elapsed_seconds) → (passed, reason, details)

  same camera and elapsed < MIN_REVISIT (30 s)  → False, SAME_CAMERA_TOO_SOON
  no path in graph                              → False, NO_PATH
  elapsed < path.min_transit_seconds            → False, TEMPORAL_TOO_FAST
  elapsed > path.max_transit_seconds            → False, TEMPORAL_EXPIRED
  otherwise                                     → True,  FEASIBLE
```

Path transit times come from `networkx.shortest_path` over the camera graph, weighted by `min_transit_seconds`, summed along the path. The graph is loaded once at startup and rebuilt when an edge changes — it is small enough that a full rebuild is cheaper than an incremental update.

Where an edge lacks explicit transit times, they are derived:

```
distance_m     = haversine(cam_a, cam_b) * ROAD_WINDING_FACTOR   # default 1.35
min_transit_s  = distance_m / (MAX_PLAUSIBLE_SPEED_KMH / 3.6)    # default 80 km/h
max_transit_s  = distance_m / (MIN_PLAUSIBLE_SPEED_KMH / 3.6)    # default 8 km/h
```

The 8 km/h lower bound is not arbitrary. In dense Indian city traffic a vehicle genuinely can average single-digit speeds, and a tighter bound would reject correct matches during congestion — precisely when this system is most needed. The winding factor accounts for road distance exceeding straight-line distance.

**Every threshold above lives in `backend/app/core/config.py` and is environment-overridable.** During demo rehearsal these will be tuned against the actual footage. A hardcoded threshold is a threshold that cannot be fixed at 11 p.m. on Friday.

---

## 6. Third-Party Integrations

Deliberately almost none. Every external dependency is a thing that can fail during the demo.

| Integration | Purpose | Failure mode | Mitigation |
|---|---|---|---|
| OpenStreetMap tiles | Basemap in development | Rate limited or offline | Local tile cache in `frontend/public/tiles/`; demo never calls out |
| Ultralytics weight CDN | YOLOv8s weights, first run only | Download fails | Weights cached in `ml-pipeline/models/`, fetched during Phase 0 |
| torchreid weight host | OSNet ImageNet weights, first run only | Download fails | Same |
| PaddleOCR model host | Detection + recognition models, first run only | Download fails | Same |

**No external API is called at runtime.** No cloud vision service, no hosted LLM, no geocoder, no map API. The system is fully self-contained once weights are downloaded, which is what makes requirement D-6 achievable.

**Webhooks:** none inbound, none outbound. There is no third party to notify.

**Rate limits:** the only rate limiting is internal — 5 failed logins per email per 15 minutes.

**Phase 0 exit criterion:** run `scripts/download_models.py`, then disconnect from the network entirely and confirm the full stack still starts and processes a video. If it does not, something is calling out that should not be, and it will fail at the venue.

---

## 7. Configuration

Each of the three units has its own `.env`, and a committed `.env.example` listing every variable with a safe placeholder.

### `backend/.env`

```ini
ENVIRONMENT=development
DATABASE_URL=sqlite:///./data/marg.db
JWT_SECRET_KEY=                       # openssl rand -hex 32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
INGEST_API_KEY=                       # openssl rand -hex 32
CORS_ORIGINS=http://localhost:5173

EMBEDDING_DIM=512
# MATCH_THRESHOLD removed 2026-09-02 (TASK-000): no coherent meaning under
# exhaustive scoring of the spatio-temporal feasible set. See §5.6.
VISUAL_FLOOR=0.55
AMBIGUITY_MARGIN=0.05
FAISS_TOP_K=50
LOOKBACK_WINDOW_SECONDS=3600

# Fusion weights amended 2026-09-02 (TASK-000) after ML benchmarking.
W_VISUAL=0.45
W_PLATE=0.20
W_TEMPORAL=0.55

ROAD_WINDING_FACTOR=1.35
MAX_PLAUSIBLE_SPEED_KMH=80
MIN_PLAUSIBLE_SPEED_KMH=8
MIN_REVISIT_SECONDS=30

CROP_STORAGE_PATH=./data/crops
RETENTION_DAYS=30
LOG_LEVEL=INFO
```

### `ml-pipeline/.env`

```ini
BACKEND_URL=http://localhost:8000
INGEST_API_KEY=                       # must match backend
DEVICE=cuda                           # cuda | cpu

YOLO_MODEL_PATH=./models/yolov8s.pt
YOLO_CONF_THRESHOLD=0.35
YOLO_IOU_THRESHOLD=0.50
TARGET_CLASSES=2,3,5,7                # car, motorcycle, bus, truck

BYTETRACK_TRACK_THRESH=0.50
BYTETRACK_MATCH_THRESH=0.80
BYTETRACK_TRACK_BUFFER=30

MIN_TRACKLET_FRAMES=8
BEST_SHOT_MIN_AREA=2500

REID_MODEL=osnet_x1_0
REID_INPUT_SIZE=256,256               # amended TASK-000: vehicles are wide, not 256,128
REID_BATCH_SIZE=16

OCR_ENGINE=easyocr                    # amended TASK-000: PaddleOCR raised NotImplementedError
OCR_MIN_CONFIDENCE=0.40

PLAYBACK_FPS=15
FRAME_SKIP=2
```

### `frontend/.env`

```ini
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000/api/v1/ws/events
VITE_MAP_TILE_URL=/tiles/{z}/{x}/{y}.png
VITE_MAP_CENTER_LAT=25.6119
VITE_MAP_CENTER_LNG=85.1416
VITE_MAP_DEFAULT_ZOOM=13
```

Map defaults are Patna coordinates. Change them to match wherever the demo footage was captured.

---

## 8. Repository Layout

```
sih-tracker/
├── .gitignore
├── README.md
├── CLAUDE.md
├── docs/
│   ├── prd.md  techspec.md  appflow.md  design.md
│   ├── schema.md  implementationplan.md  tracker.md  rules.md
│
├── ml-pipeline/
│   ├── .env.example  requirements.txt  README.md
│   ├── models/                 # gitignored
│   ├── scripts/
│   │   ├── download_models.py
│   │   ├── run_worker.py
│   │   ├── run_all_workers.py
│   │   └── benchmark_pipeline.py
│   ├── src/
│   │   ├── config.py
│   │   ├── detection/          detector.py  tracker.py
│   │   ├── anpr/               plate_detector.py  ocr.py  normalizer.py
│   │   ├── reid/               embedder.py  best_shot.py
│   │   ├── pipeline/           worker.py  frame_source.py  tracklet.py
│   │   └── client/             ingest_client.py
│   └── tests/
│
├── backend/
│   ├── .env.example  requirements.txt  alembic.ini  README.md
│   ├── data/                   # gitignored except .gitkeep
│   ├── alembic/versions/
│   ├── scripts/
│   │   ├── seed_users.py  seed_cameras.py
│   │   ├── evaluate_metrics.py
│   │   └── benchmark_faiss.py
│   ├── app/
│   │   ├── main.py
│   │   ├── core/               config.py  security.py  exceptions.py  logging.py
│   │   ├── db/                 session.py  base.py
│   │   ├── models/             user.py  camera.py  camera_edge.py  vehicle.py
│   │   │                       sighting.py  match_decision.py  audit_log.py
│   │   │                       refresh_token.py
│   │   ├── schemas/            auth.py  camera.py  vehicle.py  sighting.py
│   │   │                       match_decision.py  common.py
│   │   ├── api/                deps.py
│   │   │   └── v1/             auth.py  cameras.py  camera_edges.py  vehicles.py
│   │   │                       sightings.py  match_decisions.py  ingest.py
│   │   │                       system.py  ws.py
│   │   ├── services/           identity_resolver.py  spatiotemporal_gate.py
│   │   │                       vector_index.py  plate_matcher.py
│   │   │                       trajectory_builder.py  camera_graph.py
│   │   │                       broadcaster.py  audit.py
│   │   └── repositories/       vehicle_repo.py  sighting_repo.py  camera_repo.py
│   └── tests/                  unit/  integration/  conftest.py
│
├── frontend/
│   ├── .env.example  package.json  pnpm-lock.yaml
│   ├── vite.config.ts  tsconfig.json  tailwind.config.ts
│   ├── public/tiles/
│   └── src/
│       ├── main.tsx  App.tsx  router.tsx
│       ├── styles/             globals.css  tokens.css
│       ├── lib/                api.ts  ws.ts  auth.ts  format.ts  cn.ts
│       ├── types/              api.ts  domain.ts
│       ├── stores/             authStore.ts  liveStore.ts  uiStore.ts
│       ├── hooks/              useVehicles.ts  useTrajectory.ts
│       │                       useLiveEvents.ts  useCameras.ts
│       ├── components/
│       │   ├── ui/             Button  Input  Badge  Table  Dialog
│       │   │                   Skeleton  EmptyState  Toast
│       │   ├── layout/         AppShell  Sidebar  TopBar  ConnectionIndicator
│       │   ├── camera/         CameraWall  CameraTile  DetectionOverlay
│       │   ├── map/            TrajectoryMap  CameraMarker  TrajectoryPolyline
│       │   │                   PlaybackControls
│       │   ├── vehicle/        VehicleCard  SightingTimeline  EvidencePanel
│       │   │                   MatchExplanation  ConfidenceBadge
│       │   └── admin/          CameraForm  EdgeForm  TopologyEditor
│       └── pages/              LoginPage  LiveWallPage  SearchPage
│                               VehicleDetailPage  ReviewQueuePage
│                               CamerasPage  NotFoundPage
│
├── datasets/                   # gitignored
│   ├── videos/  annotations/  eval/
│
├── scripts/                    dev.sh  demo.sh  reset_demo.sh
└── docker-compose.yml          # backend + frontend only
```

Each of the three units has an isolated environment. `ml-pipeline/` and `backend/` get separate virtualenvs; `frontend/` has its own `node_modules`. This is what prevents a PyTorch upgrade in the pipeline from breaking the API server, and it is the reason the person working on the map never has to install CUDA.
