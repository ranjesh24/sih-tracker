# schema.md — Data Model

**Project:** Marg (SIH26127)
**Version:** 1.0
**Database:** SQLite (dev and demo) → PostgreSQL 16 (post-MVP)
**ORM:** SQLModel 0.0.42 · Migrations: Alembic 1.19

---

## 1. Entity Relationship Model

```
                         ┌──────────┐
                         │  users   │
                         └────┬─────┘
                              │ 1
              ┌───────────────┼────────────────┐
              │ N             │ N              │ N
     ┌────────▼──────┐  ┌─────▼───────┐  ┌─────▼──────────┐
     │ refresh_tokens│  │ audit_logs  │  │ match_decisions│
     └───────────────┘  └─────────────┘  │  (decided_by)  │
                                          └────────┬───────┘
                                                   │ N
   ┌──────────┐                                    │
   │ cameras  │◄──────┐                            │ 1
   └────┬─────┘       │ N (from/to)         ┌──────▼──────┐
        │ 1           │                     │  sightings  │
        │        ┌────┴─────────┐           └──────┬──────┘
        │        │ camera_edges │                  │ N
        │        └──────────────┘                  │
        │ N                                        │ 1
        └────────────────────────────────►  ┌──────▼──────┐
                                             │  vehicles   │
                                             └─────────────┘
```

### Relationships

| From | To | Cardinality | Notes |
|---|---|---|---|
| `users` → `refresh_tokens` | 1:N | One user, many active sessions. Cascade delete. |
| `users` → `audit_logs` | 1:N | Nullable actor for system-generated entries. Restrict delete. |
| `users` → `match_decisions` | 1:N | As `decided_by`. Nullable — most decisions are automatic. |
| `cameras` ↔ `cameras` | N:M via `camera_edges` | Self-referential. This is the topology graph the feasibility gate traverses. |
| `cameras` → `sightings` | 1:N | Restrict delete; cameras are soft-deleted so history survives. |
| `vehicles` → `sightings` | 1:N | A vehicle is exactly the set of sightings resolved to one identity. `vehicle_id` is nullable during resolution. Set null on delete. |
| `sightings` → `match_decisions` | 1:N | Every candidate evaluated writes a row, accepted or rejected. Cascade delete. |
| `vehicles` → `match_decisions` | 1:N | As `candidate_vehicle_id`. Cascade delete. |

### The two relationships that carry the system

**`camera_edges` is the topology graph.** It is not reference data. Every spatio-temporal rejection traces back to a row in this table, and an edge with a wrong transit window silently corrupts every match that crosses it. It is loaded into a `networkx` graph at startup and rebuilt on change.

**`match_decisions` is the audit trail of reasoning.** Most systems store only the outcome. This one stores every candidate considered, its component scores, and — for rejections — the reason and the numbers that produced it. That table is what makes the evidence panel possible, what makes the ablation study in `prd.md` §7.1 computable, and what turns "the system says these are the same car" into "here is why, and here is what it ruled out."

---

## 2. Conventions

- **Primary keys** are `TEXT` UUIDv4, generated application-side via `uuid.uuid4()`. Not autoincrement integers: sequential IDs leak record counts, make merging seeded demo data with live data awkward, and would need rewriting on the PostgreSQL migration anyway.
- **Timestamps** are `TEXT` in ISO-8601 UTC with a `Z` suffix. SQLite has no native datetime type; storing ISO-8601 keeps lexicographic ordering equal to chronological ordering, which means range queries and `ORDER BY` work correctly without a conversion function. Column names end in `_at`.
- **Booleans** are `INTEGER` 0/1 with explicit defaults. SQLite has no boolean type.
- **Embeddings** are `BLOB` — 512 float32 values, 2048 bytes, produced by `numpy.ndarray.tobytes()` on a C-contiguous array. Never store as JSON; a 512-element JSON array is roughly 6 KB of text and needs parsing on every read.
- **Enums** are `TEXT` with a `CHECK` constraint. SQLite has no enum type, and a check constraint gives the same guarantee with a readable value in the file.
- **Foreign keys** require `PRAGMA foreign_keys = ON` per connection. SQLite ignores foreign keys by default. This is set in a SQLAlchemy `connect` event listener in `backend/app/db/session.py`. Without it, every cascade and restrict rule below is documentation rather than enforcement.
- **Money, coordinates, scores** are `REAL`. Latitude and longitude are decimal degrees, WGS84.

