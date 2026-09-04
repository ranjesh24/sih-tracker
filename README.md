# Marg (मार्ग) — SIH26127

> **City-Wide Multi-Camera Vehicle Trajectory Reconstruction System**  
> Smart India Hackathon Prototype

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/Frontend-React_19-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Bundler-Vite-646CFF?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![PyTorch](https://img.shields.io/badge/Deep_Learning-PyTorch-EE4C2C?style=flat&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![YOLOv8](https://img.shields.io/badge/Detection-YOLOv8s-00FFFF?style=flat)](https://ultralytics.com/)
[![OSNet](https://img.shields.io/badge/Re--ID-OSNet_x1.0-FF6F00?style=flat)](https://github.com/KaiyangZhou/deep-person-reid)
[![Leaflet](https://img.shields.io/badge/Maps-Leaflet_OSM-199900?style=flat&logo=leaflet&logoColor=white)](https://leafletjs.com/)

---

## 1. Overview

**Marg** (मार्ग) reconstructs multi-camera vehicle trajectories across non-overlapping urban camera networks. Unlike traditional systems that rely purely on license plate recognition (which fails under occlusions, bad weather, motion blur, or missing plates), Marg fuses three tiers of evidence:

1. **Tier 1 — License Plate OCR**: Normalized Indian plate format validation and high-confidence exact/fuzzy matching (EasyOCR + RapidFuzz).
2. **Tier 2 — Spatio-Temporal Feasibility Gating**: Physical road graph topology (NetworkX) with road winding factors, minimum/maximum plausible transit speeds, and directionality. Candidates that are physically impossible to reach in the elapsed time are rejected early (e.g. `TEMPORAL_TOO_FAST`, `NO_PATH`).
3. **Tier 3 — Deep Visual Re-Identification**: 512-dimensional appearance feature embeddings (OSNet x1.0) indexed in FAISS (`IndexFlatIP`), scored exclusively against the spatio-temporally feasible candidate set.

---

## 2. System Architecture

```
[ CCTV Video Feeds / Uploads ]
              │
              ▼
    ┌───────────────────┐
    │    ML PIPELINE    │
    │  - YOLOv8s Det    │
    │  - ByteTrack      │
    │  - EasyOCR        │
    │  - OSNet Embedder │
    └─────────┬─────────┘
              │ POST /api/v1/ingest/sightings (with X-Ingest-Key)
              ▼
    ┌───────────────────┐
    │  FASTAPI BACKEND  │
    │  - SQLite / WAL   │
    │  - NetworkX Graph │ ◄── Patna Camera Topology & Road Edges
    │  - FAISS 512-dim  │ ◄── In-Memory Vector Index
    │  - Identity Res.  │ ◄── 3-Tier Fusion & Gate Validator
    └─────────┬─────────┘
              │ REST & Polling API
              ▼
    ┌───────────────────┐
    │ FRONTEND CONSOLE  │
    │  - Live Wall      │ ◄── Multi-tile live video playback & stream
    │  - Trajectory Map │ ◄── Multi-hop Leaflet map reconstruction
    │  - Evidence Drawer│ ◄── Rejection gate audit & score explanation
    │  - Simulation     │ ◄── 60fps animated Patna vehicle routes
    │  - Video Upload   │ ◄── Multi-camera parallel ingestion
    └───────────────────┘
```

---

## 3. Core Features

### 🖥️ 1. Live Camera Wall (`/`)
* Grid of camera streams with synchronized live video playback served directly from backend uploads.
* Tile flash micro-animations triggered on new detection events.
* Real-time sighting event feed with plate badges, confidence metrics, and quick navigation.

### 🗺️ 2. Trajectory Reconstruction Map (`/vehicles/:id`)
* Interactive Leaflet dark-mode map plotting chronologically ordered sightings across camera nodes.
* Dynamic polyline connectors with direction arrows and transit durations.
* Timeline drawer detailing exact timestamps, camera coordinates, and visual crops.

### 🔍 3. Spatio-Temporal Evidence Panel (`/evidence/:id`)
* Complete audit trail explaining why candidates were accepted or rejected.
* Visualizes spatial-temporal gates:
  * `TEMPORAL_TOO_FAST`: Vehicle appeared at next camera faster than maximum plausible road speed.
  * `TEMPORAL_EXPIRED`: Elapsed time exceeds the lookback threshold.
  * `NO_PATH`: No valid road graph edge connects the two cameras.
  * `SAME_CAMERA_TOO_SOON`: Duplicate detection within the minimum revisit interval.
* Multi-attribute visual breakdown: crop comparisons, normalized score formulas, and ambiguity margins.

### 📤 4. Multi-Video Upload & Processing (`/upload`)
* Drag-and-drop or select multiple video files simultaneously.
* Automatic assignment to available camera nodes (`CAM-01`, `CAM-02`, `CAM-03`).
* Parallel execution of ML workers with real-time job status polling and persistent log captures.

### 🚗 5. Trajectory Simulation (`/sim`)
* Interactive simulation on Patna coordinates (Dak Bungalow, Income Tax Golambar, Gandhi Maidan).
* Multi-vehicle animated waypoint routes (White Sedan, Yellow Auto, Blue Truck) at 60fps using `requestAnimationFrame`.
* Trail polylines, playback speed controls, and vehicle progress tracking.

---

## 4. Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Leaflet, React-Leaflet, Zustand, Lucide React, Axios |
| **Backend** | FastAPI, Python 3.11, SQLModel, SQLAlchemy, SQLite (WAL mode), FAISS-CPU, NetworkX, RapidFuzz, Uvicorn |
| **ML & Vision** | PyTorch, Ultralytics YOLOv8s, ByteTrack, EasyOCR, OSNet x1.0, OpenCV |
| **Design System** | Tailored dark control-room theme (`#0E1012`), Indian road sign semantics (Sign Green, Amber, Oxide Red) |

---

## 5. Prerequisites & Installation

### Prerequisites
* **Node.js**: v18+ and `npm`
* **Python**: 3.11+
* **Microsoft Visual C++ Redistributable (x64)** (Required for PyTorch native DLLs on Windows)

---

### Step 1: Clone Repository
```bash
git clone https://github.com/ranjesh24/sih-tracker.git
cd sih-tracker
```

---

### Step 2: Backend Setup

1. **Navigate to the backend directory and activate the virtual environment**:
   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1   # Windows PowerShell
   # source venv/bin/activate    # Linux / macOS
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install python-multipart
   ```

3. **Configure environment variables**:
   Create `backend/.env` from `.env.example`:
   ```ini
   ENVIRONMENT=development
   DATABASE_URL=sqlite:///./data/marg.db
   INGEST_API_KEY=dev-ingest-key-not-for-production
   CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174
   EMBEDDING_DIM=512
   VISUAL_FLOOR=0.55
   AMBIGUITY_MARGIN=0.05
   FAISS_TOP_K=50
   LOOKBACK_WINDOW_SECONDS=3600
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

4. **Initialize Database & Seed Patna Cameras**:
   ```bash
   python scripts/seed_cameras.py
   ```

5. **Start Backend Server**:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
   ```
   *Health Check*: `http://127.0.0.1:8000/api/v1/system/health`

---

### Step 3: ML Pipeline Configuration

1. **Navigate to the ML pipeline directory**:
   ```bash
   cd ../ml-pipeline
   ```

2. **Create `ml-pipeline/.env`**:
   ```ini
   BACKEND_BASE_URL=http://localhost:8000
   INGEST_API_KEY=dev-ingest-key-not-for-production
   DEVICE=cpu
   MODELS_DIR_PATH=./models
   PLAYBACK_FPS=15.0
   FRAME_STRIDE=2
   YOLO_MODEL_PATH=./models/yolov8s.pt
   ```

3. **Install ML dependencies (if not already installed in the virtual environment)**:
   ```bash
   pip install -r requirements.txt
   ```
   *Pre-trained models (`models/yolov8s.pt` and `models/osnet_x1_0_imagenet.pth`) are included in `ml-pipeline/models/`.*

---

### Step 4: Frontend Console Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd ../frontend
   npm install
   ```

2. **Start Frontend Dev Server**:
   ```bash
   npm run dev
   ```
   *Console UI will be running at*: `http://localhost:5173/`

---

## 6. API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/system/health` | Service health, FAISS index size, active camera count |
| `GET` | `/api/v1/cameras` | List configured cameras and coordinates |
| `POST` | `/api/v1/upload/video` | Upload video file and spawn asynchronous ML worker |
| `GET` | `/api/v1/upload/status/{job_id}` | Poll upload and worker processing status |
| `GET` | `/api/v1/upload/serve/{filename}` | Stream uploaded video file for frontend playback |
| `POST` | `/api/v1/ingest/sightings` | Ingest vehicle detection tracklet with embedding |
| `GET` | `/api/v1/sightings` | List recent sightings with pagination |
| `GET` | `/api/v1/vehicles` | List unique resolved vehicles |
| `GET` | `/api/v1/vehicles/{id}/trajectory` | Reconstructed spatio-temporal path across camera nodes |
| `GET` | `/api/v1/vehicles/{id}/evidence` | Audit log of match and gate rejection decisions |

---

## 7. Demo Walkthrough

1. **Upload Feeds**: Open `http://localhost:5173/upload`, upload video clips for `CAM-01`, `CAM-02`, and `CAM-03`, then click **Run**.
2. **Monitor Live Wall**: Click **View live wall** (`/`) to observe real video loops in camera tiles and newly ingested vehicle events streaming into the live feed.
3. **Inspect Vehicle Trajectory**: Click on any vehicle reference badge (e.g. `#CBD8`) to inspect its spatial journey across Patna on the Leaflet map.
4. **Audit Evidence**: Click **View Evidence** to inspect the 3-tier resolver decisions, visual similarity metrics, and spatio-temporal physics validation.
5. **Run Simulation**: Go to `http://localhost:5173/sim` to watch simulated animated multi-hop routes with speed and progress controls.

---

## 8. License

Developed for the **Smart India Hackathon (SIH26127)**.
