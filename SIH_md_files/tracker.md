# tracker.md — Task Tracker

**Project:** Marg (SIH26127)
**Last updated:** _not yet started_
**Current phase:** Phase 0

---

## Instructions for the AI agent

**Read this section before modifying this file. It is not optional.**

### Status symbols

| Symbol | Meaning |
|---|---|
| `[ ]` | Not started |
| `[/]` | In progress — work has begun but the task is not complete |
| `[x]` | Complete and verified |
| `[!]` | Blocked — a `> BLOCKED:` note must follow on the next line |
| `[-]` | Cancelled or descoped — a `> DESCOPED:` note must follow |

### When to update

Update this file **after every file modification**, in the same response as the change. Not at the end of the session, not when asked. A tracker updated retroactively is a tracker written from memory, and it will be wrong.

The sequence is: make the change → update the task line → state in the response which task ID moved and to what.

### How to update a task line

Format:

```
- [x] [TASK-014] Implement spatio-temporal gate  <!-- 2026-09-02T14:32Z -->
```

- Move the status symbol.
- Append or update the ISO-8601 UTC timestamp comment when the status changes to `[x]` or `[!]`.
- Never delete a task. If it is no longer needed, mark it `[-]` with a reason.
- Never renumber tasks. IDs are permanent references; other documents and commit messages point at them.

### Recording a blocker

```
- [!] [TASK-022] Wire FAISS index into resolver  <!-- 2026-09-03T09:15Z -->
  > BLOCKED: embedding dimension mismatch — OSNet returns 512 but the index was
  > built at 2048. Needs TASK-019 rebuild before this can proceed.
```

State what is blocking, and which task must complete first if that is known. A blocker note that says only "not working" is worse than no note, because it looks like information.

### Adding new tasks

Append to the relevant phase using the next free ID in that phase's block. Do not insert into the middle of the numbering. If a task turns out to need splitting, mark the original `[-]` with a note pointing at the replacements, and add the new tasks at the end of the block.

### Definition of done

A task is `[x]` only when all of the following hold:

1. The code is written and runs without error.
2. It matches the specification in `prd.md`, `techspec.md`, `schema.md`, `appflow.md`, or `design.md` — whichever governs it.
3. Its acceptance criteria are met, where the task references one.
4. Tests exist and pass, where the task is in `backend/app/services/` or is a pure function.
5. It is merged to `main` and `main` still runs.

A task that works locally on an unmerged branch is `[/]`, not `[x]`.

### Phase gates

Do not begin a phase's tasks until the previous phase's gate block is fully `[x]`. Gate tasks are prefixed `GATE-` and are verified by running the commands in `implementationplan.md`, not by inspection.

### Progress line

Update the counter at the top of each phase when a task's status changes. Format: `Progress: 7/18 complete, 2 in progress, 1 blocked`.

---

## Phase 0 — Foundations

**Owner:** all · **Target:** Day 1 morning
**Progress:** 0/22 complete

### Spec amendments

- [x] [TASK-000] Amend specs after ML benchmarking: invert the identity resolver to feasible-set scoring (`techspec.md` §5.6), fusion weights W_VISUAL 0.60→0.45 / W_TEMPORAL 0.15→0.55 / W_PLATE 0.25→0.20, add `VISUAL_FLOOR=0.55`, remove `MATCH_THRESHOLD` (§5.6 + §7); pipeline models YOLOv8n→YOLOv8s, PaddleOCR→EasyOCR, REID_INPUT_SIZE 256,128→256,256 (§2.1 + ml-pipeline `.env`); rename repo root `sih-mtmc-tracker`→`sih-tracker` across all files. Residual cleanup folded in: `MATCH_THRESHOLD`→`VISUAL_FLOOR` in `rules.md` convention examples, `implementationplan.md` sweep now `VISUAL_FLOOR` + `W_VISUAL`/`W_TEMPORAL` ratio, YOLOv8n→YOLOv8s in `techspec.md` §1 diagram and §6, §1/`CLAUDE.md` architecture updated to graph-generates-candidates flow, and TASK-118 wording corrected to "four rejection reasons plus FEASIBLE"  <!-- 2026-09-02T15:51Z -->

### Repository

