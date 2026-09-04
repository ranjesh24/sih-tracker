# ml-pipeline architecture

Describes the code as it exists in `ml-pipeline/` at the time of writing. Where
this document and the specifications in `../SIH_md_files/` disagree, this
document describes what the code does; it is not a statement that the code is
correct.

Environment: Python 3.11.15, venv at `ml-pipeline/venv`. numpy 2.4.6,
OpenCV 5.0.0, torch 2.14.0, ultralytics 8.4.138, EasyOCR 1.7.2. Test suite:
121 tests.

---

## 1. Module inventory

### `src/`

| File | Lines | What it does | Internal deps | Third-party |
|---|---|---|---|---|
| `config.py` | 170 | `Settings` (pydantic-settings) holding every tunable value, plus the `get_settings()` cached singleton. Derived properties `TARGET_CLASS_IDS`, `REID_INPUT_SIZE_PX`, `SECONDS_PER_FRAME`. | none | pydantic, pydantic-settings |
| `types.py` | 148 | Frozen dataclasses `Detection`, `FrameSample`, `Tracklet`, `Sighting`, and the `VehicleClass` / `ResolutionStatus` / `MatchMethod` literals. | none | numpy |
| `video_source.py` | 203 | `VideoSource` wraps `cv2.VideoCapture` and yields `(frame_bgr, iso_timestamp)`. `frame_timestamp()` and `to_iso8601_utc()` are free functions. Raises `VideoSourceError`. | config | cv2, numpy |
| `detector.py` | 194 | `VehicleDetector` owns the single YOLO instance; `detect()` (predict) and `track()` (ByteTrack, `persist=True`) return `Detection` objects. `resolve_device()` validates the configured device. Raises `DetectorError`. The only module importing `ultralytics`. | config, types | numpy, torch, ultralytics |
| `tracker.py` | 255 | `TrackletBuffer` holds open tracks, buffers a `FrameSample` per track per frame, finalises on `TRACK_LOST_FRAMES` absence, discards below `TRACKLET_MIN_FRAMES`. `VehicleTracker` binds buffer to detector and video source, yielding tracklets as a generator. `_OpenTrack` is the one mutable structure. | best_shot, config, detector, types, video_source | numpy |
| `best_shot.py` | 92 | `laplacian_variance()`, `shot_score()` (`area_px × det_conf × blur_var`), `select_best_shots()` returning the top `BEST_SHOT_TOP_K` descending. Pure. | config, types | cv2, numpy |
| `normalizer.py` | 156 | `strip_separators()`, `apply_positional_confusions()`, `is_valid_plate()`, `normalize_plate()`. Pure, no I/O, no logging, never raises for unreadable input. | none | none |
| `plate_reader.py` | 267 | `PlateReader` builds one EasyOCR `Reader` and reads the lower `PLATE_ROI_FRACTION` band of the top `PLATE_OCR_TOP_K` crops. `PlateRead` carries the result. | config, normalizer, types | cv2, numpy, easyocr (deferred import) |
| `embedder.py` | 295 | `VehicleEmbedder` builds OSNet once, verifies the checkpoint by direct tensor comparison, and returns a 512-D unit-norm `list[float]` from one batched forward pass. `osnet_checkpoint_path()` mirrors `osnet.py`'s cache path. Raises `EmbedderError`. | config, osnet, types | cv2, numpy, torch |
| `osnet.py` | 598 | Vendored OSNet architecture from deep-person-reid (MIT), unmodified. Provides `osnet_x1_0` and `init_pretrained_weights`. `torchreid` is not installed and is never imported. | none | torch |
| `ingest_client.py` | 267 | `sighting_to_dict()` serialises via dataclass reflection. `JsonlIngestClient` appends JSON lines with no network; `HttpIngestClient` POSTs with retry/backoff. `relative_crop_path()`. Raises `IngestError` / `IngestAuthError`. | config, types | httpx, numpy |

### `scripts/`

