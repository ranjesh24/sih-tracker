# implementationplan.md — Implementation Plan

**Project:** Marg (SIH26127)
**Version:** 1.0
**Team:** 4 people
**Window:** 6 days, Monday through Saturday, presenting Saturday
**Companion docs:** `tracker.md`, `rules.md`

---

## 1. How to Read This

Five phases, mapped onto six days. Each phase lists its prerequisites, its parallel work streams, and a **verification gate** — a concrete, runnable check that must pass before the next phase starts.

The gates are the important part. On a six-day build the failure mode is not writing too little code; it is writing four days of code that has never been run end to end and discovering on Friday that the pieces do not fit. A gate that takes ten minutes to run on Tuesday evening saves a day on Friday.

**One rule above all others: the demo path is built first and stays working.** Anything that is not on the path from "start the pipeline" to "show a trajectory with a bridged plate failure" is deferred until that path runs. Features that are not demonstrated do not exist as far as the evaluation is concerned.

### Roles

Named by responsibility, not by person. Assign on Day 1 and keep the assignment — rotating people through unfamiliar subsystems mid-week costs more than it balances.

| Role | Owns | Primary directories |
|---|---|---|
| **V** — Vision | Detection, tracking, best-shot, OCR, embeddings | `ml-pipeline/` |
| **B** — Backend | API, resolver, gate, FAISS, WebSocket, schema | `backend/` |
| **F** — Frontend | React app, map, camera wall, evidence panel | `frontend/` |
| **D** — Data & Demo | Footage, topology, ground truth, evaluation, deck | `datasets/`, `scripts/`, presentation |

V and B are the critical path. F can build against a mock from Day 1 and is never blocked. D's work is invisible until Day 4 and then becomes the most important thing in the room.

---

## 2. Phase 0 — Foundations

**Day 1, morning. Roughly 4 hours. Everyone.**

Nothing else starts until this is done. A repository that is not set up correctly on Day 1 generates merge conflicts and environment breakage for five days.

### Prerequisites
- Problem statement committed (done — SIH26127).
- Four machines with Python 3.11 and Node 22. At least one with a CUDA GPU.

### Work

**Everyone, together, in the first hour**
- Create the `sih-tracker` repository with the layout from `techspec.md` §8.
- Commit all eight specification documents plus `CLAUDE.md` into `docs/`.
- `.gitignore`: `datasets/`, `**/models/*.pt`, `**/models/*.pth`, `backend/data/`, `.env`, `__pycache__/`, `node_modules/`, `dist/`, `*.db`, `*.db-wal`, `*.db-shm`.
- Branch policy: `main` plus `feat/<role>-<topic>`. No direct pushes to `main`. Squash merge.
- **Directory ownership.** V touches `ml-pipeline/`, B touches `backend/`, F touches `frontend/`, D touches `scripts/` and `datasets/`. Cross-boundary changes go through the owner. This one rule eliminates most merge conflicts on a four-person week.

**V** — `ml-pipeline/`
- Virtualenv, `requirements.txt` with the exact pins from `techspec.md` §2.1.
- `scripts/download_models.py` fetching YOLOv8n, OSNet, and PaddleOCR weights into `models/`.
- Verify CUDA: `python -c "import torch; print(torch.cuda.is_available())"`.

**B** — `backend/`
- Separate virtualenv, `requirements.txt` per `techspec.md` §2.2.
- FastAPI skeleton with `/api/v1/system/health`.
- Alembic initialised. Migrations `0001`, `0002`, `0003` written from `schema.md` §3 and applied.
- The SQLite pragma listener from `schema.md` §5. Verify with `PRAGMA foreign_keys;` returning 1.
- `.env.example` complete.

**F** — `frontend/`
- `pnpm create vite` with the React + TypeScript template, versions pinned per `techspec.md` §2.3.
- Tailwind configured. `styles/tokens.css` populated with every token from `design.md` §4–6.
- Inter and JetBrains Mono woff2 downloaded into `public/fonts/` with `@font-face` declarations. **No CDN link.**
- App shell: TopBar, Sidebar, router with all routes from `appflow.md` §1 rendering placeholders.

