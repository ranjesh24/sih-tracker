"""Run one camera worker over one video.

    python scripts/run_worker.py --video clip.mp4 --camera-id CAM-01 --out out.jsonl

Tier structure, which this script is the enforcement point for
--------------------------------------------------------------
The frame loop below performs detection and ByteTrack association and nothing
else. OCR and embedding happen in `emit_tracklet`, called only from the loop
*over finalised tracklets* — that is, once per vehicle rather than once per
frame per vehicle.

The models are constructed once, before the loop, and reused for every tracklet.
An EasyOCR Reader costs seconds to build; constructing one per tracklet would
cost more than all the inference in the run.

Timestamps and the shared epoch
-------------------------------
`--epoch` is the synthetic start time all workers in a run share. Every frame
timestamp is derived from it arithmetically, so two cameras processing the same
synthetic instant agree regardless of decode speed. Run workers through
run_all_workers.py rather than by hand: it generates one epoch and passes the
same value to every process, which is the property cross-camera matching depends
on.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

# The pipeline package lives one level up from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.best_shot import select_best_shots  # noqa: E402
from src.config import Settings, get_settings  # noqa: E402
from src.detector import VehicleDetector  # noqa: E402
from src.embedder import VehicleEmbedder  # noqa: E402
from src.ingest_client import (  # noqa: E402
    HttpIngestClient,
    IngestAuthError,
    IngestClient,
    IngestError,
    JsonlIngestClient,
    relative_crop_path,
)
from src.plate_reader import PlateRead, PlateReader  # noqa: E402
from src.tracker import TrackletBuffer  # noqa: E402
from src.types import Detection, Sighting, Tracklet, VehicleClass  # noqa: E402
from src.video_source import VideoSource, to_iso8601_utc  # noqa: E402

# Vehicle classes the sightings table accepts (schema.md section 3.6). Anything
# the detector reports outside this set is stored as 'other' rather than
# violating the CHECK constraint.
ALLOWED_VEHICLE_CLASSES: frozenset[str] = frozenset(
    {"car", "motorcycle", "bus", "truck", "auto", "other"}
)

ANNOTATION_BOX_COLOUR_BGR = (60, 200, 60)
ANNOTATION_TEXT_COLOUR_BGR = (255, 255, 255)
ANNOTATION_BOX_THICKNESS_PX = 2
ANNOTATION_FONT_SCALE = 0.5


def parse_epoch(raw_epoch: str | None) -> datetime:
    """Parse the shared epoch, defaulting to now.

    Args:
        raw_epoch: ISO-8601 string, or None to use the current UTC time.

    Returns:
        A timezone-aware UTC datetime.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    if raw_epoch is None:
        return datetime.now(timezone.utc)

    parsed = datetime.fromisoformat(raw_epoch.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_vehicle_class(class_name: str) -> VehicleClass:
    """Map a COCO label onto the schema's vehicle_class enum.

    Args:
        class_name: The COCO label from the detector.

    Returns:
        A value the sightings CHECK constraint accepts.
    """
    if class_name in ALLOWED_VEHICLE_CLASSES:
        return class_name  # type: ignore[return-value]
    return "other"


def write_best_crop(
    tracklet: Tracklet,
    best_shot_sample_crop: np.ndarray,
    settings: Settings,
) -> Path:
    """Write the top crop to CROP_STORAGE_PATH/<camera_id>/<track_id>.jpg.

    Args:
        tracklet: The finalised tracklet the crop belongs to.
        best_shot_sample_crop: The highest-scoring crop, BGR.
        settings: Pipeline settings.

    Returns:
        The absolute path written.

    Raises:
        OSError: If the file could not be written.
    """
    camera_dir = settings.CROP_STORAGE_PATH / tracklet.camera_id
    camera_dir.mkdir(parents=True, exist_ok=True)

    crop_path = camera_dir / f"{tracklet.track_id}.jpg"
    if not cv2.imwrite(str(crop_path), best_shot_sample_crop):
        raise OSError(f"cv2.imwrite failed for {crop_path}")

    return crop_path


def write_plate_crop(
    tracklet: Tracklet,
    plate_read: PlateRead,
    settings: Settings,
) -> Path | None:
    """Write the plate crop alongside the vehicle crop, if one was read."""
    if plate_read.plate_crop_bgr is None or plate_read.plate_crop_bgr.size == 0:
        return None

    camera_dir = settings.CROP_STORAGE_PATH / tracklet.camera_id
    camera_dir.mkdir(parents=True, exist_ok=True)

    plate_path = camera_dir / f"{tracklet.track_id}_plate.jpg"
    if not cv2.imwrite(str(plate_path), plate_read.plate_crop_bgr):
        return None

    return plate_path


def build_sighting(
    tracklet: Tracklet,
    plate_read: PlateRead,
    embedding_vector: list[float],
    crop_path: Path,
    plate_crop_path: Path | None,
    settings: Settings,
) -> Sighting:
    """Assemble a Sighting from a finalised tracklet and its tier-2 results.

    `received_at`, `vehicle_id`, `resolution_status`, `match_method` and
    `match_score` are left at their defaults: the backend owns them, and
    `received_at` in particular must come from the server clock because its only
    purpose is detecting worker clock drift (schema.md section 3.6).

    Args:
        tracklet: The finalised tracklet.
        plate_read: Result of plate OCR over the best shots.
        embedding_vector: 512-D unit-norm appearance embedding.
        crop_path: Absolute path of the written vehicle crop.
        plate_crop_path: Absolute path of the plate crop, if any.
        settings: Pipeline settings, for resolving relative crop paths.

    Returns:
        A Sighting ready to emit.
    """
    best_shots = select_best_shots(tracklet.samples, settings)
    best_sample = best_shots[0]
    detection = best_sample.detection

    return Sighting(
        id=str(uuid.uuid4()),
        camera_id=tracklet.camera_id,
        local_track_id=tracklet.track_id,
        first_frame_at=tracklet.first_frame_at,
        last_frame_at=tracklet.last_frame_at,
        best_frame_at=best_sample.frame_at,
        frame_count=tracklet.frame_count,
        bbox_x=detection.bbox_x_px,
        bbox_y=detection.bbox_y_px,
        bbox_w=detection.bbox_w_px,
        bbox_h=detection.bbox_h_px,
        detection_confidence=detection.det_conf,
        vehicle_class=to_vehicle_class(detection.class_name),
        created_at=to_iso8601_utc(datetime.now(timezone.utc)),
        plate_text_raw=plate_read.text_raw,
        plate_text_norm=plate_read.text_norm,
        plate_confidence=plate_read.confidence,
        plate_is_valid=plate_read.is_valid,
        plate_bbox=plate_read.bbox_json,
        embedding=np.asarray(embedding_vector, dtype=np.float32),
        embedding_dim=len(embedding_vector),
        crop_path=relative_crop_path(crop_path, settings),
        plate_crop_path=(
            relative_crop_path(plate_crop_path, settings) if plate_crop_path else None
        ),
        sharpness_score=best_sample.blur_var,
    )


def annotate_frame(
    frame_bgr: np.ndarray,
    observations: list[tuple[int, Detection]],
) -> np.ndarray:
    """Draw track boxes and ids onto a copy of the frame."""
    annotated = frame_bgr.copy()

    for track_id, detection in observations:
        x_px = detection.bbox_x_px
        y_px = detection.bbox_y_px
        w_px = detection.bbox_w_px
        h_px = detection.bbox_h_px
        class_name = detection.class_name
        det_conf = detection.det_conf

        cv2.rectangle(
            annotated,
            (x_px, y_px),
            (x_px + w_px, y_px + h_px),
            ANNOTATION_BOX_COLOUR_BGR,
            ANNOTATION_BOX_THICKNESS_PX,
        )
        cv2.putText(
            annotated,
            f"#{track_id} {class_name} {det_conf:.2f}",
            (x_px, max(y_px - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            ANNOTATION_FONT_SCALE,
            ANNOTATION_TEXT_COLOUR_BGR,
            1,
            cv2.LINE_AA,
        )

    return annotated


def run_worker(
    video_path: Path,
    camera_id: str,
    epoch_at: datetime,
    client: IngestClient,
    settings: Settings,
    visualize_path: Path | None,
) -> int:
    """Process one video end to end, emitting one Sighting per tracklet.

    Args:
        video_path: Source video.
        camera_id: Camera this video belongs to.
        epoch_at: Shared synthetic start time.
        client: Where sightings are emitted.
        settings: Pipeline settings.
        visualize_path: Optional mp4 to write annotated frames to.

    Returns:
        The number of sightings emitted.
    """
    # Every model is built once, here, before any frame is read.
    detector = VehicleDetector(settings)
    # The buffer is driven directly rather than through VehicleTracker: this
    # loop also has to annotate each frame for --visualize, which needs the
    # per-frame observations that the tracklet generator does not surface.
    buffer = TrackletBuffer(camera_id, settings)
    plate_reader = PlateReader(settings)
    embedder = VehicleEmbedder(settings)

    print(f"[{camera_id}] models ready (embedder on {embedder.device})", flush=True)

    writer: cv2.VideoWriter | None = None
    emitted_count = 0
    frame_count = 0
    started_at = time.time()

    with VideoSource(video_path, epoch_at, settings) as source:
        for frame_bgr, frame_at in source.frames():
            frame_count += 1

            # --- TIER 1: detection and association only -----------------------
            observations = detector.track(frame_bgr)

            if visualize_path is not None:
                if writer is None:
                    height_px, width_px = frame_bgr.shape[:2]
                    writer = cv2.VideoWriter(
                        str(visualize_path),
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        settings.VISUALIZE_OUTPUT_FPS,
                        (width_px, height_px),
                    )
                writer.write(annotate_frame(frame_bgr, observations))

            finalised = buffer.update(
                observations, frame_bgr, frame_at, frame_count - 1
            )

            # --- TIER 2: only over finalised tracklets ------------------------
            for tracklet in finalised:
                emitted_count += emit_tracklet(
                    tracklet, plate_reader, embedder, client, settings
                )

        # A clip ending is not the same as every track lapsing.
        for tracklet in buffer.flush():
            emitted_count += emit_tracklet(
                tracklet, plate_reader, embedder, client, settings
            )

    if writer is not None:
        writer.release()
        print(f"[{camera_id}] annotated video written to {visualize_path}", flush=True)

    elapsed_seconds = time.time() - started_at
    print(
        f"[{camera_id}] done: {frame_count} frames processed, "
        f"{emitted_count} sightings emitted in {elapsed_seconds:.1f}s",
        flush=True,
    )
    return emitted_count


def emit_tracklet(
    tracklet: Tracklet,
    plate_reader: PlateReader,
    embedder: VehicleEmbedder,
    client: IngestClient,
    settings: Settings,
) -> int:
    """Run tier-2 work for one finalised tracklet and emit its Sighting.

    Returns:
        1 if a sighting was emitted, 0 if the tracklet was skipped.
    """
    best_shots = select_best_shots(tracklet.samples, settings)
    if not best_shots:
        return 0

    crop_path = write_best_crop(tracklet, best_shots[0].crop_bgr, settings)

    plate_read = plate_reader.read_tracklet(best_shots)
    embedding_vector = embedder.embed_tracklet(best_shots)
    plate_crop_path = write_plate_crop(tracklet, plate_read, settings)

    sighting = build_sighting(
        tracklet, plate_read, embedding_vector, crop_path, plate_crop_path, settings
    )
    client.send(sighting)

    plate_display = sighting.plate_text_norm or "no plate"
    print(
        f"[{tracklet.camera_id}] tracklet {tracklet.track_id} finalised: "
        f"{tracklet.frame_count} frames, class={sighting.vehicle_class}, "
        f"plate={plate_display}, embedding_dim={sighting.embedding_dim}",
        flush=True,
    )
    return 1


def build_arg_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Run one camera worker over one video."
    )
    parser.add_argument("--video", required=True, type=Path, help="Source video.")
    parser.add_argument(
        "--camera-id", required=True, help="Camera code, e.g. CAM-01."
    )
    parser.add_argument(
        "--epoch",
        default=None,
        help=(
            "Shared synthetic start time, ISO-8601 UTC. All workers in a run "
            "must be given the same value. Defaults to now."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSONL file to append sightings to. This is the offline demo path.",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="POST sightings to the backend instead of writing JSONL.",
    )
    parser.add_argument(
        "--visualize",
        type=Path,
        default=None,
        help="Write an annotated mp4 to this path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        0 on success, 1 on a fatal configuration or ingest failure.
    """
    args = build_arg_parser().parse_args(argv)

    if not args.post and args.out is None:
        print(
            "error: choose an output mode — --out <file.jsonl> or --post",
            file=sys.stderr,
        )
        return 1

    settings = get_settings()
    epoch_at = parse_epoch(args.epoch)

    client: IngestClient
    try:
        client = HttpIngestClient(settings) if args.post else JsonlIngestClient(args.out)
    except IngestAuthError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1

    try:
        with client:
            run_worker(
                video_path=args.video,
                camera_id=args.camera_id,
                epoch_at=epoch_at,
                client=client,
                settings=settings,
                visualize_path=args.visualize,
            )
    except IngestAuthError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