| File | Lines | What it does | Internal deps |
|---|---|---|---|
| `run_worker.py` | 453 | One camera, one video. Owns the frame loop, drives `TrackletBuffer` directly, calls tier-2 work in `emit_tracklet()`, writes crops, builds and emits `Sighting`. Flags: `--video`, `--camera-id`, `--epoch`, `--out`, `--post`, `--visualize`. | best_shot, config, detector, embedder, ingest_client, plate_reader, tracker, types, video_source |
| `run_all_workers.py` | 227 | Generates **one** epoch and passes it to one `run_worker.py` subprocess per video. Flags: `--video-dir`, `--out-dir`, `--post`, `--epoch`, `--visualize`. Camera id is the video filename stem. | video_source |
| `download_models.py` | 195 | Prints device availability, fetches YOLOv8s into `models/`, builds OSNet via the vendored module to populate its cache and copies the checkpoint into `models/`, warms EasyOCR. | config, embedder, osnet |

Dependency direction is acyclic: `config` and `types` and `normalizer` and
`osnet` depend on nothing internal; everything else depends inward on them;
`scripts/` depends on `src/` and nothing depends on `scripts/`.

---

## 2. The two-tier boundary

**Tier 1 — per frame.** `video_source.py`, `detector.py`, `tracker.py`, and the
`laplacian_variance` call in `best_shot.py`. Decode, detect, associate, crop,
measure sharpness, append to a buffer. Nothing else.

**Tier 2 — per finalised tracklet.** `best_shot.py` selection, `plate_reader.py`,
`embedder.py`, `ingest_client.py`. Reached only from `emit_tracklet()` in
`run_worker.py`, which is called from the loops over finalised tracklets
(`run_worker.py:309` and `:315`) and never from the frame loop (`:287`–`:291`).

Verified by grep: none of `tracker.py`, `detector.py`, `video_source.py`,
`best_shot.py` reference `easyocr`, `PlateReader`, `VehicleEmbedder`,
`read_tracklet`, `embed_tracklet`, or `osnet`.

### Measured cost

Test clip: 30 frames, 640×480, 10 fps, cut from an uploaded clip. Two tracklets
finalised (30 and 19 frames). Apple Silicon, MPS for OSNet, CPU for EasyOCR.

| Stage | Tier | Cost |
|---|---|---|
| Detect + track, 30 frames | 1 | **1.4–1.6 s** (47–55 ms/frame) |
| Plate OCR, 2 tracklets | 2 | **1.1–1.2 s** |
| Embedding, 2 tracklets | 2 | **0.5–1.7 s** |
| **Total processing** | | **~3.3 s** |

One-time model construction, excluded from the above: EasyOCR 3.0 s, OSNet
0.2 s, YOLO 0.1 s.

OCR cost before the ROI width clamp and `PLATE_OCR_TOP_K` were added, same clip,
same run: **122.8 s**. Attribution measured back to back:

| Configuration | OCR time |
|---|---|
| No clamp, K=5 | 122.8 s |
| Clamp only, K=5 | 2.1 s |
| K=3 only, no clamp | 37.5 s |
| Clamp + K=3 (current) | 1.1 s |

The clamp accounts for almost all of the reduction. Absolute numbers vary
between runs on this machine (the same pre-clamp configuration measured 74.2 s
in an earlier session); the ratios are the stable finding.

The tier split is what makes the pipeline affordable: OCR costs roughly 0.4 s
per crop read. Running it per detection per frame instead of per tracklet would
be on the order of 10² more calls on this clip.

---

## 3. Data flow, mp4 to Sighting JSON

1. `run_all_workers.py` generates one ISO-8601 UTC epoch and passes it verbatim
   to every `run_worker.py` subprocess. (Running `run_worker.py` by hand without
   `--epoch` defaults it to `now()`, which diverges per process.)
2. `VideoSource` opens the video, resolves fps from the container (falling back
   to `PLAYBACK_FPS` if the container reports a non-positive or non-finite rate).