**D** — data
- Collect or record footage for 3 to 5 cameras. Real junction footage is best; a phone at two ends of a street, filmed at the same time, works. Public CCTV compilations are an acceptable fallback.
- Trim to 10–20 minutes per camera with overlapping wall-clock windows.
- Author the topology: coordinates per camera, and measured or estimated transit times per edge.
- Set up the presentation skeleton.

### Verification gate 0

Every one must pass. Record the result in `tracker.md`.

```bash
# Backend runs and the database has the full schema
cd backend && uvicorn app.main:app --reload &
curl -s localhost:8000/api/v1/system/health          # → {"status":"ok"}
sqlite3 data/marg.db ".tables"                        # → all 7 tables
sqlite3 data/marg.db "PRAGMA foreign_keys;"           # → 1

# Frontend builds and serves
cd frontend && pnpm build && pnpm dev                 # → localhost:5173, shell renders

# ML environment is real
cd ml-pipeline && python scripts/download_models.py
python -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt'); print('ok')"
python -c "import torchreid, faiss, numpy; print('ok')"

# Footage exists
ls datasets/videos/                                   # → at least 3 files
```

**Offline check — run this now, not on Saturday.** Disconnect from the network entirely and repeat the backend, frontend, and model-load checks. Anything that fails is calling out to the internet and will fail at the venue. Fix it today while it is cheap.

---

## 3. Phase 1 — Data Layer and Authentication

**Day 1 afternoon into Day 2 morning. Roughly 8 hours.**

### Prerequisites
Gate 0 passed.

### Work

**B** — the critical path this phase
- SQLModel models for all seven tables, matching `schema.md` §3 exactly.
- Repository layer: `camera_repo`, `sighting_repo`, `vehicle_repo`. All database access goes through these (NFR-SC2).
- Auth: bcrypt hashing (direct `bcrypt`, no passlib — see `techspec.md` §2.2), JWT issue and verify, refresh rotation with reuse detection.
- `/api/v1/auth/*` — login, refresh, logout, me.
- `deps.py`: `get_current_user`, `require_role`.
- `/api/v1/cameras` and `/api/v1/camera-edges` full CRUD.
- `camera_graph.py`: build a `networkx` graph from `camera_edges`, `shortest_path` weighted by `min_transit_seconds`, transit window summation along a path.
- `spatiotemporal_gate.py` — pure function, no I/O, no database. This makes it trivially testable and it is the module that must be correct.
- Global exception handler emitting the error envelope from `techspec.md` §5.3, with `request_id`.
- Audit logging on auth and camera actions.
- `scripts/seed_users.py`, `scripts/seed_cameras.py`.

**F** — unblocked, working against mocks
- `lib/api.ts`: axios instance, auth interceptor, deduplicated refresh-on-401 (`appflow.md` §6.1 — a module-level promise, not one refresh per failed request).
- `authStore` in Zustand, in memory only.
- Login page, complete, with all error states from `appflow.md` §A1.
- Route guards and role-based redirects.
- UI primitives from `design.md` §7: Button, Input, Badge, Table, Dialog, Skeleton, EmptyState, Toast.
- `frontend/src/mocks/` with fixture data shaped exactly like the API contract, so pages can be built before endpoints exist.

**V** — pipeline foundations
- `frame_source.py`: read MP4, emit frames at `PLAYBACK_FPS` with synthetic wall-clock timestamps offset from a shared epoch so all workers share a timeline.
- `detector.py`: YOLOv8n wrapper filtering to `TARGET_CLASSES`.
- `tracker.py`: ByteTrack, emitting stable local track IDs.
- `tracklet.py`: accumulate frames per track ID; finalise when the track is lost; discard tracklets shorter than `MIN_TRACKLET_FRAMES`.
- Visualise output to a window or an annotated MP4. **Watch the video.** Confirm the boxes are on vehicles and the IDs are stable. Twenty minutes of watching output catches problems that no unit test will.

**D**
- Finish topology measurement; hand coordinates and transit windows to B.
- Begin ground-truth annotation: for 15–20 vehicles that cross two or more cameras, record vehicle, camera, entry time, plate if legible. A spreadsheet is fine. This is what makes the IDF1 number in the deck real rather than asserted.

### Verification gate 1

