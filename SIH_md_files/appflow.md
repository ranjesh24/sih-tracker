# appflow.md — Application Flow

**Project:** Marg (SIH26127)
**Version:** 1.0
**Companion docs:** `prd.md`, `techspec.md`, `design.md`

---

## 1. Route Map

| Route | Screen | Min role | Redirect when unauthorised |
|---|---|---|---|
| `/login` | Sign in | public | → `/` if already authenticated |
| `/` | Live wall | viewer | → `/login?next=/` |
| `/search` | Vehicle search | viewer | → `/login?next=/search` |
| `/vehicles/:vehicleId` | Trajectory detail | viewer | → `/login?next=…` |
| `/vehicles/:vehicleId/sightings/:sightingId` | Evidence panel (deep link) | viewer | → `/login?next=…` |
| `/review` | Ambiguous match queue | operator | → `/` with a toast explaining the role requirement |
| `/cameras` | Camera and topology admin | admin | → `/` with a toast |
| `/cameras/:cameraId` | Camera detail and edges | admin | → `/` with a toast |
| `*` | Not found | — | — |

Unauthorised access to an operator or admin route sends the user home with a toast, rather than to a 403 page. A dead-end error screen for someone who simply clicked a link they cannot use is worse than a redirect that explains itself and leaves them somewhere useful.

---

## 2. Application Bootstrap

Runs before any route renders. Every subsequent journey assumes it has completed.

```
App mounts
  │
  ├─ authStore.accessToken is in memory?
  │    ├─ No  → POST /api/v1/auth/refresh   (httpOnly cookie sent automatically)
  │    │         ├─ 200 → store token + user, continue
  │    │         └─ 401 → clear state, render /login
  │    └─ Yes → continue
  │
  ├─ GET /api/v1/system/health
  │    └─ Unreachable → render BackendUnavailable screen with a retry button.
  │       Do not render the app shell over a dead backend; an interface full of
  │       empty panels reads as broken data rather than a broken connection.
  │
  ├─ Prefetch GET /api/v1/cameras (React Query)
  │
  └─ Open WebSocket /api/v1/ws/events?token=…
       ├─ Open   → ConnectionIndicator: live
       ├─ Closed → backoff reconnect 1s, 2s, 4s, 8s, 16s, capped 30s
       └─ 4001 (bad token) → attempt one refresh, reconnect once, then show
                             ConnectionIndicator: disconnected with manual retry
```

A page refresh always loses the access token, because it is held in memory by design (`techspec.md` §4.2). The refresh call at bootstrap is what makes that invisible to the user. It must complete before the first route renders, or a protected route will flash the login screen and then redirect — a visible flicker on every reload.

---

## 3. Journey A — Operator investigates a plate

The primary journey and the one the demo follows.

### A1 · Sign in

**Route:** `/login`

Single centred card. Email, password, sign-in button. No registration link — accounts are provisioned by an administrator, and offering a sign-up path that does not exist is a dead end.

```
Submit
  → validate client-side (email shape, password non-empty)
  → POST /api/v1/auth/login
      ├─ 200 → store access token + user in memory
      │        redirect to ?next= param, or / if absent
      ├─ 401 → inline error above the form:
      │        "Email or password is incorrect."
      │        Password field cleared, email retained, focus moves to password
      ├─ 429 → "Too many attempts. Try again in 15 minutes."
      │        Submit disabled with a live countdown
      └─ network failure → "Cannot reach the server. Check that the backend
                            is running on port 8000."
```

The 401 message does not distinguish between an unknown email and a wrong password. Distinguishing them lets an attacker enumerate valid accounts.

### A2 · Live wall

**Route:** `/`

Landing screen after sign-in. Layout: camera grid on the left (roughly two thirds), live event feed on the right.

**On mount**
- `GET /api/v1/cameras` — hydrated from prefetch, so the grid renders immediately.
- `GET /api/v1/system/stats` — header counters.
- WebSocket already open; events stream into `liveStore`.