3. Frames are decoded sequentially. Every `FRAME_STRIDE`-th frame is yielded;
   the rest are decoded and discarded. The timestamp is
   `epoch + (true_frame_index / fps)`, formatted ISO-8601 UTC with `Z`.
4. **Tier 1.** `VehicleDetector.track()` runs YOLOv8s restricted to
   `TARGET_CLASS_IDS`, then ByteTrack with `persist=True`. Boxes the tracker did
   not associate (`boxes.id is None`) are dropped. Degenerate boxes
   (`w <= 0 or h <= 0`) are dropped.
5. `TrackletBuffer.update()` marks each observed track alive, crops each
   detection from the frame (`.copy()`, not a view), measures Laplacian
   variance, and appends a `FrameSample`. Crops under `BEST_SHOT_MIN_AREA_PX`
   are not buffered, but their track still counts as seen.
6. A track absent for `TRACK_LOST_FRAMES` processed frames is finalised. It is
   popped before the length test, so finalisation happens exactly once. Tracks
   with fewer than `TRACKLET_MIN_FRAMES` samples are discarded.
7. At end of stream, `flush()` finalises every track still open.
8. **Tier 2 begins.** `select_best_shots()` sorts the tracklet's samples by
   `area_px × det_conf × blur_var` and returns the top `BEST_SHOT_TOP_K`.
9. The rank-0 crop is written to
   `CROP_STORAGE_PATH/<camera_id>/<track_id>.jpg`.
10. `PlateReader.read_tracklet()` takes the first `PLATE_OCR_TOP_K` of those
    crops. For each: take the lower `PLATE_ROI_FRACTION` band, scale by
    `PLATE_UPSCALE_FACTOR` capped at `PLATE_ROI_MAX_WIDTH_PX` width (aspect
    preserved), run EasyOCR, keep the highest-confidence region.
11. Reads at or above `OCR_MIN_CONFIDENCE` go through `normalize_plate()`:
    uppercase, strip non-alphanumerics, reject on length, apply positional
    confusion corrections, validate against
    `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$`. The highest-confidence surviving
    read wins. If none survives, the highest-confidence raw text is retained in
    `plate_text_raw` with `plate_text_norm` left `None`.
12. The OCR box is mapped back to vehicle-crop coordinates using the *effective*
    scale (which the clamp may have reduced below `PLATE_UPSCALE_FACTOR`) plus
    the ROI's vertical offset, and stored as a JSON `[x, y, w, h]` string.
13. If a plate was read, the plate ROI is written to
    `CROP_STORAGE_PATH/<camera_id>/<track_id>_plate.jpg`.
14. `VehicleEmbedder.embed_tracklet()` resizes **all** `BEST_SHOT_TOP_K` crops to
    256×256, normalises with ImageNet statistics, runs **one** batched forward
    pass, averages the outputs, then L2-normalises the mean once. Length and
    unit norm are asserted in the code.
15. `build_sighting()` assembles the `Sighting`. `crop_path` and
    `plate_crop_path` are made relative to `CROP_STORAGE_PATH`.
16. `sighting_to_dict()` serialises by dataclass reflection; the embedding
    becomes a JSON array of 512 floats.
17. The client emits it: `JsonlIngestClient` appends one line and flushes, or
    `HttpIngestClient` POSTs to `BACKEND_BASE_URL/api/v1/ingest/sightings` with
    the `X-Ingest-Key` header.

---

## 4. Sighting output schema

30 fields, matching the `sightings` columns in `schema.md` §3.6 one for one
(verified mechanically; a test parses the `CREATE TABLE` and compares). Field
*order* differs from column order because dataclass fields without defaults must
come first; names and count match exactly.