```bash
# Auth round trip
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"operator@marg.local","password":"..."}' -c cookies.txt
# → 200, access_token in body, refresh cookie set

curl -s -X POST localhost:8000/api/v1/auth/refresh -b cookies.txt
# → 200, new token, old refresh revoked

# Role enforcement
curl -s localhost:8000/api/v1/cameras -H "Authorization: Bearer <viewer token>" \
  -X POST -d '{...}'
# → 403 INSUFFICIENT_ROLE

# Topology loaded and traversable
curl -s localhost:8000/api/v1/camera-edges -H "Authorization: Bearer <token>"
# → 5 edges

pytest backend/tests/unit/test_spatiotemporal_gate.py -v
# → all pass, including: too fast, expired, no path, same camera, multi-hop path
```

The gate test file is not optional and not a formality. Cases required: elapsed below minimum, elapsed above maximum, no path between cameras, same camera within the revisit window, and a two-hop path where the window is the sum of two edges. If any of these is wrong the entire matching system is wrong, and it will present as a mysterious model failure rather than an arithmetic bug.

```bash
# Frontend
# Sign in as each of the three seeded roles; confirm each lands correctly and
# that operator and admin routes redirect for a viewer.
```

```bash
# Pipeline
python ml-pipeline/scripts/run_worker.py --camera CAM-01 --visualize
# → annotated video: boxes on vehicles, stable IDs, tracklets finalising
```

---

## 4. Phase 2 — Core Pipeline and Identity Resolution

**Day 2 afternoon through Day 3. Roughly 14 hours. The heart of the build.**

### Prerequisites
Gate 1 passed. Specifically: the gate function is tested and the topology is loaded.

### Work

**V**
- `best_shot.py`: score each tracklet frame by `area × detection_confidence × laplacian_variance`, keep the maximum, persist the crop.
- `plate_detector.py`: locate the plate within a vehicle crop. Two options — a YOLOv8n fine-tuned on a plate dataset, or PaddleOCR's text detector run on the lower half of the crop. **Start with the second.** It requires no training and it works well enough; fine-tuning a plate detector is a Day 5 improvement if time allows, not a Day 2 dependency.
- `ocr.py`: PaddleOCR recognition, returning text and confidence.
- `normalizer.py`: uppercase, strip separators, validate against `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$`, apply the confusion map. Pure function, unit tested with real OCR failure strings.
- `embedder.py`: OSNet on the best-shot crop, batched, L2-normalised, 512-D output.
- `ingest_client.py`: POST sightings with retry and backoff; fatal exit on a 401 from a bad ingest key.
- `run_all_workers.py`: launch one process per camera, shared timestamp epoch, supervise, restart on crash, heartbeat.

**B**
- `vector_index.py`: FAISS `IndexIDMap2(IndexFlatIP)`, add, search, rebuild from the `sightings.embedding` column at startup.
- `plate_matcher.py`: exact match, then rapidfuzz with the OCR confusion map at edit distance ≤ 1.
- **`identity_resolver.py`** — the algorithm from `techspec.md` §5.6, in full: plate tier, visual tier, ambiguity margin, new identity, and a `MatchDecision` row for every candidate evaluated including rejections.
- `/api/v1/ingest/sightings` and `/batch`, guarded by `X-Ingest-Key` with `compare_digest`, serialised behind a single async lock (FAISS is not safe for concurrent add and search).
- `broadcaster.py` and `/api/v1/ws/events`: connection registry, token validation at handshake, all six message types from `techspec.md` §5.5.
- `/api/v1/vehicles` list and search, `/api/v1/vehicles/{id}/trajectory`, `/api/v1/sightings/{id}`, `/api/v1/sightings/{id}/crop`, `/api/v1/sightings/{id}/candidates`.
- Plate masking in the response serialiser for the `viewer` role.

**F**
- `useLiveEvents` hook: WebSocket with backoff reconnect and gap backfill.
- `ConnectionIndicator`.
- Live wall: camera grid, detection overlay canvas, event feed with distinct styling for `match.rejected`.
- Search page, all three tabs, with the empty states from `appflow.md` §6.6.
- Vehicle detail: Leaflet map, camera markers, confidence-styled polylines, sighting timeline.

**D**
- Complete ground truth for at least 20 cross-camera vehicles.
- `scripts/evaluate_metrics.py`: IDF1, IDP, IDR, MOTA, false-merge rate, gate rejection counts by reason, computed against the ground-truth file.
- Draft the deck through the architecture section.

### Verification gate 2 — the most important gate in the plan