---

## 3. Tables

### 3.1 `users`

```sql
CREATE TABLE users (
    id              TEXT     PRIMARY KEY NOT NULL,
    email           TEXT     NOT NULL UNIQUE,
    full_name       TEXT     NOT NULL,
    password_hash   TEXT     NOT NULL,
    role            TEXT     NOT NULL DEFAULT 'viewer'
                             CHECK (role IN ('admin','operator','viewer')),
    is_active       INTEGER  NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    last_login_at   TEXT,
    created_at      TEXT     NOT NULL,
    updated_at      TEXT     NOT NULL
);

CREATE UNIQUE INDEX idx_users_email  ON users(email);
CREATE        INDEX idx_users_role   ON users(role);
```

`password_hash` holds a bcrypt hash at cost 12. Emails are lowercased before insert so uniqueness is case-insensitive without a functional index.

---

### 3.2 `refresh_tokens`

```sql
CREATE TABLE refresh_tokens (
    id           TEXT    PRIMARY KEY NOT NULL,
    user_id      TEXT    NOT NULL,
    token_hash   TEXT    NOT NULL UNIQUE,
    issued_at    TEXT    NOT NULL,
    expires_at   TEXT    NOT NULL,
    revoked_at   TEXT,
    replaced_by  TEXT,
    user_agent   TEXT,
    ip_address   TEXT,

    FOREIGN KEY (user_id)     REFERENCES users(id)          ON DELETE CASCADE,
    FOREIGN KEY (replaced_by) REFERENCES refresh_tokens(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_refresh_hash    ON refresh_tokens(token_hash);
CREATE        INDEX idx_refresh_user    ON refresh_tokens(user_id, revoked_at);
CREATE        INDEX idx_refresh_expires ON refresh_tokens(expires_at);
```

`token_hash` is SHA-256 of the raw token. The raw value exists only in the httpOnly cookie; a database dump therefore contains no usable session credential.

`replaced_by` implements rotation and reuse detection. When a token is rotated it is marked revoked and points at its successor. If a revoked token is presented again, that is a reuse event: revoke every active token for the user and write a `SECURITY` audit entry.

---

### 3.3 `cameras`

```sql
CREATE TABLE cameras (
    id              TEXT     PRIMARY KEY NOT NULL,
    code            TEXT     NOT NULL UNIQUE,
    name            TEXT     NOT NULL,
    location_label  TEXT,
    latitude        REAL     NOT NULL CHECK (latitude  BETWEEN  -90 AND  90),
    longitude       REAL     NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    heading_deg     REAL     CHECK (heading_deg IS NULL OR
                                    heading_deg BETWEEN 0 AND 360),
    stream_uri      TEXT,
    resolution_w    INTEGER,
    resolution_h    INTEGER,
    is_active       INTEGER  NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    last_seen_at    TEXT,
    created_at      TEXT     NOT NULL,
    updated_at      TEXT     NOT NULL
);

CREATE UNIQUE INDEX idx_cameras_code   ON cameras(code);
CREATE        INDEX idx_cameras_active ON cameras(is_active);
```

`code` is the short human identifier used everywhere in the UI and in worker configuration: `CAM-01`, `CAM-02`. Uppercase, unique, stable. Workers are launched against a code, not a UUID, because a UUID in a shell command is unusable.

`stream_uri` is a file path during the demo (`datasets/videos/cam01.mp4`) and an RTSP URL post-MVP. Same column; the worker's frame source dispatches on scheme.

`heading_deg` is the camera's compass bearing. Unused by the MVP matcher but recorded now, because direction-aware gating (a vehicle cannot appear at a camera facing away from its approach) is the obvious next refinement and backfilling the value later means revisiting every camera.