**Behaviour**
- Each tile shows the camera's current frame with detection boxes and local track IDs overlaid.
- A `sighting.created` event flashes the originating tile's border for 600 ms and prepends a row to the event feed, capped at 100 rows in memory.
- A `match.rejected` event appends a distinctly-styled row showing the rejection reason and its numbers. These are visually differentiated from matches because they are the more interesting event, not an error.
- Clicking an event row → `/vehicles/:vehicleId`.
- Clicking a tile → filters the event feed to that camera. Clicking again clears the filter.

**Empty state — no cameras registered**

Full-panel message: "No cameras registered yet." Admin sees a "Register a camera" button linking to `/cameras`. Operator and viewer see "Ask an administrator to register cameras." Never show an empty grid with no explanation.

**Empty state — cameras registered, pipeline not running**

Tiles render as placeholders with the camera name and an offline status. The event feed reads: "No events yet. Start the pipeline with `./scripts/demo.sh` to begin processing." Naming the actual command is the single most useful thing this state can do — the person seeing it is almost always a teammate who forgot to start the workers.

### A3 · Search

**Route:** `/search`

Three search modes as tabs, since the officer's starting knowledge varies: full plate, partial plate, or time window.

```
Plate tab
  → input, uppercase-normalised as typed, separators stripped
  → structural validity indicated inline but never blocking; non-standard
    plates exist and must remain searchable
  → GET /api/v1/vehicles?plate=BR01AB1234

Partial tab
  → minimum 3 characters, enforced with a hint rather than a disabled button
  → debounced 300 ms
  → GET /api/v1/vehicles?plate_partial=AB12

Time window tab
  → from/to datetime, optional camera multi-select, optional vehicle class
  → GET /api/v1/vehicles?from=…&to=…&camera_id=…
```

Results are a table: thumbnail, plate (masked for viewers), class, sighting count, camera span, first and last seen. Sorted by last seen descending.

Row click → `/vehicles/:vehicleId`.

**Empty state:** state what was searched and offer a widening action. "No vehicles match plate BR01AB1234 between 09:00 and 10:00." with a "Search all time" button. An empty state that only says "No results" makes the user re-derive their own query.

**Loading:** skeleton rows matching the final table's dimensions. Not a spinner — a spinner discards the layout and causes a jump when content arrives.

### A4 · Trajectory detail — the core screen

**Route:** `/vehicles/:vehicleId`

```
GET /api/v1/vehicles/:id
GET /api/v1/vehicles/:id/trajectory
```

Three regions: map (top-left, largest), sighting timeline (left column below the map), evidence panel (right column).

**Map**
- Camera markers for every camera in the trajectory, numbered in chronological order — the numbering is legitimate here because the content genuinely is a sequence.
- Polyline segments joining consecutive sightings, styled by confidence:
  - **Confirmed** (operator-confirmed, or plate-exact) — solid, accent colour.
  - **Probable** (auto-matched above threshold) — solid, thinner, muted.
  - **Ambiguous** (queued for review) — dashed, amber, with a warning icon at the midpoint.
- Playback controls: play, pause, speed (1×/2×/4×), scrub. A marker traverses the route chronologically. Disabled and hidden entirely when `prefers-reduced-motion` is set.
- Clicking a marker selects that sighting and loads it into the evidence panel.

**Sighting timeline**
Vertical list, chronological. Each entry: thumbnail, camera name, timestamp, elapsed since previous sighting, and a match-method badge. Selecting an entry syncs the map marker. Map and timeline selection are always bidirectional — clicking either updates both.

**Evidence panel** — the trust surface

For the selected sighting:
- Best-shot crop, full width of the panel.
- Plate crop and OCR text with per-read confidence, or an explicit "No plate detected" — an absent plate is information, not a blank field.
- Camera, timestamp, vehicle class, detection confidence.
- **Match explanation**, which is the reason the panel exists:

```
Matched to this vehicle by  VISUAL RE-ID
  Visual similarity      0.87
  Plate agreement          —     (no plate read at this sighting)
  Temporal plausibility  0.91
  ─────────────────────────────
  Fused score            0.88     threshold 0.72

  Transit from CAM-01: 412 s elapsed, feasible window 180–1450 s

  Also considered:
    Vehicle #A47F   visual 0.84   rejected: TEMPORAL_TOO_FAST
                    (14 s elapsed, minimum feasible 312 s)
```