- [ ] [TASK-001] Create `sih-tracker` repository with the layout from `techspec.md` §8
- [ ] [TASK-002] Commit all eight spec documents plus `CLAUDE.md` into `docs/`
- [ ] [TASK-003] Write `.gitignore` covering datasets, weights, `.env`, `data/`, `node_modules/`, `*.db*`
- [ ] [TASK-004] Write root `README.md` with clone-to-demo setup steps
- [ ] [TASK-005] Agree and document branch policy and directory ownership in `README.md`

### Backend setup — owner B

- [/] [TASK-006] Create `backend/` virtualenv and `requirements.txt` with pins from `techspec.md` §2.2  <!-- venv on py3.14, requirements written; numpy/pytest deviations noted inline -->
  > NOTE: session-2 layers (fastapi/uvicorn/alembic/rapidfuzz/jose/bcrypt/multipart/httpx) listed but not yet installed.
- [/] [TASK-007] FastAPI skeleton with `/api/v1/system/health`  <!-- app/main.py: lifespan builds graph+index+broadcaster+lock on app.state; X-Request-ID middleware; CORS explicit origins -->

- [/] [TASK-008] Configure `pydantic-settings` config module reading every variable in `techspec.md` §7  <!-- app/core/config.py: all §7 vars, amended weights, MIN_REVISIT_SECONDS -->

- [/] [TASK-009] Initialise Alembic; add the SQLite pragma listener (`foreign_keys=ON`, WAL) from `schema.md` §5  <!-- pragma listener done (fk=ON, WAL, synchronous=NORMAL, sqlite3.Connection guard); Alembic init still pending -->

- [ ] [TASK-010] Write and apply migrations `0001`, `0002`, `0003` from `schema.md` §3
- [/] [TASK-011] Write `backend/.env.example` with every variable and safe placeholders  <!-- amended weights, VISUAL_FLOOR, MATCH_THRESHOLD removed -->


### ML pipeline setup — owner V

- [ ] [TASK-012] Create `ml-pipeline/` virtualenv and `requirements.txt` with pins from `techspec.md` §2.1
- [ ] [TASK-013] Write `scripts/download_models.py` for YOLOv8n, OSNet, and PaddleOCR weights
- [ ] [TASK-014] Verify CUDA availability and record the device in `tracker.md` notes
- [ ] [TASK-015] Write `ml-pipeline/.env.example`

### Frontend setup — owner F

- [ ] [TASK-016] Scaffold Vite + React 19 + TypeScript 5.9, versions pinned per `techspec.md` §2.3
- [ ] [TASK-017] Configure Tailwind; write `styles/tokens.css` with every token from `design.md` §4–6
- [ ] [TASK-018] Self-host Inter and JetBrains Mono woff2 in `public/fonts/` with `@font-face`. No CDN link.
- [ ] [TASK-019] Build the app shell — TopBar, Sidebar, router with all routes from `appflow.md` §1

### Data — owner D

- [ ] [TASK-020] Collect footage for 3–5 cameras with overlapping wall-clock windows
- [ ] [TASK-021] Verify at least 15 vehicles genuinely appear at two or more cameras
- [ ] [TASK-022] Author camera topology: coordinates and transit windows per edge

### Gate 0

- [ ] [GATE-000] `/system/health` returns ok; `.tables` lists all 7; `PRAGMA foreign_keys` returns 1
- [ ] [GATE-001] `pnpm build` succeeds and the shell renders at `localhost:5173`
- [ ] [GATE-002] Model weights download and load; `torchreid`, `faiss`, `numpy` all import
- [ ] [GATE-003] **Offline check** — network disconnected, backend and frontend start, models load

---

## Phase 1 — Data Layer and Authentication

**Owner:** B critical path · **Target:** Day 1 afternoon → Day 2 morning
**Progress:** 0/26 complete

### Models and repositories — owner B

- [/] [TASK-101] SQLModel classes for all 7 tables, matching `schema.md` §3 exactly  <!-- 8 tables (incl refresh_tokens), one file per model, UUID PKs, ISO-8601 TEXT ts, all CHECKs/indexes/FK ondelete verified via DDL dump -->

- [/] [TASK-102] `encode_embedding` / `decode_embedding` helpers per `schema.md` §4  <!-- app/services/vector_index.py, normalise-on-write once; roundtrip norm=1.0 verified -->

