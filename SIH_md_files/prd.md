# prd.md — Product Requirements

**Project:** Marg — City-Wide Vehicle Trajectory Reconstruction
**Problem Statement:** SIH26127 (Smart India Hackathon 2026)
**Repo:** `sih-tracker/`
**Version:** 1.0
**Status:** Approved for build

> Naming note: "Marg" (मार्ग, "route/path") is a working name. It appears in UI copy, the app title, and package metadata only. Changing it is a single find-and-replace across `frontend/` and `backend/app/core/config.py`. No logic depends on it.

---

## 1. Problem Statement

When a vehicle of interest passes through a city — a hit-and-run, a stolen car, a vehicle flagged on a watchlist — investigators today reconstruct its route by hand. An officer requests footage from each traffic camera along a suspected corridor, receives the files hours or days later, and scrubs through them looking for a match. A single 5-camera reconstruction routinely takes a working day.

Automated Number Plate Recognition (ANPR) was supposed to solve this, and it does not. ANPR is a single-camera, single-frame technology that answers "what plate is in this image." It fails, silently and often, under exactly the conditions that matter:

- The plate is obscured — by another vehicle in dense traffic, by a bumper-mounted accessory, by mud, or deliberately.
- The plate is unreadable — motion blur, glare, low light, oblique camera angle, or a resolution too low at distance.
- The plate is non-standard — hand-painted fonts, decorative scripts, and regional stylings remain common on Indian roads.
- The vehicle has no front plate mounted at all.

When ANPR fails at Camera 3 of a 6-camera route, the trajectory breaks. There is no mechanism to bridge the gap, because ANPR has no concept of "the same vehicle seen elsewhere." Every camera is an island.

**The gap this project fills:** no publicly available system fuses Multi-Target Multi-Camera (MTMC) visual re-identification with ANPR on Indian road conditions. MTMC research exists (AI City Challenge). Indian ANPR implementations exist in quantity. The two have not been combined, and combining them is what makes trajectory reconstruction survive a plate-read failure.

**The approach:** treat the plate as one signal among several rather than the only signal. Each vehicle sighting produces a plate read (when available), a 512-dimensional visual appearance embedding, and a timestamped camera location. A vehicle's identity across cameras is resolved by fusing all three, with a spatio-temporal feasibility gate that rejects matches which violate the physics of road travel.

---

## 2. Why Visual Matching Alone Is Not Enough

Adding visual Re-ID on top of ANPR introduces its own failure mode, and the specification must be honest about it.

**The "White Maruti" problem.** Indian roads carry enormous numbers of visually identical vehicles. A white Maruti Suzuki hatchback is not a distinguishing description; it is a description of thousands of vehicles within any given city. An appearance embedding for two different white hatchbacks of the same model, viewed at similar angles under similar lighting, will have a cosine similarity high enough to pass any threshold that is loose enough to be useful. Intra-class similarity in this domain is severe, and no amount of embedding model quality removes it — the vehicles genuinely look the same.

**This is why spatio-temporal filtering is a first-class component, not a refinement.** If Camera A and Camera B are 5 km apart along a road with a realistic transit window of 6 to 25 minutes, then a visually identical vehicle appearing at B ten seconds after A is not the same vehicle. It is physically impossible, regardless of embedding similarity. The camera topology graph is what converts an ambiguous appearance match into a defensible identity claim.

The system therefore has three signals, and the design principle is that **no single signal is trusted alone:**

| Signal | Strength | Failure mode |
|---|---|---|
| Plate text | Near-unique when read correctly | Frequently unavailable or wrong |
| Visual appearance | Always available | Severe intra-class ambiguity |
| Spatio-temporal feasibility | Physically grounded, cannot be spoofed by appearance | Only constrains; never confirms alone |

---

## 3. Target Personas

### Primary — Traffic Control Room Operator ("Ramesh")

City traffic management centre, monitoring 8–40 camera feeds across a shift. Comfortable with CCTV software and municipal dashboards; not a data scientist. Works under time pressure with a supervisor asking for answers.