```bash
# End to end, three cameras
./scripts/demo.sh
# → 3 workers start, sightings arrive, resolution runs, events broadcast
```

Then, in the browser:

1. Live wall shows three feeds with detection boxes and a populating event feed.
2. Search a plate that appears in the footage. At least one vehicle returns.
3. Open the vehicle. The trajectory renders as a polyline across two or more cameras.
4. **Find a sighting matched by `VISUAL` where no plate was read.** This is criterion D-2 and the core of the demo. If it does not exist, either the footage has no plate failures — unlikely — or the visual tier is not firing. Diagnose now.
5. **Find a `TEMPORAL_TOO_FAST` rejection.** Query it directly:

```sql
SELECT visual_score, elapsed_seconds, min_transit_seconds, rejection_reason
FROM match_decisions
WHERE rejection_reason = 'TEMPORAL_TOO_FAST'
ORDER BY visual_score DESC LIMIT 5;
```

If this returns nothing, the gate has never rejected anything, which means it is either not wired in or the topology's transit windows are too permissive to constrain anything. **This is the single most likely silent failure in the whole build**, because everything appears to work — trajectories render, matches happen — while the differentiating component sits inert. Verify it explicitly. If necessary, construct the case: take footage from two distant cameras with a visually similar vehicle at each and confirm the rejection fires.

```bash
pytest backend/tests/ -v --cov=app/services
# → ≥ 70% on services/, identity_resolver and gate near 100%

python backend/scripts/evaluate_metrics.py --ground-truth datasets/eval/gt.csv
# → IDF1 printed. Any number is fine today. It needs to exist.
```

**If gate 2 does not pass by the end of Day 3, stop adding features.** Days 4 and 5 become debugging days. A working three-camera demo with a mediocre IDF1 wins a college round; a feature-rich system that crashes during the demo does not.

---

## 5. Phase 3 — Explainability, Review, and Edge Cases

**Day 4. Roughly 8 hours.**

This phase converts a working system into a persuasive one. Everything here exists to answer the question a judge asks after the trajectory renders: "how do you know that is the same car?"

### Prerequisites
Gate 2 passed end to end.

### Work

**F** — the highest-value work of the day
- **Evidence panel**, complete, per `appflow.md` §A4: best-shot crop, plate crop with confidence, component score breakdown, fused score against threshold, transit window, and the "also considered" block listing rejected candidates with their reasons and numbers.
- `MatchExplanation` component. This is the single most important component in the frontend. Build it carefully.
- Confirm and reject actions with optimistic update and rollback.
- Review queue at `/review`: side-by-side candidate crops, three actions.
- Trajectory playback with `prefers-reduced-motion` handling.
- Every empty state and error state from `appflow.md` §6.

**B**
- `/api/v1/match-decisions/{id}/confirm` and `/reject`, with re-resolution on rejection excluding the rejected candidate.
- `/api/v1/match-decisions/ambiguous`.
- `/api/v1/vehicles/{id}/split` and `/api/v1/vehicles/merge`.
- `/api/v1/system/reset-demo` — wipe sightings, vehicles, decisions, crops, and the FAISS index; keep cameras, edges, users, audit log.
- `/api/v1/system/metrics` returning live IDF1, gate rejection counts by reason, and match-method distribution.
- Clock-skew detection and the `system.error` broadcast.

**V**
- Robustness. Every failure path from `appflow.md` §6.4: missing weights, unregistered camera, bad ingest key, video ending cleanly.
- Threshold tuning against the actual footage. Sweep `VISUAL_FLOOR` and the `W_VISUAL`/`W_TEMPORAL` ratio (and `YOLO_CONF_THRESHOLD`), record IDF1 and false-merge rate at each, pick the operating point. Put the sweep table in the deck — it demonstrates method rather than a lucky default.
- `benchmark_pipeline.py` for the FPS figure in NFR-P1.

**D**
- Run the ablation: gate disabled, then enabled, same footage, same ground truth. Record false-merge rate for both. **This is the strongest single slide in the deck.**
- Deck through the results section.
- Write the demo script: exact clicks, exact vehicle, exact plate, in order.

### Verification gate 3