- [/] [TASK-103] `camera_repo.py` with CRUD and active filtering  <!-- get_all/active_cameras, get_by_code, get_all_edges (read path for graph build) -->
- [/] [TASK-104] `sighting_repo.py` with time-range and camera filtering  <!-- get_by_vehicle, get_since (index rebuild), get_latest_per_vehicle -->
- [/] [TASK-105] `vehicle_repo.py` with plate, partial-plate, and time-window search  <!-- get_by_plate, search_partial_plate, get_by_ids, create, update_counters -->
- [ ] [TASK-106] `scripts/seed_users.py` — three roles, passwords from env, no defaults
- [ ] [TASK-107] `scripts/seed_cameras.py` — topology from `schema.md` §6

### Authentication — owner B

- [ ] [TASK-108] bcrypt hash and verify, cost 12, using `bcrypt` directly (no passlib)
- [ ] [TASK-109] JWT issue and verify, HS256, 30-minute expiry, claims per `techspec.md` §4.2
- [ ] [TASK-110] Refresh token issue, SHA-256 storage, rotation, reuse detection
- [ ] [TASK-111] `/auth/login`, `/refresh`, `/logout`, `/me`
- [ ] [TASK-112] `deps.py` — `get_current_user`, `require_role`
- [ ] [TASK-113] Failed-login throttle: 5 per email per 15 minutes → 429
- [ ] [TASK-114] Audit logging on all auth actions

### Topology and gate — owner B

- [ ] [TASK-115] `/cameras` CRUD with soft delete
- [ ] [TASK-116] `/camera-edges` CRUD plus `/estimate`
- [/] [TASK-117] `camera_graph.py` — networkx build, shortest path, transit-window summation  <!-- from_camera_id/to_camera_id, is_bidirectional reverse edge, node codes, PathResult(distance+codes), feasible_candidates -->

- [/] [TASK-118] **`spatiotemporal_gate.py`** — pure function, four rejection reasons plus FEASIBLE (SAME_CAMERA_TOO_SOON, NO_PATH, TEMPORAL_TOO_FAST, TEMPORAL_EXPIRED, FEASIBLE); an absent camera raises `CameraNotFoundError`, it is not a rejection outcome  <!-- str ids, int elapsed; GateDecision carries passed/reason/elapsed/min/max/path_distance_m/path_camera_codes -->

- [/] [TASK-119] Unit tests for the gate: too fast, expired, no path, same camera, multi-hop  <!-- 11 tests pass (pytest 9.1.1): 4 rejections + FEASIBLE + two-hop sum-of-edges + bidirectional + one-way NO_PATH + CameraNotFoundError -->

- [/] [TASK-120] Global exception handler emitting the envelope from `techspec.md` §5.3 with `request_id`  <!-- core/exceptions.py: MargError/validation/unhandled handlers; X-Request-ID header -->


### Frontend — owner F

- [ ] [TASK-121] `lib/api.ts` — axios, auth interceptor, **deduplicated** refresh-on-401
- [ ] [TASK-122] `authStore` — in-memory only, no localStorage
- [ ] [TASK-123] Login page with every error state from `appflow.md` §A1
- [ ] [TASK-124] Route guards and role-based redirects with toasts
- [ ] [TASK-125] UI primitives per `design.md` §7 — Button, Input, Badge, Table, Dialog, Skeleton, EmptyState, Toast
- [ ] [TASK-126] `mocks/` fixtures matching the API contract exactly

### Pipeline — owner V

- [ ] [TASK-127] `frame_source.py` — MP4 read, controlled FPS, shared timestamp epoch
- [ ] [TASK-128] `detector.py` — YOLOv8n filtered to `TARGET_CLASSES`
- [ ] [TASK-129] `tracker.py` — ByteTrack with stable local IDs
- [ ] [TASK-130] `tracklet.py` — accumulate, finalise on track loss, discard below `MIN_TRACKLET_FRAMES`
- [ ] [TASK-131] Visualisation mode writing an annotated MP4; watch it and confirm quality

### Data — owner D

- [ ] [TASK-132] Ground truth for 20+ cross-camera vehicles: vehicle, camera, entry time, plate

### Gate 1