**Needs**
- Enter a plate (or partial plate) and see, within seconds, where that vehicle has been and where it went.
- Understand *why* the system linked two sightings, so he can defend the answer when questioned.
- See when the system is unsure, rather than being handed false confidence.
- Keep working when a plate is unreadable — the current dead end.

**Frustrations with existing tools**
- Systems that report a match with no evidence attached.
- Interfaces requiring a per-camera search rather than a per-vehicle search.
- Trajectories that terminate the moment ANPR fails.

### Secondary — Investigating Officer ("Inspector Devi")

Assigned to a specific incident. Not a continuous system user; arrives with one vehicle and one time window and needs a reconstruction she can put in a case file.

**Needs**
- Query by time window and location when no plate is known at all.
- Export a trajectory with per-hop evidence: cropped images, timestamps, confidence scores, and the reason each link was accepted.
- Clear separation between machine-suggested links and human-confirmed links.

### Tertiary — System Administrator ("Arjun")

Municipal IT. Registers cameras, maintains the topology graph, manages user accounts.

**Needs**
- Add a camera with coordinates and connect it to neighbours with realistic transit times.
- Control who can view unmasked plate data.
- Audit trail of who searched for what.

---

## 4. Scope Boundary

This is a **decision-support tool**, not an identification system. The distinction is deliberate and appears in the product, not only in the documentation.

- The system proposes candidate links between sightings, ranked and scored, with evidence attached.
- A human operator confirms or rejects each proposed link.
- No output is presented as an identification. Confirmed trajectories are labelled as operator-confirmed, not system-verified.
- Confidence is always surfaced. The UI has no state in which a match is shown without its score and its reasoning.

This framing is not defensive hedging. It reflects a real accuracy ceiling — cross-camera Re-ID under dense traffic does not reach identification-grade reliability, and a system claiming otherwise would be wrong in a way that matters.

---

## 5. Core Features

### 5.1 MVP — Required for the demo

---

**F-01 · Multi-camera ingestion**

*As an operator, I want the system to process several camera feeds at once so that a vehicle is tracked as it moves through the city.*

Acceptance criteria:
- Given 3 or more video sources registered as cameras, when the pipeline runs, then each is processed by an independent worker and sightings are attributed to the correct camera.
- Given a video file source, when playback is requested, then frames are emitted at a controlled rate with synthetic wall-clock timestamps, so recorded footage behaves like a live feed for demo purposes.
- Given a worker crashes, when the supervisor detects it, then remaining workers continue and the failure is surfaced on the dashboard rather than silently dropping the feed.

---

**F-02 · In-camera detection and tracking**

*As the system, I need to detect vehicles and follow them within a single feed so that one vehicle produces one sighting rather than one per frame.*

Acceptance criteria:
- Given a frame, when detection runs, then cars, motorcycles, buses, trucks, and autos are detected with bounding boxes and class labels.
- Given consecutive frames, when tracking runs, then each vehicle receives a stable local track ID for the duration of its presence in the frame.
- Given a completed tracklet, when it is finalised, then exactly one `Sighting` record is emitted, containing the tracklet's best frame.
- Given a tracklet shorter than the configured minimum frame count, when it ends, then it is discarded as noise and no sighting is emitted.

---

**F-03 · Best-shot selection**

*As the system, I need to pick the highest-quality frame per tracklet so that OCR and embedding operate on the best available image rather than an arbitrary one.*

Acceptance criteria:
- Given all frames of a tracklet, when scoring runs, then the selected frame maximises a composite of bounding-box area, detection confidence, and Laplacian-variance sharpness.
- Given the selected frame, when it is persisted, then the crop is written to disk and its path is stored on the sighting for later display as evidence.

This step exists because running OCR and a Re-ID backbone on every frame of every tracklet is both wasteful and worse: averaging over blurry frames degrades the embedding. One good frame beats fifty mediocre ones.

---

**F-04 · Plate reading (ANPR)**

*As an operator, I want plates read automatically where they are legible so that high-confidence identity is available when possible.*

