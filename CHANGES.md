# CHANGES.md — Session changelog for Marg (SIH26127)

All modifications made across Claude Code sessions. Use this to understand what was changed, why, and what state each component is in.

Last updated: 2026-09-04

---

## 1. Environment setup

### Python environments
- **Backend**: Python 3.14, venv at `backend/venv/`. Has FastAPI, SQLModel, uvicorn, etc.
- **ML pipeline**: System Python 3.12 at `C:\Users\BIT\AppData\Local\Programs\Python\Python312\python.exe`. Has PyTorch, ultralytics, easyocr, cv2, etc.
- **Critical**: The backend spawns ML pipeline as a subprocess using Python 3.12 (not the backend's own 3.14 which lacks ML deps). This is hardcoded in `backend/app/api/v1/upload.py`.

### Dependencies installed into Python 3.12 (not in requirements.txt)
- `easyocr`
- `pydantic`
- `pydantic-settings`
- `httpx`
- `lap` (auto-installed by ultralytics on first run, needed by ByteTrack)

### Backend dependency fix
- `backend/requirements.txt`: Changed `pytest==9.1.1` to `pytest==8.3.5` (version conflict with `pytest-asyncio==0.24.0`)

---

## 2. ML Pipeline fixes

### `ml-pipeline/src/osnet.py`
**Problem**: `init_pretrained_weights()` imported `gdown` at the top of the function (line 448), but `gdown` is not installed. The import crashed even when weights were already cached locally.

**Fix**: Moved `import gdown` inside the `if not os.path.exists(cached_file):` block so it only imports when a download is actually needed.

```python
# Before (crashed):
def init_pretrained_weights(model, key=''):
    import gdown  # always imported, always crashed

# After (lazy import):
def init_pretrained_weights(model, key=''):
    ...
    if not os.path.exists(cached_file):
        import gdown  # only when download needed
        gdown.download(...)
```

### `ml-pipeline/src/embedder.py`
**Problem**: OSNet weights exist at `ml-pipeline/models/osnet_x1_0_imagenet.pth` but `osnet_x1_0(pretrained=True)` looks for them at `~/.cache/torch/checkpoints/osnet_x1_0_imagenet.pth`. The file wasn't there, so `init_pretrained_weights` tried to download via gdown.

**Fix**: Added `_ensure_cached_weights()` static method that copies the local weights file to the torch cache directory before building the model. Also added `import shutil`.

```python
@staticmethod
def _ensure_cached_weights() -> None:
    cache_path = osnet_checkpoint_path()
    if cache_path.is_file():
        return
    local_weights = Path(__file__).resolve().parent.parent / "models" / OSNET_CHECKPOINT_FILENAME
    if local_weights.is_file():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_weights, cache_path)
```

Called in `__init__` before `osnet_x1_0(pretrained=True)`.

### `ml-pipeline/src/ingest_client.py` (prior session)
- Changed `camera_id` to `camera_code` key in the POST payload to match backend schema.

### `ml-pipeline/scripts/run_worker.py` (prior session)
- Fixed `best_shots` parameter passing to avoid double `select_best_shots` call.

---

## 3. Backend changes

### `backend/app/api/v1/upload.py` — NEW FILE
Video upload and pipeline execution endpoint. Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/upload/video` | Upload video + camera_code, saves file, spawns ML pipeline subprocess |
| GET | `/api/v1/upload/status/{job_id}` | Poll job status (processing/completed/failed) |
| GET | `/api/v1/upload/status/{job_id}/logs` | Get pipeline stdout |
| GET | `/api/v1/upload/serve/{filename}` | Serve uploaded video file for frontend playback |

Key details:
- Uses Python 3.12 path (`C:\Users\BIT\AppData\Local\Programs\Python\Python312\python.exe`) to spawn pipeline
- `UPLOAD_DIR` resolved to absolute path via `.resolve()` (fixes path issue when subprocess runs from ml-pipeline cwd)
- Jobs tracked in-memory `_jobs` dict (lost on restart)
- Pipeline env vars loaded from `ml-pipeline/.env` + backend's `INGEST_API_KEY`

### `backend/app/main.py`
- Added `from app.api.v1 import upload` and `app.include_router(upload.router, prefix=API_V1_PREFIX)`

### `backend/app/api/v1/cameras.py`
- Added `last_seen_at`, `created_at`, `updated_at` to `CameraRead` schema to match frontend TypeScript types.

### `backend/app/schemas/vehicle.py`
- Added `plate_confidence`, `merged_into_id`, `created_at`, `updated_at` to `VehicleRead`
- Added `display_ref`, `canonical_plate` to `TrajectoryRead`

### `backend/app/api/v1/vehicles.py`
- Updated `get_trajectory` to pass `display_ref` and `canonical_plate` to `TrajectoryRead` response.

### `backend/scripts/seed_cameras.py`
- Changed from 5 cameras to 3 cameras (Patna locations):
  - CAM-01: Dak Bungalow Chauraha (25.6093, 85.1376)
  - CAM-02: Income Tax Golambar (25.6138, 85.1322)
  - CAM-03: Gandhi Maidan Gate 1 (25.6205, 85.1441)
- 3 bidirectional edges connecting all pairs

### `backend/app/services/identity_resolver.py` (prior session)
- Fixed `_new_identity()` method
- Added `_refresh_plate_and_class()` method

### `backend/app/repositories/vehicle_repo.py` (prior session)
- Fixed `first_seen_at` always-update bug

---

## 4. Frontend changes

### `frontend/src/stores/uploadStore.ts` — NEW FILE
Zustand store for managing multi-video upload state. Tracks per-camera: file, jobId, status (queued/uploading/processing/completed/failed), videoUrl. Used by UploadPage to manage uploads and by LiveWallPage to get video URLs for camera tiles.

### `frontend/src/pages/UploadPage.tsx` — NEW FILE (rewritten)
Multi-video upload page with:
- Add multiple videos, each assigned to a different camera
- Camera selector auto-advances to next available camera
- Drag-and-drop + click-to-browse
- "Run" button fires all pipelines in parallel
- Per-job status polling (2s interval)
- Status badges per video (queued/uploading/processing/completed/failed)
- "View live wall" and "View simulation" buttons on completion
- Uses zustand store to persist video URLs for Live Wall playback

### `frontend/src/pages/SimulationPage.tsx` — NEW FILE
Map-based trajectory simulation:
- 3 camera markers at Patna locations
- 3 animated vehicle routes (White Sedan, Yellow Auto, Blue Truck)
- Vehicles move along predefined waypoint paths between cameras
- Staggered start (2s between each vehicle)
- Different durations per route (12s, 18s, 22s)
- Trail polylines draw behind each vehicle
- Play/Pause/Reset/Replay controls
- Route legend with per-vehicle progress %
- Recenter button
- Uses `requestAnimationFrame` for smooth 60fps animation
- Uses standard (not dark-filtered) OSM tiles

### `frontend/src/components/camera/CameraTile.tsx` — MODIFIED
- Added `videoUrl` prop
- When `videoUrl` is provided, renders a `<video>` element (muted, looping, autoplay) instead of the placeholder grid
- Video plays the uploaded file served from backend's `/api/v1/upload/serve/{filename}`

### `frontend/src/pages/LiveWallPage.tsx` — MODIFIED
- Imports `useUploadStore` to get video URLs per camera
- Passes `videoUrl={getVideoUrl(camera.code)}` to each `CameraTile`

### `frontend/src/components/common/TopBar.tsx` — MODIFIED
- Added "Simulation" nav tab with Route icon linking to `/sim`
- Added "Upload" nav tab with Upload icon linking to `/upload`

### `frontend/src/App.tsx` — MODIFIED
- Added routes: `/upload` -> `UploadPage`, `/sim` -> `SimulationPage`
- Imports for both new pages

### `frontend/src/mocks/mockData.ts` — MODIFIED
- Reduced from 4 mock cameras to 3 (removed CAM-04 Kargil Chowk)

---

## 5. Database state

- SQLite at `backend/data/marg.db` (WAL mode)
- Seeded with 3 cameras + 3 edges
- Contains sightings from test uploads (can be reset with `scripts/reset_demo.sh` or by deleting the .db file and re-running `seed_cameras.py`)

---

## 6. Known issues / incomplete items

### Pipeline produces 0 sightings for videos without vehicles
- YOLO filters for COCO classes 2 (car), 3 (motorcycle), 5 (bus), 7 (truck)
- Videos with only people produce 0 detections = 0 sightings
- This is correct behavior, not a bug

### Cross-camera matching needs real multi-camera footage
- Uploading the same video to different cameras creates sightings with near-identical timestamps
- The spatio-temporal gate rejects these as TEMPORAL_TOO_FAST (correct behavior — same video = same time = can't travel between cameras)
- Real demo needs videos filmed at different cameras with realistic time gaps

### Simulation page map rendering
- Uses standard OSM tiles (not dark-filtered) — requires internet for tile loading
- For offline demo, tiles need to be pre-downloaded to `frontend/public/tiles/`
- Map container uses absolute positioning wrapper for Leaflet height calculation

### Backend auto-reload on OneDrive paths
- uvicorn `--reload` file watcher doesn't reliably detect changes on OneDrive-synced paths
- Workaround: manually restart the backend after code changes (`taskkill` + re-run uvicorn)

### No plate reads on test video
- EasyOCR didn't find plates in the test car video (likely angle/distance)
- Plate matching (Tier 1) untested with real data

---

## 7. How to run

```bash
# 1. Backend
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_cameras.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 2. Frontend
cd frontend
pnpm install
pnpm dev

# 3. ML Pipeline (runs via upload endpoint, but to test manually):
cd ml-pipeline
C:\Users\BIT\AppData\Local\Programs\Python\Python312\python.exe scripts/run_worker.py --video <path> --camera-id CAM-01 --post

# 4. Full flow
# Go to http://localhost:5173/upload
# Add videos, assign to cameras, click Run
# Go to Live Wall to see videos playing + sightings appearing
# Go to Simulation to see animated vehicle routes on map
```

---

## 8. File tree of changes

```
sih-tracker/
  .gitignore                              MODIFIED — added video formats, models, uploads, DB, IDE
  CHANGES.md                              NEW — this file
  backend/
    app/
      api/v1/
        upload.py                         NEW — upload + pipeline + video serving endpoints
        cameras.py                        MODIFIED — schema alignment
        vehicles.py                       MODIFIED — trajectory response fields
      main.py                             MODIFIED — registered upload router
      schemas/vehicle.py                  MODIFIED — schema alignment
      services/identity_resolver.py       MODIFIED — fixed _new_identity
      repositories/vehicle_repo.py        MODIFIED — fixed first_seen_at
    requirements.txt                      MODIFIED — pytest 9.1.1 -> 8.3.5
    scripts/seed_cameras.py               MODIFIED — 5 cameras -> 3
  ml-pipeline/
    src/
      osnet.py                            MODIFIED — lazy gdown import
      embedder.py                         MODIFIED — _ensure_cached_weights + shutil
      ingest_client.py                    MODIFIED — camera_id -> camera_code
    scripts/run_worker.py                 MODIFIED — best_shots fix
  frontend/
    src/
      stores/uploadStore.ts               NEW — zustand store for upload state
      pages/UploadPage.tsx                NEW — multi-video upload page
      pages/SimulationPage.tsx            NEW — animated trajectory simulation
      pages/LiveWallPage.tsx              MODIFIED — video playback in camera tiles
      components/camera/CameraTile.tsx    MODIFIED — added videoUrl prop + <video> element
      components/common/TopBar.tsx        MODIFIED — added Simulation + Upload nav tabs
      App.tsx                             MODIFIED — added /upload and /sim routes
      mocks/mockData.ts                   MODIFIED — 4 cameras -> 3
```

---

## 9. Environment-specific values (hardcoded, change on new machine)

| Value | Location | Purpose |
|-------|----------|---------|
| `C:\Users\BIT\AppData\Local\Programs\Python\Python312\python.exe` | `backend/app/api/v1/upload.py` lines 72-73 | Python 3.12 path for ML pipeline subprocess |
| `dev-ingest-key-not-for-production` | `backend/.env` and `ml-pipeline/.env` | Ingest API key (must match) |
| Patna coordinates (25.60-25.62, 85.13-85.14) | `seed_cameras.py`, `mockData.ts`, `SimulationPage.tsx` | Camera locations |