The "also considered" block is what separates this from a black box. It shows the system evaluated alternatives and shows precisely why each was discarded. During the demo this is the panel to sit on, because it answers the question a judge will ask before they ask it.

- **Operator actions** (operator and admin only): "Confirm link" and "Reject link". Viewers see the panel without the buttons — read-only rather than disabled controls, since disabled buttons invite clicking.

### A5 · Confirm or reject a link

```
Confirm
  → POST /api/v1/match-decisions/:id/confirm
  → optimistic UI: segment restyles to confirmed immediately
  → on success: toast "Link confirmed."
  → on failure: revert, toast "Could not confirm the link. Try again."

Reject
  → confirmation dialog: "Reject this link? The sighting will be detached
    from this vehicle and matched again."
  → POST /api/v1/match-decisions/:id/reject
  → backend detaches the sighting, re-runs resolution excluding the rejected
    candidate, returns the new assignment
  → trajectory refetches; the sighting either joins another vehicle or becomes
    a new one
  → toast: "Link rejected. Sighting reassigned to vehicle #B12C."
    with an "Open" action
```

Rejection is destructive to the current view — the trajectory the user is looking at changes shape under them. It gets a confirmation dialog. Confirmation is additive and reversible, so it does not.

### A6 · Review queue

**Route:** `/review` · operator and admin

`GET /api/v1/match-decisions/ambiguous`

Sightings where the top two candidates scored within the ambiguity margin. This is the "White Maruti" case surfaced as a work item rather than resolved by a coin flip.

Each row: the sighting's crop alongside both candidate vehicles' crops, side by side, with scores. Actions: assign to candidate A, assign to candidate B, or create a new vehicle.

Side-by-side crops are the whole design. A human distinguishes two white hatchbacks in about two seconds by noticing a sticker, a dent, or a roof rack — details the embedding compressed away. The interface's job is to put the images next to each other and get out of the way.

**Empty state:** "No ambiguous matches. Everything the system has seen was resolved confidently." — a good state, worded as one.

---

## 4. Journey B — Administrator configures topology

### B1 · Camera list

**Route:** `/cameras` · admin

Map on the left with every camera and edge drawn; table on the right. Table columns: code, name, coordinates, edge count, status, last sighting.

A camera with zero edges shows a warning badge and a tooltip: "No connections. Vehicles seen here cannot be linked to other cameras." This is the single most common configuration error and the one whose symptom — trajectories that never join up — looks like a model failure rather than a missing edge.

### B2 · Register a camera

Dialog, not a separate route. Fields: code (uppercase, unique), name, latitude, longitude, heading, location label, stream URI.

Coordinates are also settable by clicking the map, which is faster and less error-prone than typing decimal degrees.

```
Submit
  → POST /api/v1/cameras
      ├─ 201 → close, refetch list, toast "Camera CAM-05 registered."
      │        follow-up prompt: "Connect it to nearby cameras?" → opens edge form
      ├─ 409 → inline on the code field: "A camera with this code already exists."
      └─ 422 → field-level errors from the error payload's details array
```

The follow-up prompt exists because a camera without edges is inert, and the moment after creating one is the moment the admin is thinking about where it sits relative to the others.

### B3 · Create an edge

Dialog. Pick from-camera and to-camera, or click two markers on the map.

```
On camera pair selected
  → POST /api/v1/camera-edges/estimate  { from_camera_id, to_camera_id }
  → returns derived distance_m, min_transit_seconds, max_transit_seconds
  → fields pre-fill with the estimates, each flagged as estimated
  → admin overrides any of them; overridden fields lose the estimated flag
  → bidirectional checkbox, default on
```

Pre-filling from a physics estimate and letting the admin correct it is the right order. Asking someone to type "minimum transit time in seconds" from a blank field invites a guess, and a bad transit window silently poisons every match through that edge.

```
Submit
  → POST /api/v1/camera-edges
      ├─ 201 → close, redraw graph, toast "CAM-01 ↔ CAM-04 connected."
      ├─ 409 → "These cameras are already connected." with an "Edit" action
      └─ 422 → field errors; min_transit must be less than max_transit
```

### B4 · Reset between demo runs