Acceptance criteria:
- Given a vehicle crop, when plate detection runs, then a plate region is returned or the crop is marked as having no detectable plate.
- Given a plate region, when OCR runs, then raw text and a per-read confidence score are returned.
- Given raw OCR text, when normalisation runs, then whitespace and separators are stripped, characters are uppercased, and a canonical form is produced.
- Given a normalised plate, when it is validated against the Indian plate grammar (`^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$`), then a structural-validity flag is stored alongside the text.
- Given plate reading fails entirely, when the sighting is emitted, then the sighting is still valid with a null plate — a missing plate must never block the pipeline.

---

**F-05 · Visual appearance embedding**

*As the system, I need an appearance fingerprint per sighting so that vehicles can be matched when the plate is unavailable.*

Acceptance criteria:
- Given a best-shot crop, when the Re-ID backbone runs, then a 512-dimensional float32 vector is produced.
- Given a produced vector, when it is stored, then it is L2-normalised so that inner product equals cosine similarity.
- Given a batch of crops, when embedding runs, then they are processed as a batch rather than individually.

---

**F-06 · Spatio-temporal feasibility gate** — *the differentiating component*

*As an operator, I want the system to reject matches that are physically impossible so that identical-looking vehicles in different parts of the city are not merged.*

Acceptance criteria:
- Given a camera topology graph with per-edge distance and min/max transit times, when two sightings are compared, then the elapsed time between them is checked against the feasible transit window for the shortest path connecting the two cameras.
- Given an elapsed time below the minimum transit time, when the gate evaluates, then the match is rejected with reason `TEMPORAL_TOO_FAST` regardless of visual or plate similarity.
- Given an elapsed time above the maximum transit window, when the gate evaluates, then the match is rejected with reason `TEMPORAL_EXPIRED`.
- Given no path exists between the two cameras in the graph, when the gate evaluates, then the match is rejected with reason `NO_PATH`.
- Given a rejection, when it is recorded, then the reason and the numeric values that produced it are persisted and are viewable in the UI.

The last criterion matters for the presentation. A rejection the operator can inspect — "matched at 0.91 visual similarity, rejected: 5.2 km apart in 14 seconds, minimum feasible transit 312 s" — is far more persuasive than a match with a high score.

---

**F-07 · Global identity resolution**

*As an operator, I want sightings of the same vehicle across cameras merged into one entity so that I can view a single trajectory.*

Resolution is tiered, cheapest and most reliable first:

1. **Plate tier.** If the incoming sighting has a structurally valid plate that matches an existing vehicle's canonical plate — exactly, or within edit distance 1 under the OCR confusion map (`0↔O`, `1↔I↔L`, `8↔B`, `5↔S`, `2↔Z`, `6↔G`) — and the spatio-temporal gate passes, assign that vehicle.
2. **Visual tier.** Query FAISS for the top-K nearest embeddings. Apply the spatio-temporal gate to each candidate. Score surviving candidates by the fusion formula. If the best score exceeds the match threshold and beats the runner-up by the configured margin, assign that vehicle.
3. **New identity.** Otherwise, create a new global vehicle.

Acceptance criteria:
- Given a sighting with a plate matching an existing vehicle and a feasible transit time, when resolution runs, then the existing vehicle is assigned and the decision is recorded as `PLATE_EXACT` or `PLATE_FUZZY`.
- Given a sighting with no plate and a high-similarity feasible visual candidate, when resolution runs, then the candidate is assigned and recorded as `VISUAL`.
- Given a sighting whose top two visual candidates score within the ambiguity margin of each other, when resolution runs, then no automatic assignment is made; the sighting is flagged `AMBIGUOUS` and queued for operator review.
- Given every decision, when it completes, then a `MatchDecision` row is written with all component scores and the outcome — including for rejected candidates.

---

**F-08 · Live operations dashboard**

*As an operator, I want to watch camera feeds and vehicle movement together so that I have situational awareness.*

