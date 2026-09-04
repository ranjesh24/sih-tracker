# mapsimulation.md — Incremental Trajectory Map (Leaflet + OSM)

**Project:** Marg (SIH26127) — MTMC vehicle trajectory reconstruction
**Screen:** Trajectory Map (screen 2 of 3)
**Owner:** frontend (B), contract owned by backend (Sahil)
**Status:** spec — not yet implemented

---

## 1. Objective

The Trajectory Map must **grow one hop at a time**. As each of the 4 camera videos is
processed and ingested, the map gains one more marker and extends the polyline to it.
After all 4 videos, the map shows 4 numbered markers connected by a single ordered
trajectory for one `global_id`.

This is the money shot for the judges. It must never fail live.

**Non-goals:** no vehicle icon sliding along the road, no route-snapping to the road
network, no time-scrubber. Markers + straight polyline segments only. This is a bounded
exception to the "no playback animation" scope lock: we reveal points as data arrives,
we do not animate motion between them.

---

## 2. Two drivers, one renderer

The single hardest requirement: **live mode and simulation mode must render through the
exact same component.** Only the data source differs.

| Mode | Trigger | Source | Use |
|---|---|---|---|
| `live` | default | polls backend `GET /api/v1/vehicles/{global_id}/trajectory` | real demo, pipeline running |
| `sim` | `?mode=sim` in URL | static `public/demo/trajectory_demo.json`, advanced by timer | stage fallback, dev without backend |

`<TrajectoryMap>` accepts a resolved `path: PathPoint[]` and nothing else. The hook that
produces `path` is swapped. If the two modes ever diverge visually, the spec is violated.

**The sim fixture is not hand-written.** It is a real backend response, exported once from
a successful run via `scripts/export_demo_trajectory.py`, committed to the repo. If the
live pipeline dies on stage we fall back to a recording of a real run, not a fake.

---

## 3. Data contract

### 3.1 Camera registry

Cameras are static for the demo. Source from backend `GET /api/v1/cameras` if that
endpoint exists; otherwise hardcode in `src/data/cameras.ts` with the same shape.

```ts
export interface Camera {
  camera_id: string;      // "CAM_01"
  name: string;           // "Kanke Road / Rock Garden approach"
  lat: number;
  lon: number;
  bearing_deg?: number;   // direction camera faces, optional
}
```

**Placeholder coordinates — REPLACE with real filming GPS before the demo.**
Read them off the phone at each shoot location; do not eyeball them from a map.

```ts
export const CAMERAS: Camera[] = [
  { camera_id: "CAM_01", name: "Site 1", lat: 23.3866, lon: 85.3200 },
  { camera_id: "CAM_02", name: "Site 2", lat: 23.3721, lon: 85.3238 },
  { camera_id: "CAM_03", name: "Site 3", lat: 23.3585, lon: 85.3290 },
  { camera_id: "CAM_04", name: "Site 4", lat: 23.3441, lon: 85.3096 },
];
```

A `camera_id` present in a trajectory but missing from the registry is a hard error:
log it, skip the point, show a toast. Never silently drop a hop.

### 3.2 Trajectory response

```ts
type GateStatus = "origin" | "feasible" | "borderline" | "inferred";

interface PathPoint {
  seq: number;              // 0-indexed, strictly increasing
  camera_id: string;
  ts: number;               // epoch seconds, SHARED CLOCK
  sighting_id: string;
  plate_text: string | null;
  plate_confidence: number | null;
  match_score: number | null;   // null for seq 0
  gate_status: GateStatus;
  travel_time_s: number | null;
  expected_min_s: number | null;
  expected_max_s: number | null;
  best_shot_url: string | null;
}

interface TrajectoryResponse {
  global_id: string;
  plate: string | null;         // consensus plate across the track
  path: PathPoint[];            // sorted by seq
  complete: boolean;            // backend has no more pending ingests
}
```

Frontend **must** sort by `seq` on receipt and must not assume the array arrives sorted.
Ties or duplicate `seq` values: keep the first, log a warning.