Cameras are **soft-deleted** by setting `is_active = 0`. Hard deletion would orphan historical sightings, and the foreign key below is `ON DELETE RESTRICT` specifically to make that impossible by accident.

---

### 3.4 `camera_edges`

```sql
CREATE TABLE camera_edges (
    id                    TEXT     PRIMARY KEY NOT NULL,
    from_camera_id        TEXT     NOT NULL,
    to_camera_id          TEXT     NOT NULL,
    distance_m            REAL     NOT NULL CHECK (distance_m > 0),
    min_transit_seconds   INTEGER  NOT NULL CHECK (min_transit_seconds >= 0),
    max_transit_seconds   INTEGER  NOT NULL CHECK (max_transit_seconds > 0),
    is_bidirectional      INTEGER  NOT NULL DEFAULT 1
                                   CHECK (is_bidirectional IN (0,1)),
    road_name             TEXT,
    is_estimated          INTEGER  NOT NULL DEFAULT 1
                                   CHECK (is_estimated IN (0,1)),
    created_at            TEXT     NOT NULL,
    updated_at            TEXT     NOT NULL,

    FOREIGN KEY (from_camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
    FOREIGN KEY (to_camera_id)   REFERENCES cameras(id) ON DELETE CASCADE,

    CHECK (from_camera_id <> to_camera_id),
    CHECK (max_transit_seconds > min_transit_seconds)
);

CREATE UNIQUE INDEX idx_edges_pair ON camera_edges(from_camera_id, to_camera_id);
CREATE        INDEX idx_edges_from ON camera_edges(from_camera_id);
CREATE        INDEX idx_edges_to   ON camera_edges(to_camera_id);
```

**This table is the differentiator.** Everything else here is standard CRUD; this is the part no comparable public system has.

`min_transit_seconds` and `max_transit_seconds` bound the physically plausible travel time along this road segment. The gate rejects any candidate match whose elapsed time falls outside the summed window along the shortest path. Defaults are derived as:

```
distance_m          = haversine(from, to) × ROAD_WINDING_FACTOR   (1.35)
min_transit_seconds = distance_m ÷ (80 km/h ÷ 3.6)
max_transit_seconds = distance_m ÷ (8 km/h  ÷ 3.6)
```

The 8 km/h floor gives a wide upper bound, and that is intentional. Indian city traffic genuinely averages single digits during congestion; a tighter bound would reject correct matches precisely when the tool is most needed. Precision comes from the lower bound — nothing crosses 5 km in fourteen seconds — and that is the bound that kills the "White Maruti" false merge.

`is_estimated` flags whether the window came from the formula or from a human. The admin UI surfaces this so an operator can see which edges are guesses. Once someone times an actual vehicle over the route, they override the values and the flag clears.

`is_bidirectional` at 1 means the gate treats the edge as traversable in both directions. Set it to 0 for one-way roads. Storing one row with a direction flag rather than two mirrored rows keeps the admin UI simpler and prevents the two halves drifting apart.

`ON DELETE CASCADE` on both camera references is correct here: an edge to a camera that no longer exists is meaningless. It does not conflict with soft-deletion, because soft-deleted cameras are never hard-deleted.

---

### 3.5 `vehicles`