| Field | Python type | JSON type | Set by |
|---|---|---|---|
| `id` | `str` | string | worker (uuid4) |
| `camera_id` | `str` | string | worker |
| `local_track_id` | `int` | number | worker |
| `first_frame_at` | `str` | string | worker (ISO-8601 UTC, `Z`) |
| `last_frame_at` | `str` | string | worker |
| `best_frame_at` | `str` | string | worker |
| `frame_count` | `int` | number | worker |
| `bbox_x` | `int` | number | worker |
| `bbox_y` | `int` | number | worker |
| `bbox_w` | `int` | number | worker |
| `bbox_h` | `int` | number | worker |
| `detection_confidence` | `float` | number | worker |
| `vehicle_class` | `VehicleClass` | string | worker |
| `created_at` | `str` | string | worker |
| `vehicle_id` | `str \| None` | null | **backend** |
| `received_at` | `str \| None` | null | **backend** (server clock) |
| `plate_text_raw` | `str \| None` | string/null | worker |
| `plate_text_norm` | `str \| None` | string/null | worker |
| `plate_confidence` | `float \| None` | number/null | worker |
| `plate_is_valid` | `bool` | boolean | worker |
| `plate_bbox` | `str \| None` | string/null | worker (JSON `[x,y,w,h]`) |
| `embedding` | `np.ndarray \| None` | array[512] float | worker |
| `embedding_dim` | `int` | number | worker (512) |
| `in_vector_index` | `bool` | boolean | **backend** (default `False`) |
| `crop_path` | `str \| None` | string/null | worker (relative) |
| `plate_crop_path` | `str \| None` | string/null | worker (relative) |
| `sharpness_score` | `float \| None` | number/null | worker (Laplacian variance) |
| `resolution_status` | `ResolutionStatus` | string | **backend** (default `"pending"`) |
| `match_method` | `MatchMethod \| None` | null | **backend** |
| `match_score` | `float \| None` | null | **backend** |

`VehicleClass` is `car | motorcycle | bus | truck | auto | other`.
`ResolutionStatus` is `pending | matched | ambiguous | new_vehicle`.
`MatchMethod` is `PLATE_EXACT | PLATE_FUZZY | VISUAL | MANUAL | NEW`.

The worker never populates the six backend-owned fields. `received_at` in
particular must come from the server clock, since its only purpose is detecting
worker clock drift.

---

## 5. Configuration

All values live in `src/config.py`, loaded from `ml-pipeline/.env` via
pydantic-settings. Defaults below are the values in the code.

### Backend connection

| Name | Default | Controls |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Ingest host in HTTP mode. |
| `INGEST_API_KEY` | `""` | `X-Ingest-Key` header. Empty means HTTP mode refuses to start. |

### Runtime

| Name | Default | Controls |
|---|---|---|
| `DEVICE` | `cuda` | Requested compute device (`cuda`/`cpu`/`mps`). The detector raises if unavailable; the embedder degrades to MPS then CPU. |
| `MODELS_DIR_PATH` | `models` | Where `download_models.py` writes weights. |

### Video decode

| Name | Default | Controls |
|---|---|---|
| `PLAYBACK_FPS` | `15.0` | Fallback frame rate when the container reports none. |
| `FRAME_STRIDE` | `2` | Process every Nth decoded frame. Does not affect timestamps. |

### Detection

| Name | Default | Controls |
|---|---|---|
| `YOLO_MODEL_PATH` | `models/yolov8s.pt` | Detector weights. Missing file fails at construction. |
| `DETECTION_CONF_MIN` | `0.35` | Minimum detection confidence. |
| `DETECTION_IOU_MAX` | `0.50` | NMS IoU threshold. |
| `TARGET_CLASS_IDS_CSV` | `2,3,5,7` | COCO classes kept: car, motorcycle, bus, truck. |

### Tracking

| Name | Default | Controls |
|---|---|---|
| `BYTETRACK_TRACK_CONF_MIN` | `0.50` | Present in config; ByteTrack is currently configured via ultralytics' `bytetrack.yaml`, so this is not read by `detector.py`. |
| `BYTETRACK_MATCH_IOU_MIN` | `0.80` | As above. |
| `BYTETRACK_BUFFER_FRAMES` | `30` | As above. |
| `TRACK_LOST_FRAMES` | `30` | Processed frames a track may be absent before finalisation. |
| `TRACKLET_MIN_FRAMES` | `8` | Tracklets with fewer buffered samples are discarded. |