Acceptance criteria:
- Given the pipeline is running, when the operator opens the dashboard, then a grid of camera feeds is shown with detection boxes and local track IDs overlaid.
- Given a WebSocket connection, when a sighting event arrives, then the corresponding camera tile updates and the event enters a live feed panel within 500 ms of resolution.
- Given the WebSocket disconnects, when the client detects it, then reconnection is attempted with exponential backoff and a connection-status indicator reflects the state.

---

**F-09 · Trajectory map**

*As an operator, I want a vehicle's route drawn on a city map so that the movement is immediately legible.*

Acceptance criteria:
- Given a vehicle with two or more sightings, when its trajectory is requested, then camera locations are plotted as markers and consecutive sightings joined by a polyline.
- Given a trajectory segment, when it is rendered, then its colour encodes match confidence: confirmed, probable, or ambiguous.
- Given a marker is clicked, when the detail panel opens, then it shows the best-shot crop, timestamp, camera name, plate read (if any), and the match decision for that hop.
- Given a trajectory is animated, when playback runs, then a marker traverses the polyline in chronological order at a controllable speed.

---

**F-10 · Vehicle search**

*As an investigating officer, I want to find a vehicle by plate, partial plate, or time window so that I can start a reconstruction from what I actually know.*

Acceptance criteria:
- Given a full plate, when searched, then matching vehicles are returned ranked by recency.
- Given a partial plate of 3 or more characters, when searched, then vehicles whose canonical plate contains that substring are returned.
- Given a time range and an optional camera filter, when searched, then all vehicles sighted in that window are returned, paginated.
- Given a search returns nothing, when results render, then the empty state explains what was searched and offers a widened query.

---

**F-11 · Operator confirmation of links**

*As an operator, I want to accept or reject the system's proposed links so that the final trajectory reflects human judgement.*

Acceptance criteria:
- Given a proposed link, when the operator confirms it, then the decision status becomes `CONFIRMED`, the acting user and timestamp are recorded, and the trajectory segment re-renders as confirmed.
- Given a proposed link, when the operator rejects it, then the sighting is detached from that vehicle and re-resolved, excluding the rejected candidate.
- Given a rejection splits a trajectory, when re-resolution completes, then the detached sighting either joins another vehicle or becomes a new vehicle, and the map updates.

---

**F-12 · Camera topology management**

*As an administrator, I want to register cameras and define the road connections between them so that the feasibility gate has a graph to reason over.*

Acceptance criteria:
- Given the admin creates a camera, when it is saved, then code, name, latitude, longitude, and stream source are persisted and the camera appears on the map.
- Given the admin creates an edge, when it is saved, then distance, minimum transit time, and maximum transit time are persisted, with bidirectionality optional.
- Given an edge is created without an explicit minimum transit time, when it is saved, then a default is derived from great-circle distance at 80 km/h, and the derived value is flagged as an estimate.
- Given a camera has no edges, when the admin views it, then a warning states that vehicles at this camera cannot be linked to any other.

---

**F-13 · Authentication and roles**

*As an administrator, I want access controlled by role so that plate data is not visible to everyone.*

Acceptance criteria:
- Given valid credentials, when a user logs in, then a short-lived access token and an httpOnly refresh cookie are issued.
- Given an expired access token, when the client calls a protected route, then the refresh flow issues a new access token transparently, once; a second consecutive failure redirects to login.
- Given a user with the `viewer` role, when they view a sighting, then plate text is masked except for the last four characters.
- Given any search or export, when it executes, then an audit-log entry is written recording the user, action, target, and time.

---

### 5.2 Post-MVP — Explicitly out of scope for the hackathon round

These are listed so that the boundary is unambiguous and so that the roadmap slide has real content. **None should be built before every MVP item is verified.**

- **P-01 · Watchlist and live alerting.** Register a plate or vehicle; receive a notification on next sighting.
- **P-02 · Live RTSP ingestion.** Replace file playback with real camera streams and hardware decoding.
- **P-03 · Fine-tuned Indian-context models.** Fine-tune the detector on IDD and the Re-ID backbone on FGVD plus self-captured footage.
- **P-04 · Persistent vector index.** Replace in-memory FAISS with an on-disk index or Qdrant/Milvus for multi-day retention.
- **P-05 · Trajectory prediction.** Given a partial route, predict likely next cameras from historical flow.
- **P-06 · Image-query search.** Upload a photo of a vehicle and search by appearance alone.
- **P-07 · Multi-tenant deployment.** Per-city isolation with separate data boundaries.
- **P-08 · Edge deployment.** Run detection, tracking, and embedding on a Jetson-class device at the camera, sending only sightings upstream.