```sql
CREATE TABLE vehicles (
    id                  TEXT     PRIMARY KEY NOT NULL,
    display_ref         TEXT     NOT NULL UNIQUE,
    canonical_plate     TEXT,
    plate_confidence    REAL     CHECK (plate_confidence IS NULL OR
                                        plate_confidence BETWEEN 0 AND 1),
    plate_is_valid      INTEGER  NOT NULL DEFAULT 0
                                 CHECK (plate_is_valid IN (0,1)),
    vehicle_class       TEXT     CHECK (vehicle_class IS NULL OR vehicle_class IN
                                 ('car','motorcycle','bus','truck','auto','other')),
    dominant_color      TEXT,
    sighting_count      INTEGER  NOT NULL DEFAULT 0
                                 CHECK (sighting_count >= 0),
    camera_count        INTEGER  NOT NULL DEFAULT 0
                                 CHECK (camera_count >= 0),
    first_seen_at       TEXT,
    last_seen_at        TEXT,
    status              TEXT     NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active','merged','archived')),
    merged_into_id      TEXT,
    created_at          TEXT     NOT NULL,
    updated_at          TEXT     NOT NULL,

    FOREIGN KEY (merged_into_id) REFERENCES vehicles(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_vehicles_ref        ON vehicles(display_ref);
CREATE        INDEX idx_vehicles_plate      ON vehicles(canonical_plate);
CREATE        INDEX idx_vehicles_last_seen  ON vehicles(last_seen_at DESC);
CREATE        INDEX idx_vehicles_status     ON vehicles(status);
CREATE        INDEX idx_vehicles_class_seen ON vehicles(vehicle_class, last_seen_at DESC);
```

A `vehicle` is a **hypothesis about identity**, not a registered vehicle. It is the set of sightings the system currently believes belong to one physical object. Operator confirmations strengthen the hypothesis; rejections split it.

`display_ref` is a short human-readable handle — `#A47F`, `#B12C` — derived from the first four hex characters of the UUID. Operators need to say vehicle identifiers out loud to each other, and a full UUID cannot be spoken.

`canonical_plate` is the best plate read across all of the vehicle's sightings, normalised. Null when no sighting produced a valid plate — which is the interesting case and must never be treated as an error.

`sighting_count` and `camera_count` are denormalised, maintained by the resolver on each assignment. Recomputing them per row in a search result list would mean an aggregate per row; the write path already touches the vehicle, so updating two counters there is free.

`merged_into_id` supports the operator merge action. Merged vehicles are kept with `status = 'merged'` and a pointer, rather than deleted, so any existing link or export still resolves to something meaningful.

---

### 3.6 `sightings`

The central table. One row per completed tracklet.

```sql
CREATE TABLE sightings (
    id                   TEXT     PRIMARY KEY NOT NULL,
    vehicle_id           TEXT,
    camera_id            TEXT     NOT NULL,
    local_track_id       INTEGER  NOT NULL,

    first_frame_at       TEXT     NOT NULL,
    last_frame_at        TEXT     NOT NULL,
    best_frame_at        TEXT     NOT NULL,
    received_at          TEXT     NOT NULL,
    frame_count          INTEGER  NOT NULL CHECK (frame_count > 0),

    bbox_x               INTEGER  NOT NULL,
    bbox_y               INTEGER  NOT NULL,
    bbox_w               INTEGER  NOT NULL CHECK (bbox_w > 0),
    bbox_h               INTEGER  NOT NULL CHECK (bbox_h > 0),
    detection_confidence REAL     NOT NULL
                                  CHECK (detection_confidence BETWEEN 0 AND 1),
    vehicle_class        TEXT     NOT NULL CHECK (vehicle_class IN
                                  ('car','motorcycle','bus','truck','auto','other')),

    plate_text_raw       TEXT,
    plate_text_norm      TEXT,
    plate_confidence     REAL     CHECK (plate_confidence IS NULL OR
                                         plate_confidence BETWEEN 0 AND 1),
    plate_is_valid       INTEGER  NOT NULL DEFAULT 0
                                  CHECK (plate_is_valid IN (0,1)),
    plate_bbox           TEXT,

    embedding            BLOB,
    embedding_dim        INTEGER  NOT NULL DEFAULT 512,
    in_vector_index      INTEGER  NOT NULL DEFAULT 0
                                  CHECK (in_vector_index IN (0,1)),

    crop_path            TEXT,
    plate_crop_path      TEXT,
    sharpness_score      REAL,

    resolution_status    TEXT     NOT NULL DEFAULT 'pending'
                                  CHECK (resolution_status IN
                                  ('pending','matched','ambiguous','new_vehicle')),
    match_method         TEXT     CHECK (match_method IS NULL OR match_method IN
                                  ('PLATE_EXACT','PLATE_FUZZY','VISUAL',
                                   'MANUAL','NEW')),
    match_score          REAL     CHECK (match_score IS NULL OR
                                         match_score BETWEEN 0 AND 1),

    created_at           TEXT     NOT NULL,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL,
    FOREIGN KEY (camera_id)  REFERENCES cameras(id)  ON DELETE RESTRICT,

    CHECK (last_frame_at >= first_frame_at)
);

CREATE INDEX idx_sightings_vehicle       ON sightings(vehicle_id, first_frame_at);
CREATE INDEX idx_sightings_camera_time   ON sightings(camera_id, first_frame_at DESC);
CREATE INDEX idx_sightings_plate         ON sightings(plate_text_norm)
                                          WHERE plate_text_norm IS NOT NULL;
CREATE INDEX idx_sightings_time          ON sightings(first_frame_at DESC);
CREATE INDEX idx_sightings_status        ON sightings(resolution_status)
                                          WHERE resolution_status IN
                                                ('pending','ambiguous');
CREATE INDEX idx_sightings_index_flag    ON sightings(in_vector_index)
                                          WHERE in_vector_index = 0;
```