### Best-shot

| Name | Default | Controls |
|---|---|---|
| `BEST_SHOT_TOP_K` | `5` | Crops kept per tracklet; all of them are embedded. |
| `BEST_SHOT_MIN_AREA_PX` | `2500` | Crops smaller than this are not buffered. |

### Re-ID

| Name | Default | Controls |
|---|---|---|
| `REID_MODEL_NAME` | `osnet_x1_0` | Architecture selected from the vendored module. |
| `REID_INPUT_HEIGHT_PX` | `256` | Embedder input height. |
| `REID_INPUT_WIDTH_PX` | `256` | Embedder input width. |
| `REID_BATCH_SIZE` | `16` | Present in config; not read by `embedder.py`, which batches the whole top-K set in one pass. |
| `REID_EMBEDDING_DIM` | `512` | Asserted against the backbone's actual output. |

### Plate OCR

| Name | Default | Controls |
|---|---|---|
| `OCR_MIN_CONFIDENCE` | `0.40` | Reads below this are not normalised. |
| `PLATE_ROI_FRACTION` | `0.40` | Lower fraction of the vehicle box searched for a plate. |
| `PLATE_UPSCALE_FACTOR` | `4` | Nominal ROI upscale before OCR. |
| `PLATE_ROI_MAX_WIDTH_PX` | `640` | Ceiling on upscaled ROI width. Small crops never reach it and keep the full upscale. |
| `PLATE_OCR_TOP_K` | `3` | How many best shots get an OCR pass. |

### Ingest client

| Name | Default | Controls |
|---|---|---|
| `INGEST_TIMEOUT_SECONDS` | `10.0` | HTTP request timeout. |
| `INGEST_MAX_RETRIES` | `3` | Retries on 5xx and transport errors. Never on 401. |
| `INGEST_BACKOFF_BASE_SECONDS` | `0.5` | First backoff; doubles per attempt. |

### Visualisation and storage

| Name | Default | Controls |
|---|---|---|
| `VISUALIZE_OUTPUT_FPS` | `15.0` | Frame rate of the `--visualize` mp4. |
| `CROP_STORAGE_PATH` | `data/crops` | Root for written crops; `crop_path` is relative to it. |

Derived properties: `TARGET_CLASS_IDS` → `(2, 3, 5, 7)`,
`REID_INPUT_SIZE_PX` → `(256, 256)`, `SECONDS_PER_FRAME` → `1 / PLAYBACK_FPS`.

---

## 6. Known limitations

### OSNet weights are ImageNet-pretrained, not vehicle Re-ID weights

`osnet_x1_0(pretrained=True)` loads `osnet_x1_0_imagenet.pth` from
`~/.cache/torch/checkpoints`. These are ImageNet classification weights, not
weights trained on a vehicle Re-ID dataset such as VeRi-776. The embedder
verifies that *these* weights loaded — it compares `conv1.conv.weight` against
the checkpoint file and raises rather than falling back to random
initialisation — but it cannot make ImageNet features into vehicle Re-ID
features.

### Measured similarity scores overlap between identities

Measured once on four sample vehicle images (two views of one car, one of
another). Those images have since been removed from the repository, so the
figures below are a recorded historical finding rather than something the suite
re-derives; the underlying limitation is a property of the weights and still
applies. Cosine similarity between 512-D embeddings:

| Pair | Similarity |
|---|---|
| Vehicle A, view 1 vs view 2 (same vehicle) | **0.571** |
| Vehicle A, view 1 vs view 3 (same vehicle) | **0.771** |
| Vehicle A vs Vehicle B (different vehicles) | **0.676** |

The different-vehicle score sits *between* the two same-vehicle scores. On this
sample there is no threshold that separates same from different. Any
visual-tier threshold in the backend is therefore not supported by measurement
on this data, and cross-camera matching on appearance alone should be expected
to fail on some pairs. This is a property of the weights, not a defect in
`embedder.py`.

### The normalizer produces structurally valid false positives