1. Evidence panel shows the full breakdown for a `VISUAL` match on a sighting with no plate.
2. "Also considered" lists at least one rejected candidate with reason and numbers.
3. Confirm restyles the segment; reject splits the trajectory and reassigns; both produce correct toasts.
4. Review queue shows at least one ambiguous case with side-by-side crops.
5. `/system/reset-demo` clears state and the UI empties without a page reload.
6. Every empty state in `appflow.md` §6.6 reachable and correct.
7. Ablation complete, both numbers recorded.
8. Kill a worker mid-run: its tile goes offline, others continue, an error appears, no crash.
9. Kill and restart the backend: the FAISS index rebuilds and existing trajectories still resolve.

---

## 6. Phase 4 — Polish, Rehearsal, Deck

**Day 5 and Day 6 morning. Roughly 10 hours.**

### Prerequisites
Gate 3 passed. **Feature freeze begins now.** No new features after Day 5 starts. Bug fixes and presentation work only.

### Work

**F**
- Design audit against the `design.md` §9 checklist, item by item. Grep for `#` hex literals outside `tokens.css`. Grep for emoji. Grep for `backdrop-filter`.
- Accessibility: keyboard-only pass through the entire demo script, focus rings everywhere, contrast verified, `prefers-reduced-motion` verified.
- Loading skeletons everywhere a spinner remains.
- Production build; confirm time-to-interactive under 2 s on the demo laptop.

**B**
- Logging cleanup: structured, `request_id` on every line, no secrets, `INFO` in the demo profile.
- Seed a clean demo database and commit it, so the demo works from a fresh clone.
- Final metrics run for the deck.

**V**
- Final threshold values committed to `.env.example`.
- Pipeline startup time measured. If workers take more than about 30 s to load models, pre-warm them before the presentation rather than starting them on stage.

**D** — most important role for these two days
- Finish the deck.
- **Three full rehearsals of the demo, end to end, on the demo machine, with the room's projector if possible.** Timed. `reset-demo` between each. Criterion D-5 is zero crashes across three consecutive runs, and it is only meaningful if the three runs actually happen.
- Prepare the failure fallback: a screen recording of a successful run, on the local disk, ready to play. If the live demo fails on stage, the recording plays and the presentation continues. This is not defeatism; it is the difference between a bad minute and a lost round.
- Prepare answers for the questions that will be asked:
  - "How is this different from existing ANPR?" — plate is one signal of three; show the visual bridge.
  - "How do you handle two identical white cars?" — show the ablation and the gate rejection.
  - "What is your accuracy?" — IDF1 is X, and here is why accuracy is the wrong metric for identity assignment.
  - "Does this scale to a whole city?" — workers are independent per camera; the index is swappable; here is the edge-deployment path.
  - "What about privacy?" — role-based masking, audit log, 30-day retention, vehicles-only crops, and data minimisation at the edge.
  - "What is the licence on YOLO?" — AGPL-3.0, fine for this, and the detector is swappable behind an interface if commercialised.

### Verification gate 4 — release gate

- [ ] Three consecutive full demo runs, zero crashes (D-5).
- [ ] Full demo completes in under 90 seconds of interaction (D-4).
- [ ] **Network cable unplugged, wifi off, full demo runs** (D-6).
- [ ] Trajectory across three or more cameras renders (D-1).
- [ ] Visual bridge over a plate failure demonstrated on demand (D-2).
- [ ] Gate rejection shown live with numbers on screen (D-3).
- [ ] Every `design.md` §9 checklist item passes.
- [ ] Keyboard-only navigation completes the demo script.
- [ ] Clean clone → running demo in under 15 minutes following `README.md` (E-5).
- [ ] `tracker.md` fully updated.
- [ ] Fallback recording on the demo machine's local disk.
- [ ] Laptop charged. Charger packed. HDMI adapter packed. Recording on the same disk as the app.

---

## 7. Dependency Map