**Time columns, and why there are four.**

| Column | Source | Used for |
|---|---|---|
| `first_frame_at` | Worker, frame timestamp | Spatio-temporal gating. The authoritative time. |
| `last_frame_at` | Worker | Dwell duration, tracklet quality |
| `best_frame_at` | Worker | Evidence panel display |
| `received_at` | Backend, server clock | Clock-skew detection |

Gating uses `first_frame_at` because it is when the vehicle actually entered the camera's view. `received_at` exists solely so the backend can compare worker clocks: if `received_at - first_frame_at` diverges by more than 5 s across workers, clocks have drifted and the gate will start producing spurious `TEMPORAL_TOO_FAST` rejections that look exactly like a matching bug. Detecting it costs one subtraction and saves an evening of debugging the wrong component.

**Plate columns.** `plate_text_raw` preserves what OCR actually returned, including junk. `plate_text_norm` is uppercased with separators stripped. `plate_is_valid` records whether the normalised form matches `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$`. Keeping the raw value costs nothing and makes OCR error analysis possible — the difference between `BR01A81234` and `BR01AB1234` is one character and diagnostic of a specific confusion pair.

`plate_bbox` is a JSON string `[x, y, w, h]` relative to the vehicle crop. JSON rather than four columns because it is display-only and never filtered on; four more integer columns to render one rectangle is not worth the width.

**Embedding storage.** `embedding` holds 512 float32 in `BLOB` form. This is the durability layer under the in-memory FAISS index — NFR-R2 requires the index to rebuild on startup, and it rebuilds from this column. `in_vector_index` tracks whether the vector is currently loaded, which makes the startup rebuild resumable and lets a background job repair an inconsistent index without a full reload.

`embedding_dim` is stored explicitly. It is 512 today and would be 2048 if the backbone changed; recording it prevents feeding a mismatched vector into a 512-dimensional index and getting an unhelpful shape error deep inside FAISS.

`ON DELETE RESTRICT` on `camera_id` is deliberate. Deleting a camera that has sightings would silently destroy trajectory history. The database refuses; the application soft-deletes instead.

---

### 3.7 `match_decisions`

Every candidate evaluated during resolution writes a row here — accepted, rejected, and ambiguous alike.