**Route:** `/cameras`, in an overflow menu · admin

Dialog with typed confirmation: the admin types `RESET` to enable the button.

```
POST /api/v1/system/reset-demo
  → deletes sightings, vehicles, match_decisions, crop files
  → keeps cameras, edges, users, audit log
  → clears the FAISS index
  → broadcasts system.reset over the WebSocket; all clients clear live state
  → toast "Demo data cleared. Cameras and users kept."
```

The typed confirmation is not bureaucracy. This is a destructive action sitting in an admin menu that will be opened under presentation pressure, and a misclick between run two and run three costs the demo.

---

## 5. Journey C — Viewer with masked data

Identical navigation, reduced surface. Documented separately because the differences must be verified during testing, not assumed.

| Screen | Viewer sees | Viewer does not see |
|---|---|---|
| Live wall | All feeds, all events | Full plate text — masked to `••••••1234` |
| Search | Plate and time search | Full plates in results |
| Trajectory | Full route, timeline, crops | Full plates; no confirm/reject buttons |
| Evidence | Match explanation and scores | Nothing hidden — the reasoning is not sensitive |
| Review queue | — | Route not reachable; redirect home with a toast |
| Cameras | — | Route not reachable; redirect home with a toast |

Masking is applied server-side by the response serialiser (`techspec.md` §4.4). The frontend renders whatever it receives and performs no masking of its own — client-side masking would mean the unmasked value crossed the wire, which is the thing being prevented.

The match explanation is deliberately *not* restricted. Understanding why the system linked two sightings does not expose personal data, and a viewer who can see a trajectory but not its justification is being asked to trust it blindly.

---

## 6. Edge Cases and Error Handling

### 6.1 Authentication

| Situation | Behaviour |
|---|---|
| Access token expires mid-session | Axios response interceptor catches 401, calls `/auth/refresh` once, replays the original request. Transparent to the user. |
| Refresh fails | Clear auth state, redirect to `/login?next=<current path>`, toast "Your session expired. Sign in to continue." |
| Two requests 401 simultaneously | Refresh calls are deduplicated by a module-level promise. One refresh, both requests replayed. Without this, concurrent 401s trigger parallel refreshes and token rotation revokes the second one's result. |
| Refresh token reuse detected | Server revokes all of the user's tokens. Client receives 401, redirects to login with "Your session was ended for security reasons." |
| User's role changes while signed in | Next access-token refresh carries the new role. Route guards re-evaluate on the next navigation. |
| Sign-in on the login screen while already authenticated | Redirect to `/` immediately; do not render the form. |

### 6.2 Network and backend

| Situation | Behaviour |
|---|---|
| Backend unreachable at bootstrap | Full-screen `BackendUnavailable` with the configured API URL, a retry button, and the start command. |
| Backend dies mid-session | React Query surfaces errors per panel. Each panel shows an inline error with a retry, not a full-screen takeover — an operator watching feeds should not lose the whole screen because one request failed. |
| WebSocket drops | `ConnectionIndicator` → reconnecting. Backoff 1/2/4/8/16/30 s. Live feed shows "Reconnecting. Historical data is still available." REST-backed views keep working. |
| WebSocket reconnects after a gap | Client calls `GET /api/v1/sightings?from=<last received timestamp>` to backfill missed events, then resumes streaming. Without backfill, the gap is invisible and the operator believes they saw everything. |
| Slow request (> 10 s) | Timeout, inline error, retry. No infinite spinner. |
| 500 from any endpoint | Toast "Something went wrong on the server." plus the `request_id`, which is copyable. The ID maps to a server log line. |

### 6.3 Data