---

## 6. Non-Functional Requirements

### Performance

| ID | Requirement | Target | How measured |
|---|---|---|---|
| NFR-P1 | Single-camera pipeline throughput | ≥ 15 FPS at 720p on one CUDA GPU; ≥ 5 FPS CPU-only | `scripts/benchmark_pipeline.py` |
| NFR-P2 | FAISS top-50 query latency | p95 < 50 ms at 10,000 vectors | `scripts/benchmark_faiss.py` |
| NFR-P3 | End-to-end sighting to dashboard | p95 < 500 ms | Timestamp delta, worker emit to client receive |
| NFR-P4 | Trajectory API response | p95 < 200 ms for a 20-sighting vehicle | `pytest-benchmark` |
| NFR-P5 | Frontend time-to-interactive | < 2 s on the demo laptop | Lighthouse, local build |
| NFR-P6 | Concurrent WebSocket clients | ≥ 10 without event loss | Load script |

### Security

- NFR-S1 — Passwords hashed with bcrypt, cost factor 12. Plaintext passwords never logged.
- NFR-S2 — Access tokens are JWT HS256, 30-minute expiry, held in memory only. Never in `localStorage`.
- NFR-S3 — Refresh tokens are opaque random strings, stored hashed, delivered as httpOnly + SameSite=Strict cookies, 7-day expiry, rotated on use.
- NFR-S4 — Every state-changing endpoint enforces role. Authorisation is checked server-side; UI hiding is not access control.
- NFR-S5 — All request bodies validated by Pydantic. Rejected input returns 422 with field-level detail.
- NFR-S6 — CORS restricted to the configured frontend origin. No wildcard.
- NFR-S7 — Secrets loaded from environment. No credential is ever committed; `.env.example` carries names and dummy values only.

### Privacy

Vehicle movement data is sensitive personal information. The system handles it accordingly, and this is a scored talking point under Indian regulation.

- NFR-PR1 — Plate text is masked to the last four characters for the `viewer` role.
- NFR-PR2 — Every search, export, and trajectory view is written to the audit log with actor, target, and timestamp.
- NFR-PR3 — Retention is configurable, default 30 days; a purge job deletes sightings and crops past retention.
- NFR-PR4 — Best-shot crops contain vehicles only. No full-frame captures containing bystanders or pedestrians are retained.
- NFR-PR5 — The architecture supports data minimisation at the edge: in the target deployment, only sightings leave the camera site, not video.

### Accessibility

- NFR-A1 — Text meets WCAG AA contrast (4.5:1 body, 3:1 large). Verified against the design tokens.
- NFR-A2 — All interactive elements reachable by keyboard with a visible focus ring. No focus traps outside modals.
- NFR-A3 — Match confidence is never encoded by colour alone; a text label and an icon accompany every colour signal.
- NFR-A4 — Map markers and controls have accessible names. The trajectory is available as a chronological table, not only as a map.
- NFR-A5 — `prefers-reduced-motion` disables trajectory animation and transitions.

### Scalability

- NFR-SC1 — Camera workers are independent processes; adding a camera adds a process, requiring no change to existing ones.
- NFR-SC2 — Data access is confined to a repository layer, so SQLite can be replaced by PostgreSQL without touching business logic.
- NFR-SC3 — The vector index sits behind an interface (`VectorIndex`) so FAISS can be swapped for a persistent store without touching the matcher.
- NFR-SC4 — Configuration is environment-driven. No hostname, path, or threshold is hardcoded.

### Reliability