```sql
CREATE TABLE match_decisions (
    id                    TEXT     PRIMARY KEY NOT NULL,
    sighting_id           TEXT     NOT NULL,
    candidate_vehicle_id  TEXT,
    candidate_sighting_id TEXT,

    tier                  TEXT     NOT NULL CHECK (tier IN ('plate','visual')),
    outcome               TEXT     NOT NULL CHECK (outcome IN
                                   ('accepted','rejected','ambiguous','superseded')),

    visual_score          REAL     CHECK (visual_score IS NULL OR
                                          visual_score BETWEEN -1 AND 1),
    plate_score           REAL     CHECK (plate_score IS NULL OR
                                          plate_score BETWEEN 0 AND 1),
    temporal_score        REAL     CHECK (temporal_score IS NULL OR
                                          temporal_score BETWEEN 0 AND 1),
    fused_score           REAL     CHECK (fused_score IS NULL OR
                                          fused_score BETWEEN 0 AND 1),
    runner_up_score       REAL,

    gate_passed           INTEGER  NOT NULL DEFAULT 0
                                   CHECK (gate_passed IN (0,1)),
    rejection_reason      TEXT     CHECK (rejection_reason IS NULL OR
                                   rejection_reason IN
                                   ('TEMPORAL_TOO_FAST','TEMPORAL_EXPIRED',
                                    'NO_PATH','SAME_CAMERA_TOO_SOON',
                                    'BELOW_THRESHOLD','AMBIGUOUS_MARGIN',
                                    'OPERATOR_REJECTED','CLASS_MISMATCH')),

    elapsed_seconds       INTEGER,
    min_transit_seconds   INTEGER,
    max_transit_seconds   INTEGER,
    path_distance_m       REAL,
    path_camera_codes     TEXT,

    review_status         TEXT     NOT NULL DEFAULT 'auto'
                                   CHECK (review_status IN
                                   ('auto','confirmed','rejected')),
    decided_by_user_id    TEXT,
    decided_at            TEXT,

    created_at            TEXT     NOT NULL,

    FOREIGN KEY (sighting_id)           REFERENCES sightings(id) ON DELETE CASCADE,
    FOREIGN KEY (candidate_vehicle_id)  REFERENCES vehicles(id)  ON DELETE CASCADE,
    FOREIGN KEY (candidate_sighting_id) REFERENCES sightings(id) ON DELETE SET NULL,
    FOREIGN KEY (decided_by_user_id)    REFERENCES users(id)     ON DELETE SET NULL
);

CREATE INDEX idx_decisions_sighting ON match_decisions(sighting_id, fused_score DESC);
CREATE INDEX idx_decisions_vehicle  ON match_decisions(candidate_vehicle_id);
CREATE INDEX idx_decisions_review   ON match_decisions(review_status, created_at DESC)
                                     WHERE review_status IN ('auto','confirmed');
CREATE INDEX idx_decisions_outcome  ON match_decisions(outcome, created_at DESC);
CREATE INDEX idx_decisions_reason   ON match_decisions(rejection_reason)
                                     WHERE rejection_reason IS NOT NULL;
```

**Why rejections are persisted.** Storing only accepted matches would be smaller and simpler and would make three things impossible:

1. The "also considered" block in the evidence panel — the interface element that turns the system from a black box into something an operator can defend.
2. The `match.rejected` WebSocket broadcast, which lets the demo show the gate working live rather than asserting that it does.
3. The ablation in `prd.md` §7.1 — run with the gate off, run with it on, compare the false-merge rate. That study is computed by counting rows in this table grouped by `rejection_reason`. Without the rows there is no study, and the ablation is the strongest slide in the deck.

`path_camera_codes` is a JSON array of the camera codes along the shortest path used for gating: `["CAM-01","CAM-02","CAM-04"]`. Displayed in the evidence panel so the operator can see the assumed route, and invaluable when a rejection looks wrong — usually the path is wrong, not the timing.

`runner_up_score` is stored on the accepted decision so the margin is recoverable later without re-running the search. `AMBIGUOUS_MARGIN` rejections are exactly the "White Maruti" case, and counting them tells you how often the system correctly refused to guess.

`review_status` distinguishes automatic decisions from human ones. `outcome` is what the system concluded; `review_status` is what a person did about it. Conflating them would lose the ability to measure how often operators disagree with the matcher — a number worth reporting.

---

### 3.8 `audit_logs`