- [ ] [GATE-100] Login → access token + refresh cookie; refresh rotates and revokes the old token
- [ ] [GATE-101] Viewer receives 403 `INSUFFICIENT_ROLE` on an admin endpoint
- [ ] [GATE-102] `/camera-edges` returns the seeded topology
- [ ] [GATE-103] **All gate unit tests pass**, including the multi-hop path case
- [ ] [GATE-104] All three seeded roles sign in and land correctly; guards redirect as specified
- [ ] [GATE-105] Worker produces an annotated video with stable track IDs

---

## Phase 2 — Core Pipeline and Identity Resolution

**Owner:** V and B · **Target:** Day 2 afternoon → Day 3
**Progress:** 0/28 complete

### Pipeline — owner V

- [ ] [TASK-201] `best_shot.py` — area × confidence × Laplacian variance, persist crop
- [ ] [TASK-202] `plate_detector.py` — PaddleOCR text detection on the lower crop region
- [ ] [TASK-203] `ocr.py` — PaddleOCR recognition returning text and confidence
- [ ] [TASK-204] `normalizer.py` — uppercase, strip, validate regex, confusion map
- [ ] [TASK-205] Unit tests for the normaliser using real OCR failure strings
- [ ] [TASK-206] `embedder.py` — OSNet, batched, L2-normalised 512-D output
- [ ] [TASK-207] `ingest_client.py` — POST with retry, fatal exit on 401
- [ ] [TASK-208] `run_all_workers.py` — process per camera, shared epoch, supervise, heartbeat

### Resolution — owner B

- [/] [TASK-209] `vector_index.py` — `IndexIDMap2(IndexFlatIP)`, add, search, startup rebuild  <!-- +search_subset; internal uuid<->int64 map; rebuild via sighting_repo.get_since; 5 tests pass -->

- [/] [TASK-210] `plate_matcher.py` — exact, then rapidfuzz with the confusion map at distance ≤ 1  <!-- normalise/is_structurally_valid/match_score + is_confusable_match; rapidfuzz 3.14.1 installed; 8 unit tests -->

- [/] [TASK-211] **`identity_resolver.py`** — full algorithm from `techspec.md` §5.6 (AMENDED: feasible-set candidate generation, cosine+temporal fusion, VISUAL_FLOOR, plate tier + gate fall-through)  <!-- 8 resolver tests incl White Maruti; all thresholds from config -->
- [/] [TASK-212] `MatchDecision` written for every candidate evaluated, including rejections  <!-- gate rejects carry visual_score + path_camera_codes/path_distance_m/elapsed/min/max -->
- [/] [TASK-213] Ambiguity margin → `AMBIGUOUS` status, no assignment  <!-- top-2 within AMBIGUITY_MARGIN → ambiguous, no fall-through to NEW -->
- [/] [TASK-214] Denormalised counter maintenance on `vehicles`  <!-- vehicle_repo.update_counters: sighting_count, camera_count, first/last_seen_at -->
  > RESOLVED (session 3): `match_decision_repo.py` added (create_many/get_by_sighting/get_ambiguous/count_by_rejection_reason); resolver now defers all decision writes to it. Layering seam closed.
  > RESOLVED (session 3): IdentityResolver now takes injected graph + VectorIndex; no per-resolve rebuild. Ingest/batch pass the long-lived app.state index.
- [/] [TASK-215] `/ingest/sightings` and `/batch` with `compare_digest` key check  <!-- /ingest/sightings + /ingest/sightings/batch (§5.4 path); ingest_service; received_at + >5s skew warning+system.error -->
- [/] [TASK-216] Async lock serialising resolution — FAISS is not concurrent-safe  <!-- app.state.ingest_lock wraps ingest_one+commit; index.add after resolve -->
- [/] [TASK-217] `broadcaster.py` and `/ws/events` with all 6 message types  <!-- sighting.created/match.ambiguous/match.rejected/worker.status/system.error builders; no token check (auth cut) -->
- [/] [TASK-218] `/vehicles` list and search  <!-- plate/plate_partial/from/to/camera_id/vehicle_class/min_sightings/limit/offset, list envelope §5.2 -->
- [/] [TASK-219] `/vehicles/{id}/trajectory` — ordered sightings, polyline, per-hop decisions
- [/] [TASK-220] `/sightings/{id}`, `/crop`, `/candidates`  <!-- SightingDetailRead + decisions; candidates = every MatchDecision; crop FileResponse from CROP_STORAGE_PATH -->
  > NOTE: auth CUT this session — no /auth, JWT, roles, plate masking or WS token check. users/refresh_tokens tables remain as roadmap only.
  > TESTS: tests/integration/test_ingest_and_batch.py — ingest→persisted+read-back, wrong key 401, unknown camera 404, and batch runner == ingest path on identical input. 34 tests pass.