> Depends on the shared-epoch task. If camera clocks are skewed, `travel_time_s` is
> garbage and the gate badges will read wrong on stage. Verify before filming.

---

## 4. Files

```
frontend/src/
  data/cameras.ts                 # registry + camera_id -> LatLng lookup
  hooks/useLiveTrajectory.ts      # polling driver
  hooks/useSimTrajectory.ts       # timer driver over static fixture
  hooks/useTrajectory.ts          # picks driver from ?mode=, returns identical shape
  components/map/TrajectoryMap.tsx
  components/map/CameraMarker.tsx
  components/map/TrajectoryLine.tsx
  components/map/HopTooltip.tsx
frontend/public/demo/trajectory_demo.json
frontend/public/tiles/{z}/{x}/{y}.png    # self-hosted OSM, offline
```

---

## 5. Rendering rules

### 5.1 Markers

- One marker per path point, labelled with `seq + 1` (1, 2, 3, 4).
- Same camera appearing twice = two markers at the same LatLng. Offset the second by
  ~15px in screen space so both are clickable, or render a stacked badge. Do not merge.
- Marker colour by `gate_status`:
  - `origin` — neutral / slate
  - `feasible` — green
  - `borderline` — amber
  - `inferred` — grey, dashed outline
- Click a marker → opens the Evidence Panel for that `sighting_id`.
- Hover → `HopTooltip` with camera name, local time from `ts`, plate + confidence,
  `match_score`, and `travel_time_s` against `[expected_min_s, expected_max_s]`.

### 5.2 Polyline

- One `Polyline` per **segment** (between `seq n` and `seq n+1`), not one for the whole
  path. Per-segment styling is required and a single polyline can't do it.
- Segment style follows the **destination** point's `gate_status`: solid green for
  feasible, solid amber for borderline, dashed grey for inferred.
- Weight 4, opacity 0.85. Add a subtle white casing underneath (weight 7, opacity 0.4)
  so the line stays readable over dense OSM tiles.
- Direction: small arrow marker at segment midpoint, rotated to the bearing. If
  `leaflet-polylinedecorator` is a hassle, use a rotated divIcon — do not skip direction,
  the judges need to see which way the vehicle went.

### 5.3 Reveal

When `path.length` increases:

1. Append the new marker with a 300ms fade+scale-in (CSS on the divIcon, no JS animation loop).
2. Draw the new segment.
3. Fit bounds — see below.

Never re-mount existing markers or the whole `MapContainer` on update. Key markers by
`sighting_id`, key segments by `${from.sighting_id}->${to.sighting_id}`. Re-mounting
causes the whole map to flash on every poll, which looks broken on a projector.

### 5.4 Bounds

- On each new point: `map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16, animate: true })`.
- Track `userInteracted` (set on `dragstart` / `zoomstart` by the user). Once true, stop
  auto-fitting and show a small "Recenter" button instead. Presenters pan the map; the
  map must not fight them.
- Single point (`path.length === 1`): `setView(point, 15)`, do not `fitBounds`.

---

## 6. Live driver — `useLiveTrajectory`

```ts
useLiveTrajectory(globalId: string): {
  path: PathPoint[];
  plate: string | null;
  status: "idle" | "polling" | "complete" | "error";
  received: number;   // path.length
  expected: number;   // 4 for the demo, from config
}
```

- Poll `GET /api/v1/vehicles/{globalId}/trajectory` every **2000ms**.
- Stop when `complete === true` **or** `path.length >= expected` **or** 3 consecutive
  network failures (then `status: "error"`, keep last good path on screen).
- Merge, don't replace: if a response somehow returns fewer points than we already have,
  keep the longer one. The map only ever grows during a demo run.
- Clean up the interval on unmount. Guard against overlapping in-flight requests.

Show `received / expected` as a "3 of 4 cameras" chip in the map header. This makes the
incremental fill legible to someone watching from ten feet away.

---

## 7. Sim driver — `useSimTrajectory`