```sql
CREATE TABLE audit_logs (
    id           TEXT    PRIMARY KEY NOT NULL,
    user_id      TEXT,
    action       TEXT    NOT NULL CHECK (action IN (
                         'LOGIN_SUCCESS','LOGIN_FAILURE','LOGOUT',
                         'SEARCH_PLATE','SEARCH_PARTIAL','SEARCH_TIME',
                         'VIEW_TRAJECTORY','VIEW_CROP','EXPORT',
                         'CONFIRM_MATCH','REJECT_MATCH','MERGE_VEHICLES',
                         'SPLIT_VEHICLE','CREATE_CAMERA','UPDATE_CAMERA',
                         'DELETE_CAMERA','CREATE_EDGE','UPDATE_EDGE',
                         'DELETE_EDGE','RESET_DEMO','SECURITY')),
    entity_type  TEXT,
    entity_id    TEXT,
    detail       TEXT,
    ip_address   TEXT,
    user_agent   TEXT,
    created_at   TEXT    NOT NULL,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX idx_audit_user   ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at DESC);
CREATE INDEX idx_audit_time   ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
```

`user_id` is nullable so system-generated entries have somewhere to live, and `ON DELETE RESTRICT` prevents deleting a user whose actions are on record — an audit log with the actor removed is not an audit log.

`detail` is a JSON string of action-specific context: the plate searched, the vehicle IDs merged, the camera code created. Free-form because the shape differs per action and a normalised schema for it would be a table per action type.

Every search and every trajectory view is logged. Vehicle movement is personal data (NFR-PR2), and "who looked up which vehicle, and when" is precisely the accountability question a data-protection authority asks. This table is a small amount of code and a disproportionately strong answer to a judge's privacy question.

---

## 4. SQLModel Definitions

Shortened to the shape that matters. Full definitions live in `backend/app/models/`.

```python
# backend/app/models/base.py
from datetime import datetime, timezone
from uuid import uuid4

def new_id() -> str:
    return str(uuid4())

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
```

```python
# backend/app/models/camera.py
from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import new_id, utcnow

class Camera(SQLModel, table=True):
    __tablename__ = "cameras"

    id: str = Field(default_factory=new_id, primary_key=True)
    code: str = Field(index=True, unique=True, max_length=32)
    name: str
    location_label: Optional[str] = None
    latitude: float
    longitude: float
    heading_deg: Optional[float] = None
    stream_uri: Optional[str] = None
    resolution_w: Optional[int] = None
    resolution_h: Optional[int] = None
    is_active: bool = Field(default=True)
    last_seen_at: Optional[str] = None
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
```

```python
# backend/app/models/camera_edge.py
class CameraEdge(SQLModel, table=True):
    __tablename__ = "camera_edges"

    id: str = Field(default_factory=new_id, primary_key=True)
    from_camera_id: str = Field(foreign_key="cameras.id", index=True)
    to_camera_id:   str = Field(foreign_key="cameras.id", index=True)
    distance_m: float
    min_transit_seconds: int
    max_transit_seconds: int
    is_bidirectional: bool = Field(default=True)
    road_name: Optional[str] = None
    is_estimated: bool = Field(default=True)
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
```

```python
# backend/app/models/sighting.py
class Sighting(SQLModel, table=True):
    __tablename__ = "sightings"

    id: str = Field(default_factory=new_id, primary_key=True)
    vehicle_id: Optional[str] = Field(default=None, foreign_key="vehicles.id", index=True)
    camera_id:  str = Field(foreign_key="cameras.id", index=True)
    local_track_id: int

    first_frame_at: str = Field(index=True)
    last_frame_at:  str
    best_frame_at:  str
    received_at:    str
    frame_count:    int

    bbox_x: int; bbox_y: int; bbox_w: int; bbox_h: int
    detection_confidence: float
    vehicle_class: str

    plate_text_raw:  Optional[str] = None
    plate_text_norm: Optional[str] = Field(default=None, index=True)
    plate_confidence: Optional[float] = None
    plate_is_valid: bool = Field(default=False)
    plate_bbox: Optional[str] = None

    embedding: Optional[bytes] = None
    embedding_dim: int = Field(default=512)
    in_vector_index: bool = Field(default=False)

    crop_path: Optional[str] = None
    plate_crop_path: Optional[str] = None
    sharpness_score: Optional[float] = None

    resolution_status: str = Field(default="pending")
    match_method: Optional[str] = None
    match_score: Optional[float] = None

    created_at: str = Field(default_factory=utcnow)
```