- NFR-R1 — A worker failure does not stop other workers or the backend.
- NFR-R2 — Backend restart rebuilds the FAISS index from embeddings persisted in the database on startup.
- NFR-R3 — WebSocket clients reconnect automatically with exponential backoff, capped at 30 s.
- NFR-R4 — A failed model load produces a clear startup error naming the missing weight file, not a runtime crash mid-demo.

---

## 7. Success Criteria and Key Metrics

### 7.1 Accuracy

Reported using standard MTMC metrics. **Accuracy is not reported** — for an identity-assignment task with heavy class imbalance it is misleading, and evaluators who know the field will notice.

| Metric | What it measures | Target on demo set | Notes |
|---|---|---|---|
| **IDF1** | Harmonic mean of identity precision and recall across cameras | ≥ 0.55 | Primary headline metric |
| **IDP / IDR** | Identity precision and recall separately | Reported, unbounded | Precision matters more here; a false merge is worse than a missed link |
| **MOTA** | Single-camera tracking quality | ≥ 0.65 | Diagnoses whether errors come from tracking or from matching |
| **Rank-1 / mAP** | Re-ID retrieval quality in isolation | Rank-1 ≥ 0.60 | Isolates the embedding from the full pipeline |
| **Plate read rate** | Fraction of sightings yielding a structurally valid plate | Reported honestly | Expected to be low; that is the point of the project |
| **False-merge rate** | Distinct vehicles wrongly assigned one ID | ≤ 5% | The "White Maruti" failure, measured directly |
| **Gate rejection count** | Matches blocked by spatio-temporal filtering | Reported | Direct evidence that the differentiating component does work |

The last two rows form the core evaluation argument: run the pipeline with the feasibility gate disabled, then enabled, and show the false-merge rate falling. That single ablation is the strongest slide in the deck, because it isolates the contribution of the one component nobody else has built.

### 7.2 Demo success

The internal round is won or lost on the demo. These are the criteria that matter on the day:

- **D-1** — A vehicle is tracked across at least 3 cameras and its trajectory renders as a connected polyline.
- **D-2** — At least one trajectory hop is bridged by visual Re-ID where the plate was unreadable. This is the money shot and must be reproducible on demand.
- **D-3** — At least one visually similar vehicle is correctly rejected by the feasibility gate, with the rejection reason and numbers shown on screen.
- **D-4** — The full flow — search a plate, view a trajectory, inspect a hop's evidence, confirm a link — completes in under 90 seconds of live interaction.
- **D-5** — Zero crashes across three consecutive complete runs of the demo script.
- **D-6** — The demo runs entirely offline. No dependency on venue wifi, external map tiles, or any hosted API.

D-6 is not a nicety. Venue connectivity fails, and a demo that requires the internet is a demo that may not happen.

### 7.3 Engineering health

- **E-1** — 100% of MVP acceptance criteria pass their verification gate.
- **E-2** — Test coverage ≥ 70% on `backend/app/services/` — the matching logic specifically, since it is where correctness lives.
- **E-3** — Zero TypeScript `any` in `frontend/src/`, enforced by lint.
- **E-4** — Every dependency present in `requirements.txt` or `package.json` is one listed in `techspec.md`.
- **E-5** — A clean clone reaches a running demo by following `README.md` alone, in under 15 minutes.

---

## 8. Assumptions

1. Video sources are pre-recorded MP4 files for the demo; live RTSP is deferred to P-02.
2. The camera topology graph is authored manually. Automatic topology learning from traffic flow is out of scope.
3. Camera coordinates are approximate; the feasibility gate uses great-circle distance with a road-winding factor, not routed road distance.
4. At least one CUDA GPU is available for the build. A CPU fallback path exists and must work, at reduced FPS, in case the demo machine has no GPU.
5. Demo footage covers 3 to 6 cameras over 10 to 30 minutes of wall-clock time.
6. The evaluation is a presentation with a live demo, not a deployment. Production hardening is explicitly not a goal.

## 9. Out of Scope

- Facial recognition or occupant identification of any kind. Not attempted, not designed for.
- Integration with government vehicle registration databases.
- Automated enforcement actions, ticketing, or penalty issuance.
- Mobile applications.
- Any claim that an output constitutes a legal identification.