- Loads `public/demo/trajectory_demo.json` once.
- Holds `step` state, starts at 1, advances every **3000ms** until `step === path.length`.
- Returns `path.slice(0, step)` — identical shape to the live hook.
- Exposes `play / pause / reset / stepForward`. Bind `reset` to a visible button and
  `stepForward` to the right-arrow key so the presenter can drive it manually if the
  auto-timer runs ahead of the narration.
- Add a small "SIM" badge in the map corner whenever `mode=sim`. We disclose the fallback;
  we do not pass a recording off as a live run if a judge asks.

---

## 8. Leaflet / OSM setup

- `react-leaflet` v4+ with React 19. `MapContainer` mounted once, never keyed on data.
- **Self-hosted tiles.** `TileLayer url="/tiles/{z}/{x}/{y}.png"`. Pre-download the bbox
  covering all 4 camera sites at **z13–z17** before the event. Venue wifi will not be
  there for you.
- Attribution string stays visible — OSM's licence requires it. `&copy; OpenStreetMap contributors`.
- Set `maxBounds` to the camera bbox padded ~2km, `maxBoundsViscosity: 0.8`, so a stray
  drag can't strand the presenter in an untiled grey void.
- `attributionControl` on, `zoomControl` on, `scrollWheelZoom` on.
- Self-host the marker icon assets; do not rely on the CDN default icon URLs (they 404
  offline and Leaflet's default-icon path bug will bite).

---

## 9. Edge cases

| Case | Behaviour |
|---|---|
| `path` empty | Map at default centre/zoom, empty-state text: "Waiting for first sighting." |
| Unknown `camera_id` | Skip point, warn in console, toast once. Do not crash. |
| Out-of-order `seq` | Sort on receipt. |
| Duplicate `seq` | Keep first, warn. |
| Same camera twice in path | Two offset markers, zero-length segment suppressed. |
| `plate_text` null | Show "no read" in tooltip, not an empty string or "null". |
| Backend 5xx | Retry with backoff (2s, 4s, 8s), then `status: "error"` + retry button. Existing path stays rendered. |
| Tiles fail to load | Grey background is acceptable; markers and lines must still render. Do not block on tiles. |
| Poll returns shorter path | Ignore, keep longer. |

---

## 10. Acceptance criteria

1. Starting from empty, ingesting videos 1→4 one at a time produces markers appearing
   one at a time, in order, with the polyline extending each time — no full-map reflow.
2. `?mode=sim` produces a visually identical sequence with no backend running.
3. Segment colour and dash correctly reflect `gate_status` from the response.
4. Direction arrows point from earlier to later `seq`.
5. Manual pan/zoom disables auto-fit; "Recenter" restores it.
6. With the network fully disconnected, `?mode=sim` still renders tiles, markers and lines.
7. Clicking any marker opens the Evidence Panel for the correct `sighting_id`.
8. Killing the backend mid-run leaves the last good path on screen with an error chip.

---

## 11. Demo runbook

1. Pre-flight: tiles cached, `trajectory_demo.json` present, camera coords match real sites.
2. Open Trajectory Map in `live`, backend up, path empty.
3. Run pipeline on video 1 → marker 1 appears. Narrate: single sighting, no association yet.
4. Video 2 → segment 1→2 draws. Narrate the gate: travel time vs feasible window, and
   that vision only ranked candidates the topology graph had already allowed.
5. Videos 3, 4 → full 4-hop trajectory.
6. If anything stalls for more than ~10s, switch the URL to `?mode=sim` and continue.
   Say out loud that this is a recorded run of the same pipeline.

---

## 12. Open items

- Real GPS coordinates for the 4 filming sites — blocks section 3.1.
- Shared epoch across cameras — blocks the travel-time badges in section 5.1.
- Confirm the exact `GET /api/v1/vehicles/{global_id}/trajectory` payload against
  `schema.md`; this spec proposes the shape, backend is the source of truth.
- Decide whether `expected` (4) comes from config or from a backend `expected_hops` field.