Embedding conversion helpers, kept in one place so no other module reinvents the byte layout:

```python
# backend/app/services/vector_index.py
import numpy as np

def encode_embedding(vec: np.ndarray) -> bytes:
    """L2-normalise, cast to float32, return contiguous bytes."""
    v = np.asarray(vec, dtype=np.float32).ravel()
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return np.ascontiguousarray(v).tobytes()

def decode_embedding(blob: bytes, dim: int = 512) -> np.ndarray:
    v = np.frombuffer(blob, dtype=np.float32)
    if v.size != dim:
        raise ValueError(f"Embedding dimension mismatch: got {v.size}, expected {dim}")
    return v
```

Normalisation happens on write, exactly once, in `encode_embedding`. Every vector in the database and in FAISS is therefore unit-length, and `IndexFlatIP` inner product equals cosine similarity with no further work. A vector normalised twice, or not at all, produces similarity scores that are subtly wrong and very hard to notice.

---

## 5. Migrations

Alembic from the first commit, even though `SQLModel.metadata.create_all()` would work initially.

```
alembic/versions/
  0001_initial_schema.py      users, refresh_tokens, cameras, camera_edges
  0002_vehicles_sightings.py  vehicles, sightings, indexes
  0003_match_decisions.py     match_decisions, audit_logs
```

Reason: four people are building this simultaneously. When one adds a column and another pulls, `create_all` silently does nothing to the existing file and the second developer gets a runtime `no such column` error. Alembic makes that a one-command fix. Three migrations set up in Phase 0 costs about twenty minutes and prevents a whole category of "it works on my machine."

Foreign key enforcement must be enabled per connection:

```python
# backend/app/db/session.py
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
```

Without `foreign_keys=ON`, every `ON DELETE` rule in this document is inert. This is the single most commonly missed line in a SQLite project.

---

## 6. Seed Data

`backend/scripts/seed_cameras.py` creates a demo topology. Coordinates below are Patna; replace them with the locations the demo footage was actually shot at, or every trajectory will draw in the wrong place.

```python
CAMERAS = [
    ("CAM-01", "Gandhi Maidan North",  25.6127, 85.1440),
    ("CAM-02", "Ashok Rajpath East",   25.6198, 85.1712),
    ("CAM-03", "Bailey Road Junction", 25.6093, 85.1102),
    ("CAM-04", "Boring Road Crossing", 25.6180, 85.1234),
    ("CAM-05", "Patna Junction Approach", 25.6015, 85.1372),
]

EDGES = [
    # from,     to,       distance_m, min_s, max_s, bidirectional
    ("CAM-01", "CAM-02",  3400,  153, 1530, True),
    ("CAM-01", "CAM-04",  2100,   95,  945, True),
    ("CAM-04", "CAM-03",  1600,   72,  720, True),
    ("CAM-01", "CAM-05",  1800,   81,  810, True),
    ("CAM-05", "CAM-03",  3100,  140, 1395, True),
]
```

The topology deliberately contains a **non-adjacent pair**: `CAM-02` and `CAM-03` have no direct edge, so a vehicle appearing at both must be routed through `CAM-01` or `CAM-04`, and the transit windows sum along the path. This is the case that demonstrates graph traversal rather than a simple pairwise lookup, and it should be the pair used in the demo.

---

## 7. Retention

`backend/scripts/purge_expired.py`, run manually or on a schedule:

1. Delete `sightings` where `first_frame_at < now - RETENTION_DAYS` (default 30). Cascades to `match_decisions`.
2. Delete orphaned crop files under `CROP_STORAGE_PATH`.
3. Delete `vehicles` with `sighting_count = 0` after the cascade.
4. Delete `refresh_tokens` past `expires_at`.
5. **Retain `audit_logs` indefinitely.** The point of an audit log is that it outlives the data it describes.

Retention is the concrete implementation of NFR-PR3 and is worth one slide. "We delete movement data after 30 days by default, and keep only the record of who accessed it" is a materially stronger privacy position than most surveillance-adjacent systems can state, and it costs one script.