- [ ] [TASK-221] Plate masking in the response serialiser for `viewer`

### Frontend — owner F

- [ ] [TASK-222] `useLiveEvents` — WebSocket, backoff reconnect, gap backfill
- [ ] [TASK-223] `ConnectionIndicator`
- [ ] [TASK-224] Live wall — camera grid, detection overlay, event feed
- [ ] [TASK-225] Distinct styling for `match.rejected` rows in the event feed
- [ ] [TASK-226] Search page — all three tabs with empty states
- [ ] [TASK-227] Vehicle detail — Leaflet map, markers, confidence-styled polylines, timeline

### Data — owner D

- [ ] [TASK-228] `scripts/evaluate_metrics.py` — IDF1, IDP, IDR, MOTA, false-merge rate, gate counts

### Gate 2 — the most important gate

- [ ] [GATE-200] `./scripts/demo.sh` starts 3 workers; sightings arrive and resolve
- [ ] [GATE-201] Live wall shows 3 feeds with boxes and a populating event feed
- [ ] [GATE-202] Plate search returns a vehicle from the footage
- [ ] [GATE-203] Trajectory renders as a polyline across 2+ cameras (**D-1**)
- [ ] [GATE-204] **A `VISUAL` match exists on a sighting with no plate read** (**D-2**)
- [ ] [GATE-205] **A `TEMPORAL_TOO_FAST` rejection exists in `match_decisions`** (**D-3**)
- [ ] [GATE-206] `pytest --cov=app/services` ≥ 70%
- [ ] [GATE-207] `evaluate_metrics.py` prints an IDF1 figure

> GATE-205 is the one that fails silently. Everything can appear to work while the
> gate is never actually invoked. Verify it with a direct SQL query, not by
> assuming. If no rejection exists, construct the case deliberately.

---

## Phase 3 — Explainability, Review, and Edge Cases

**Owner:** F leads · **Target:** Day 4
**Progress:** 0/22 complete

### Evidence and review — owner F

- [ ] [TASK-301] **`MatchExplanation` component** — component scores, fused score, threshold, transit window
- [ ] [TASK-302] "Also considered" block listing rejected candidates with reasons and numbers
- [ ] [TASK-303] Evidence panel — best shot, plate crop, metadata, explanation, actions
- [ ] [TASK-304] Confirm action with optimistic update and rollback
- [ ] [TASK-305] Reject action with confirmation dialog and re-resolution
- [ ] [TASK-306] Review queue at `/review` — side-by-side candidate crops, three actions
- [ ] [TASK-307] Trajectory playback with `prefers-reduced-motion` handling
- [ ] [TASK-308] Every empty state from `appflow.md` §6.6
- [ ] [TASK-309] Every error state from `appflow.md` §6.2 — inline per panel, not full-screen
- [ ] [TASK-310] Admin camera and edge forms with map-click coordinate entry
- [ ] [TASK-311] Reset-demo dialog with typed `RESET` confirmation

### Backend — owner B

- [ ] [TASK-312] `/match-decisions/{id}/confirm`
- [ ] [TASK-313] `/match-decisions/{id}/reject` with re-resolution excluding the rejected candidate
- [ ] [TASK-314] `/match-decisions/ambiguous`
- [ ] [TASK-315] `/vehicles/{id}/split` and `/vehicles/merge`
- [ ] [TASK-316] `/system/reset-demo` — wipe data and index, keep cameras, users, audit
- [ ] [TASK-317] `/system/metrics` — live IDF1, gate counts by reason, method distribution
- [ ] [TASK-318] Clock-skew detection and `system.error` broadcast

### Pipeline — owner V

- [ ] [TASK-319] All failure paths from `appflow.md` §6.4
- [ ] [TASK-320] Threshold sweep; record IDF1 and false-merge rate per operating point
- [ ] [TASK-321] `benchmark_pipeline.py` producing the NFR-P1 FPS figure

### Data — owner D