| Situation | Behaviour |
|---|---|
| Vehicle has exactly one sighting | Map shows a single marker, no polyline. Timeline shows one entry. Panel: "Seen once. No trajectory to reconstruct yet." Not an error. |
| Vehicle ID in URL does not exist | 404 screen: "No vehicle with this ID." with a link to search. |
| Sighting has no plate | Evidence panel shows "No plate detected" and the plate-agreement row shows an em dash. Absence is displayed, not hidden. |
| Sighting crop file missing on disk | Placeholder with "Image unavailable" and the sighting ID. Match explanation still renders — losing an image must not blank the reasoning. |
| Camera deleted while a trajectory references it | Cameras are soft-deleted (`is_active = false`). Historical sightings keep resolving. The marker renders muted with "Camera decommissioned." |
| Two cameras at identical coordinates | Markers overlap. Apply a small deterministic offset based on camera ID so both remain clickable. |
| Trajectory with more than 50 sightings | Timeline virtualises. Map draws all segments but disables playback with "Trajectory too long to animate." |
| Clock skew between workers | Backend records `received_at` alongside the worker-supplied `frame_timestamp` and uses `frame_timestamp` for gating. A skew of more than 5 s triggers a `system.error` broadcast — silent skew produces false `TEMPORAL_TOO_FAST` rejections and looks like a matching bug. |

### 6.4 Pipeline

| Situation | Behaviour |
|---|---|
| Worker crashes | Camera tile shows offline with the last frame dimmed and a timestamp. Other cameras unaffected. `system.error` broadcast names the camera. |
| Worker sends a sighting for an unregistered camera | 404 from ingest with `CAMERA_NOT_FOUND`. Worker logs and continues; it does not retry, since the camera will not appear spontaneously. |
| Ingest key wrong | 401 from ingest. Worker logs a fatal error naming the mismatch and exits — retrying with a bad key forever produces a confusing silence rather than a clear failure. |
| Video file ends | Worker emits final tracklets, sends a heartbeat with `status: completed`, exits cleanly. Tile shows completed, not offline. |
| Two workers ingest concurrently | Ingest is serialised through a single async lock around resolution. FAISS is not thread-safe for concurrent add and search, and resolution reads the index it is about to write. |
| Model weights missing at startup | Worker exits before processing with "Model weights not found at ./models/yolov8n.pt. Run scripts/download_models.py." Fail at startup, not on frame 400. |

### 6.5 Permissions

| Situation | Behaviour |
|---|---|
| Viewer navigates to `/review` | Redirect to `/`, toast "The review queue requires operator access." |
| Viewer calls a protected endpoint directly | 403 with `INSUFFICIENT_ROLE`. Server-side enforcement is authoritative; the route guard is convenience only. |
| Operator opens `/cameras` | Redirect to `/`, toast "Camera management requires administrator access." |
| Role changes to a lower level mid-session | Current view keeps rendering until the next navigation or refetch, then guards apply. Acceptable; the server rejects any privileged action in the meantime. |

### 6.6 Empty and first-run states

| Screen | Empty state |
|---|---|
| Live wall, no cameras | "No cameras registered yet." Admin gets a create button; others get a message naming who to ask. |
| Live wall, no events | "No events yet. Start the pipeline with `./scripts/demo.sh`." |
| Search, no query yet | Neutral prompt describing the three search modes. Not an error, not a blank panel. |
| Search, no results | Restates the query and offers a widening action. |
| Trajectory, single sighting | "Seen once. No trajectory to reconstruct yet." |
| Review queue, empty | "No ambiguous matches. Everything the system has seen was resolved confidently." |
| Cameras, none registered | "Register your first camera to start building the topology." with a create button. |
| Camera detail, no edges | "This camera has no connections. Vehicles seen here cannot be linked to other cameras." with a connect button. |

Empty states follow one rule, from `design.md`: state the situation plainly, then offer the next action. Never apologise, never leave a blank rectangle.

---

## 7. State Transition Reference

```
Sighting lifecycle
  created (ingest)
    └→ resolving
         ├→ matched      (assigned, decision MATCHED)
         ├→ ambiguous    (queued for review, no assignment)
         └→ new_vehicle  (new identity created)

MatchDecision lifecycle
  proposed
    ├→ confirmed  (operator confirmed)
    ├→ rejected   (operator rejected → sighting re-resolves)
    └→ superseded (a later decision replaced this one)

Trajectory segment rendering
  confirmed   → solid, accent, 3 px
  probable    → solid, muted, 2 px
  ambiguous   → dashed, amber, 2 px + warning marker at midpoint
  rejected    → not rendered

WebSocket connection
  connecting → open → [closed → reconnecting → open]
                          └→ failed (after 6 attempts, manual retry offered)
```