`normalize_plate()` accepts anything matching
`^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$` after positional correction. It has no
way to know whether the characters were really on a plate.

Observed on the test clip: raw OCR `'J0 1EF6035'` (a reflection/badge read on a
car with no valid Indian plate) normalised to `JO1EF6035` at confidence 0.50,
above the 0.40 floor, and was emitted with `plate_is_valid: true`. A second
configuration produced `JH01EF6035` from the same vehicle. Neither is a real
plate.

A related ambiguity is pinned by
`test_a_dropped_character_can_still_yield_a_valid_plate`: `BR01AB123` (a plate
with one character dropped by OCR) normalises to the valid-but-wrong
`BR01A8123`, because at nine characters the trailing-serial window starts at
index 5 and corrects the series `B` to `8`. No positional scheme can distinguish
this from a genuine nine-character plate. The correction is kept because letters
misread inside the serial are more common, but the trade-off is real.

Consequence: `plate_confidence` is the only signal distinguishing a real read
from a plausible-looking invention, and the backend's plate tier is its
highest-trust match method.

### `PLATE_OCR_TOP_K = 3` can miss the only readable crop

Measured on the test clip with the clamp active, per best-shot rank:

```
rank 0: 'IO1EF60357'    conf=0.31  -> None
rank 1: 'LJHO1EF6035'   conf=0.65  -> None
rank 2: 'L~JHO EF6035'  conf=0.47  -> None
rank 3: '~JHO 1EF6035'  conf=0.62  -> JH01EF6035
rank 4: 'LJHO1EF6035'   conf=0.67  -> None
```

The only read that survives normalisation is at rank 3, outside a `K=3` budget.
Best-shot score ranks by area, detection confidence and focus, which predict a
good embedding but only loosely predict a readable plate. `K=3` saves about 1
second per clip relative to `K=5` and lost the read here.

### The ROI width clamp changes what OCR sees

`PLATE_ROI_MAX_WIDTH_PX` is not read-neutral. On the test clip the same vehicle
yielded `JO1EF6035` without the clamp and `JH01EF6035` with it. For a
frame-filling vehicle the ROI now receives an effective scale of 1.0 — no
upscale at all — because 640 px wide already exceeds the ceiling.

### No auto-rickshaw class

`TARGET_CLASS_IDS_CSV` is `2,3,5,7`: COCO's car, motorcycle, bus, truck. COCO
has no auto-rickshaw category. The `sightings` schema permits `vehicle_class`
`'auto'`, and `to_vehicle_class()` in `run_worker.py` can map to it, but nothing
in the pipeline ever produces that value — the detector cannot emit it. Auto
rickshaws in footage will be detected as `car`, `motorcycle`, or `truck`, or
missed. Since the backend gates matches on vehicle class, an auto rickshaw
classified inconsistently across cameras will not match itself.

### Other

- **EasyOCR runs on CPU.** `gpu=False` is hardcoded in `PlateReader`: EasyOCR's
  GPU path expects CUDA, which this machine does not have. OCR is the dominant
  tier-2 cost.
- **Three config values are declared but not read**:
  `BYTETRACK_TRACK_CONF_MIN`, `BYTETRACK_MATCH_IOU_MIN`,
  `BYTETRACK_BUFFER_FRAMES` (ByteTrack is configured through ultralytics'
  `bytetrack.yaml`), and `REID_BATCH_SIZE` (the embedder batches the entire
  top-K set in one pass). Changing them has no effect.
- **`FRAME_STRIDE` interacts with `TRACK_LOST_FRAMES`.** Both are counted in
  *processed* frames, so raising the stride shortens the real-time window before
  a track finalises.
- **Ultralytics is AGPL-3.0.** Confined to `detector.py`, which is the only
  module importing it.
- **numpy 2.4.6 and OpenCV 5.0.0** deviate from the pinned versions in
  `techspec.md` §2.1 (1.26.x and 4.9.0.80). Ultralytics 8.4.x requires them; the
  deviation is recorded at the top of `requirements.txt`.