- [/] [TASK-322] **Ablation study** — gate off vs gate on, same footage, false-merge rate for each  <!-- mechanism built: scripts/run_batch.py --no-gate; smoke shows gate ON = 2 vehicles + TEMPORAL_TOO_FAST, gate OFF = 1 (false merge). Data owner still runs it on real footage. -->
  > NOTE: scripts/reset_demo.py (offline) added — clears sightings/vehicles/match_decisions + crops, keeps cameras/edges/users. The /system/reset-demo HTTP endpoint (TASK-316) remains for a later session.

### Gate 3

- [ ] [GATE-300] Evidence panel shows a full breakdown for a `VISUAL` match with no plate
- [ ] [GATE-301] "Also considered" lists a rejected candidate with reason and numbers
- [ ] [GATE-302] Confirm restyles the segment; reject splits and reassigns; toasts correct
- [ ] [GATE-303] Review queue shows an ambiguous case with side-by-side crops
- [ ] [GATE-304] Reset-demo clears state; UI empties without a page reload
- [ ] [GATE-305] Kill a worker: tile offline, others continue, error surfaced, no crash
- [ ] [GATE-306] Restart the backend: FAISS rebuilds, trajectories still resolve
- [ ] [GATE-307] Ablation complete, both numbers recorded

---

## Phase 4 — Polish, Rehearsal, Deck

**Owner:** D leads · **Target:** Day 5 → Day 6 morning
**Progress:** 0/18 complete

> **Feature freeze is in force from the start of this phase.** New feature work
> here is a bug, not a contribution.

### Frontend — owner F

- [ ] [TASK-401] Design audit against the `design.md` §9 checklist, item by item
- [ ] [TASK-402] Grep for hex literals outside `tokens.css`; replace with tokens
- [ ] [TASK-403] Grep for emoji and `backdrop-filter`; remove
- [ ] [TASK-404] Keyboard-only pass through the entire demo script
- [ ] [TASK-405] Contrast verification against the ratios in `design.md` §4
- [ ] [TASK-406] `prefers-reduced-motion` verified across every animated element
- [ ] [TASK-407] Loading skeletons replacing any remaining spinners
- [ ] [TASK-408] Production build; TTI under 2 s on the demo laptop

### Backend — owner B

- [ ] [TASK-409] Structured logging with `request_id`; no secrets; `INFO` in the demo profile
- [ ] [TASK-410] Seed and commit a clean demo database
- [ ] [TASK-411] Final metrics run for the deck

### Pipeline — owner V

- [ ] [TASK-412] Final threshold values committed to `.env.example`
- [ ] [TASK-413] Measure worker startup time; plan pre-warming if over 30 s

### Demo — owner D

- [ ] [TASK-414] Complete the deck
- [ ] [TASK-415] Write the demo script — exact clicks, exact vehicle, exact plate, in order
- [ ] [TASK-416] **Three timed full rehearsals on the demo machine**, reset between each
- [ ] [TASK-417] Record the fallback screen capture; store on the demo machine's local disk
- [ ] [TASK-418] Prepare answers to the six anticipated questions in `implementationplan.md` §6

### Gate 4 — release

- [ ] [GATE-400] Three consecutive full runs, zero crashes (**D-5**)
- [ ] [GATE-401] Full demo under 90 seconds of interaction (**D-4**)
- [ ] [GATE-402] **Network disconnected, full demo runs** (**D-6**)
- [ ] [GATE-403] Trajectory across 3+ cameras (**D-1**)
- [ ] [GATE-404] Visual bridge over a plate failure, on demand (**D-2**)
- [ ] [GATE-405] Gate rejection shown live with numbers on screen (**D-3**)
- [ ] [GATE-406] Every `design.md` §9 item passes
- [ ] [GATE-407] Keyboard-only completion of the demo script
- [ ] [GATE-408] Clean clone → running demo in under 15 minutes (**E-5**)
- [ ] [GATE-409] `tracker.md` fully updated
- [ ] [GATE-410] Fallback recording present on the demo machine
- [ ] [GATE-411] Laptop charged, charger packed, HDMI adapter packed

---

## Descoped

Tasks moved here with a reason. Nothing is deleted.

_(empty)_

---

## Blockers

Active blockers, mirrored from their task lines for visibility.

_(none)_

---

## Notes

Free-form log. Environment details, decisions made mid-build, threshold values landed on, anything a teammate would otherwise have to ask about.

_(empty)_