```
Phase 0 ─────────────────────────────────────────────────┐
   │                                                      │
   ├─ B: schema + migrations ──┐                          │
   ├─ V: environment + weights ─┤                          │
   ├─ F: tokens + shell ────────┤                          │
   └─ D: footage + topology ────┘                          │
                                │                          │
Phase 1 ◄───────────────────────┘                          │
   │                                                       │
   ├─ B: auth, cameras, edges, GATE  ──┐                   │
   ├─ V: detect, track, tracklets ─────┤                   │
   ├─ F: login, guards, primitives ────┤   (mock-backed,   │
   └─ D: ground truth begins ──────────┘    never blocked) │
                                │                          │
Phase 2 ◄───────────────────────┘                          │
   │  needs: gate tested, topology loaded                  │
   ├─ V: best-shot, OCR, embeddings, ingest ──┐            │
   ├─ B: FAISS, RESOLVER, ingest, WebSocket ──┤            │
   ├─ F: live wall, search, map ──────────────┤            │
   └─ D: evaluation script ───────────────────┘            │
                                │                          │
Phase 3 ◄───────────────────────┘                          │
   │  needs: end-to-end run producing decisions            │
   ├─ F: EVIDENCE PANEL, review queue ──┐                  │
   ├─ B: confirm/reject, reset, metrics ─┤                 │
   ├─ V: robustness, threshold sweep ────┤                 │
   └─ D: ABLATION, demo script ──────────┘                 │
                                │                          │
Phase 4 ◄───────────────────────┘                          │
   │  FEATURE FREEZE                                       │
   └─ polish, rehearse ×3, deck ◄────────────────────────  ┘
```

### Hard blocking dependencies

| Blocked | Blocked by | Why |
|---|---|---|
| Identity resolver | Spatio-temporal gate | The gate filters candidates before scoring. Building the resolver first means rewriting it. |
| Identity resolver | Camera topology loaded | The gate needs a graph. No graph, no gating, and the resolver silently degrades to pure visual matching. |
| Ingest endpoint | Sightings schema | Contract must be fixed before V writes the client. |
| Trajectory map | `/vehicles/{id}/trajectory` | F mocks it until Phase 2. |
| Evidence panel | `match_decisions` populated | Cannot show reasoning that was never recorded. |
| Ablation study | Rejections persisted | The study is a `GROUP BY rejection_reason`. |
| Metrics | Ground truth | No annotation, no IDF1, and the deck has an empty results slide. |
| Demo rehearsal | Everything | Which is why the freeze exists. |

### Non-blocking, parallel from Day 1

- All frontend work, against mocks.
- All footage collection and annotation.
- Deck structure and narrative.
- UI primitives and design tokens.
- Gate unit tests — the gate is a pure function and can be written and tested before anything calls it.

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gate never rejects anything and nobody notices | **High** | **Fatal to the pitch** | Explicit SQL check at gate 2. Construct the case if the footage does not produce one naturally. |
| OCR reads almost nothing | High | Low | Expected, and it is the premise of the project. Report the read rate honestly; it strengthens the argument. Ensure the visual tier carries the demo. |
| Re-ID merges two different vehicles | High | Medium | Ambiguity margin sends the case to review rather than guessing. Report false-merge rate rather than hiding it. |
| Footage has no genuine cross-camera vehicles | Medium | **Fatal** | Verify on Day 1, not Day 4. If none exist, re-shoot immediately — a phone at each end of a street for twenty minutes is enough. |
| Worker clocks drift | Medium | High | Shared epoch across workers, skew detection in the backend, `system.error` broadcast. |
| CUDA or driver problems on the demo machine | Medium | High | Keep the CPU path working. Benchmark it. Know the FPS. |
| Merge conflicts | Medium | Medium | Directory ownership. Squash merges. Daily integration at end of day. |
| Venue wifi fails | **High** | **Fatal if unprepared** | D-6 offline requirement, verified at gate 0 and gate 4. Local tiles, local fonts, local weights. |
| Scope creep into post-MVP items | High | High | Feature freeze Day 5. The post-MVP list in `prd.md` §5.2 is a roadmap slide, not a backlog. |
| Live demo fails on stage | Low | High | Rehearsed three times, plus a local recording as fallback. |

---

## 9. Daily Cadence

**Morning, 15 minutes, standing.** What each person finished yesterday, what they are doing today, what is blocking them. Fifteen minutes, not forty.

**End of day, 30 minutes.** Everyone merges to `main`. Run the current gate's checks. Update `tracker.md`. If `main` is broken at the end of a day, fix it before anyone leaves — a broken `main` overnight costs four people their first hour the next morning.

**Day 3 evening is the decision point.** If gate 2 has not passed, cut scope immediately: drop the review queue, drop merge and split, drop playback animation. Keep the live wall, the trajectory map, and the evidence panel. Those three screens are the demo. Everything else is decoration on a screen nobody will reach in ninety seconds.
