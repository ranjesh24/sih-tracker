"""Seed a complete, presentable demo: one vehicle tracked across three cameras.

Why this exists
---------------
The evidence panel needs a vehicle whose sightings carry a real ``crop_path``.
Before this script there was no seeded trajectory at all: the UI fell back to
frontend fixture data (``mockData.ts``), whose sightings have no crop and never
could, so the "Tracklet Best Frame" box was permanently empty.

This writes real rows into the database and real JPEGs into the static crops
directory, so the demo works end to end with no pipeline run — which is what
will be on screen on presentation day.

Crops are extracted from any uploaded clip in ``data/uploads`` when one is
available and OpenCV is importable in this interpreter. Otherwise a labelled
placeholder JPEG is generated, so the script always produces a working demo.

    python scripts/seed_demo.py
    python scripts/seed_demo.py --clear   # remove seeded rows first

Run ``seed_cameras.py`` first: this depends on CAM-01..03 and their edges.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import delete  # noqa: E402
from sqlmodel import Session, col, select  # noqa: E402

import app.db.session as db_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import Camera, MatchDecision, Sighting, Vehicle, Video  # noqa: E402
from app.repositories import video_repo  # noqa: E402

STATIC_CROPS_DIR = _BACKEND_ROOT / "static" / "crops"
UPLOADS_DIR = _BACKEND_ROOT / "data" / "uploads"
ML_PIPELINE_DIR = _BACKEND_ROOT.parent / "ml-pipeline"


def _imaging_python() -> str | None:
    """Return an interpreter that can import cv2, or None.

    The backend venv is 3.14 and deliberately has no OpenCV — the imaging stack
    lives in the ml-pipeline venv. Rather than add a heavy dependency to the API
    environment just to seed a demo, the crop step shells out to that
    interpreter, the same arrangement the upload endpoint already uses.
    """
    try:
        import cv2  # noqa: F401

        return sys.executable
    except ImportError:
        pass

    for candidate in (
        ML_PIPELINE_DIR / "venv" / "bin" / "python",
        ML_PIPELINE_DIR / "venv" / "Scripts" / "python.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return None


_CROP_SCRIPT = """
import hashlib
import sys
import cv2

clip_path, target, camera_code, plate, width, height, rank = sys.argv[1:8]
width, height, rank = int(width), int(height), int(rank)

CANDIDATE_FRAMES = 12
MIN_BOX_AREA_PX = 4000


def write(image):
    ok = bool(cv2.imwrite(target, cv2.resize(image, (width, height))))
    if ok:
        print(hashlib.md5(open(target, "rb").read()).hexdigest())
    return ok


wrote = False
if clip_path:
    # Sample frames across the clip and keep the ones where the detector finds
    # a vehicle, ranked by how large it is. Picking the middle frame blind
    # often landed on empty road; this picks a frame where the car is actually
    # visible and reasonably big. `rank` selects the Nth-best frame, which lets
    # the caller ask for a different one when two cameras would otherwise
    # produce an identical crop.
    try:
        sys.path.insert(0, "ML_ROOT")
        from src.config import Settings
        from src.detector import VehicleDetector

        settings = Settings(DEVICE="mps", YOLO_MODEL_PATH="ML_ROOT/models/yolov8s.pt")
        detector = VehicleDetector(settings)

        capture = cv2.VideoCapture(clip_path)
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        scored = []
        try:
            for step in range(CANDIDATE_FRAMES):
                index = int(total * (step + 0.5) / CANDIDATE_FRAMES) if total > 1 else 0
                capture.set(cv2.CAP_PROP_POS_FRAMES, max(index, 0))
                is_read, frame = capture.read()
                if not is_read or frame is None:
                    continue
                detections = detector.detect(frame)
                if not detections:
                    continue
                best = max(detections, key=lambda d: d.area_px)
                if best.area_px < MIN_BOX_AREA_PX:
                    continue
                scored.append((best.area_px, index, frame, best))
        finally:
            capture.release()

        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            _, _, frame, best = scored[min(rank, len(scored) - 1)]
            h, w = frame.shape[:2]
            x1 = max(0, best.bbox_x_px)
            y1 = max(0, best.bbox_y_px)
            x2 = min(w, best.bbox_x_px + best.bbox_w_px)
            y2 = min(h, best.bbox_y_px + best.bbox_h_px)
            # Pad a little so the crop reads as a vehicle in context.
            pad_x = int((x2 - x1) * 0.12)
            pad_y = int((y2 - y1) * 0.12)
            crop = frame[max(0, y1 - pad_y):min(h, y2 + pad_y),
                         max(0, x1 - pad_x):min(w, x2 + pad_x)]
            if crop.size > 0:
                wrote = write(crop)
    except Exception as exc:
        print("DETECT_FAILED " + str(exc)[:120], file=sys.stderr)

    if not wrote:
        # Detector unavailable: fall back to the previous middle-frame centre crop.
        capture = cv2.VideoCapture(clip_path)
        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count > 1:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
            is_read, frame = capture.read()
        finally:
            capture.release()
        if is_read and frame is not None:
            h, w = frame.shape[:2]
            crop = frame[int(h * 0.15):int(h * 0.90), int(w * 0.15):int(w * 0.85)]
            if crop.size > 0:
                wrote = write(crop)

if not wrote:
    import numpy as np
    frame = np.full((height, width, 3), 32, dtype=np.uint8)
    cv2.rectangle(frame, (40, 40), (width - 40, height - 40), (90, 180, 90), 2)
    cv2.putText(frame, camera_code, (60, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (230, 230, 230), 2)
    cv2.putText(frame, plate, (60, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (140, 200, 140), 2)
    write(frame)
"""

# The demo vehicle. A single car passing three junctions in sequence.
# Retained only to label the fallback placeholder image; no sighting or vehicle
# carries a plate any more.
DEMO_PLATE = "BR01AB1234"

# Per-hop appearance and temporal scores, in the range OSNet actually produces
# on this footage: measured same-vehicle cosine sits at 0.65-0.75, not the 0.88
# the seed used to claim. Indexed by the hop's destination camera.
DEMO_HOP_SCORES: dict[str, tuple[float, float]] = {
    # to_camera: (visual, temporal)
    "CAM-02": (0.68, 0.93),
    "CAM-03": (0.71, 0.89),
}

# Rejected candidates sit at or slightly above the accepted visual scores. That
# is the whole point of those cards: appearance alone could not separate these
# vehicles, and the gate is what ruled them out.
DEMO_REJECTED_VISUAL_TOO_FAST = 0.74
DEMO_REJECTED_VISUAL_SAME_CAMERA = 0.70


def fused_score(visual: float, temporal: float) -> float:
    """Fuse exactly as the resolver's visual tier does.

    Mirrors ``identity_resolver`` rather than storing a number by hand, so the
    three values on screen are always arithmetically consistent:

        fused = W_VISUAL * visual + W_TEMPORAL * temporal

    There is no plate term — the visual tier has none — and the weights are read
    from config rather than restated here, so this cannot drift if they change.
    """
    settings = get_settings()
    return settings.W_VISUAL * visual + settings.W_TEMPORAL * temporal
DEMO_REF = "#A47F"

# Camera order and the gap, in seconds, from the previous camera. Both gaps sit
# inside the seeded transit windows in seed_cameras.py, so the gate passes.
DEMO_HOPS: list[tuple[str, int]] = [
    ("CAM-01", 0),
    ("CAM-02", 420),
    ("CAM-03", 500),
]

CROP_WIDTH_PX = 480
CROP_HEIGHT_PX = 270


def _utc(moment: datetime) -> str:
    """ISO-8601 UTC with a Z suffix (schema.md section 2)."""
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _find_clip_for(camera_code: str, session: Session | None = None) -> Path | None:
    """Return the video currently associated with this camera.

    Reads the ``videos`` table for the current upload batch, so the seeded crop
    is cut from the clip that actually plays in that camera's tile. The previous
    version globbed the uploads directory and took whichever filename sorted
    last, which is why the CAM-01 crop showed a different car than the CAM-01
    feed. Falls back to the glob when the camera has no current upload.
    """
    if session is not None:
        camera = session.exec(select(Camera).where(Camera.code == camera_code)).first()
        if camera is not None:
            batch_id = video_repo.get_current_batch_id(session)
            if batch_id is not None:
                video = session.exec(
                    select(Video)
                    .where(Video.camera_id == camera.id)
                    .where(Video.batch_id == batch_id)
                    .order_by(col(Video.uploaded_at).desc())
                ).first()
                if video is not None:
                    candidate = UPLOADS_DIR / video.filename
                    if candidate.is_file():
                        return candidate

    if not UPLOADS_DIR.is_dir():
        return None
    matches = sorted(UPLOADS_DIR.glob(f"*_{camera_code}.*"))
    return matches[-1] if matches else None


def _extract_crop(
    camera_code: str,
    target: Path,
    session: Session | None = None,
    rank: int = 0,
) -> tuple[str, str | None]:
    """Write a crop JPEG for one camera and report how it was produced.

    Returns (report, md5). The md5 lets the caller notice two cameras producing
    an identical image and ask for a different frame.
    """
    interpreter = _imaging_python()
    if interpreter is None:
        return "FAILED (no interpreter with opencv found)", None

    clip = _find_clip_for(camera_code, session)
    script = _CROP_SCRIPT.replace("ML_ROOT", str(ML_PIPELINE_DIR))
    result = subprocess.run(
        [
            interpreter,
            "-c",
            script,
            str(clip) if clip else "",
            str(target),
            camera_code,
            DEMO_PLATE,
            str(CROP_WIDTH_PX),
            str(CROP_HEIGHT_PX),
            str(rank),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not target.is_file():
        return f"FAILED ({result.stderr.strip().splitlines()[-1:] or 'unknown'})", None

    lines = [ln for ln in result.stdout.strip().splitlines() if ln]
    digest = lines[-1] if lines and len(lines[-1]) == 32 else None
    source = f"frame from {clip.name}" if clip is not None else "generated placeholder"
    return source, digest


def clear_seeded(session: Session) -> None:
    """Remove the seeded demo vehicle and everything hanging off it."""
    vehicles = session.exec(select(Vehicle).where(Vehicle.display_ref == DEMO_REF)).all()
    for vehicle in vehicles:
        sightings = session.exec(
            select(Sighting).where(Sighting.vehicle_id == vehicle.id)
        ).all()
        for sighting in sightings:
            session.execute(
                delete(MatchDecision).where(MatchDecision.sighting_id == sighting.id)
            )
            session.delete(sighting)
        session.delete(vehicle)
    session.commit()


def seed(session: Session) -> dict:
    """Create the demo vehicle, its sightings, crops and match decisions."""
    cameras = {c.code: c for c in session.exec(select(Camera)).all()}
    missing = [code for code, _ in DEMO_HOPS if code not in cameras]
    if missing:
        raise SystemExit(
            f"Missing cameras {missing}. Run scripts/seed_cameras.py first."
        )

    STATIC_CROPS_DIR.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc) - timedelta(minutes=30)

    vehicle = Vehicle(
        display_ref=DEMO_REF,
        # The demo footage shows a car with no legible plate, so the seeded
        # vehicle carries none. The UI then renders its existing "no plate"
        # placeholder everywhere, exactly as it does for a real plateless
        # sighting — no special-casing needed.
        canonical_plate=None,
        plate_confidence=None,
        plate_is_valid=False,
        vehicle_class="car",
        sighting_count=len(DEMO_HOPS),
        camera_count=len(DEMO_HOPS),
        status="active",
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)

    camera_code_by_id = {c.id: c.code for c in cameras.values()}
    hop_summaries: list[tuple[str, int, float, float, float]] = []
    crop_reports: list[str] = []
    seen_digests: set[str] = set()
    sightings: list[Sighting] = []
    elapsed_seconds = 0

    for index, (camera_code, gap_seconds) in enumerate(DEMO_HOPS):
        elapsed_seconds += gap_seconds
        first_at = started_at + timedelta(seconds=elapsed_seconds)
        last_at = first_at + timedelta(seconds=4)

        sighting = Sighting(
            vehicle_id=vehicle.id,
            camera_id=cameras[camera_code].id,
            local_track_id=index + 1,
            first_frame_at=_utc(first_at),
            last_frame_at=_utc(last_at),
            best_frame_at=_utc(first_at + timedelta(seconds=2)),
            received_at=_utc(last_at),
            frame_count=38 - index * 4,
            bbox_x=120,
            bbox_y=90,
            bbox_w=340,
            bbox_h=210,
            detection_confidence=0.93 - index * 0.03,
            vehicle_class="car",
            # No plate is read at any camera: every hop is bridged by the
            # visual tier plus the gate, which is what the footage shows.
            plate_text_raw=None,
            plate_text_norm=None,
            plate_confidence=None,
            plate_is_valid=False,
            embedding_dim=512,
            resolution_status="matched" if index > 0 else "new_vehicle",
            match_method="VISUAL" if index > 0 else "NEW",
            match_score=(
                fused_score(*DEMO_HOP_SCORES[camera_code]) if index > 0 else None
            ),
        )
        session.add(sighting)
        session.commit()
        session.refresh(sighting)

        crop_file = STATIC_CROPS_DIR / f"{sighting.id}.jpg"
        report, digest = _extract_crop(camera_code, crop_file, session)
        # Keep the three crops visually distinct: if this camera's clip yields
        # the same image as an earlier one (two cameras can share a video), ask
        # for the next-best frame instead.
        attempt = 1
        while digest is not None and digest in seen_digests and attempt <= 3:
            report, digest = _extract_crop(camera_code, crop_file, session, rank=attempt)
            attempt += 1
        if digest is not None:
            seen_digests.add(digest)
        crop_reports.append(f"{camera_code}: {report}")
        if crop_file.is_file():
            sighting.crop_path = f"crops/{sighting.id}.jpg"
            session.add(sighting)
            session.commit()

        sightings.append(sighting)

    # Accepted decisions for the two hops, plus rejected candidates so the
    # "Rejected matches" section has real gate output to render.
    for previous, current in zip(sightings[:-1], sightings[1:]):
        gap = int(
            (
                datetime.fromisoformat(current.first_frame_at.replace("Z", "+00:00"))
                - datetime.fromisoformat(previous.first_frame_at.replace("Z", "+00:00"))
            ).total_seconds()
        )
        to_code = camera_code_by_id[current.camera_id]
        hop_visual, hop_temporal = DEMO_HOP_SCORES[to_code]
        hop_fused = fused_score(hop_visual, hop_temporal)
        hop_summaries.append((to_code, gap, hop_visual, hop_temporal, hop_fused))
        session.add(
            MatchDecision(
                sighting_id=current.id,
                candidate_vehicle_id=vehicle.id,
                candidate_sighting_id=previous.id,
                tier="visual",
                outcome="accepted",
                visual_score=hop_visual,
                plate_score=None,
                temporal_score=hop_temporal,
                # Computed, never written by hand.
                fused_score=hop_fused,
                gate_passed=True,
                elapsed_seconds=gap,
                min_transit_seconds=180,
                max_transit_seconds=1450,
                path_distance_m=2150.0,
                review_status="auto",
            )
        )

    # Two rejected candidates on the middle sighting: one per reason code, so
    # both plain-language templates are exercised on screen.
    middle = sightings[1]
    session.add(
        MatchDecision(
            sighting_id=middle.id,
            candidate_vehicle_id=None,
            tier="visual",
            outcome="rejected",
            visual_score=DEMO_REJECTED_VISUAL_TOO_FAST,
            temporal_score=0.0,
            fused_score=fused_score(DEMO_REJECTED_VISUAL_TOO_FAST, 0.0),
            gate_passed=False,
            rejection_reason="TEMPORAL_TOO_FAST",
            elapsed_seconds=14,
            min_transit_seconds=312,
            max_transit_seconds=1600,
            path_distance_m=5200.0,
            review_status="auto",
        )
    )
    session.add(
        MatchDecision(
            sighting_id=middle.id,
            candidate_vehicle_id=None,
            tier="visual",
            outcome="rejected",
            visual_score=DEMO_REJECTED_VISUAL_SAME_CAMERA,
            temporal_score=0.0,
            fused_score=fused_score(DEMO_REJECTED_VISUAL_SAME_CAMERA, 0.0),
            gate_passed=False,
            rejection_reason="SAME_CAMERA_TOO_SOON",
            elapsed_seconds=8,
            min_transit_seconds=30,
            path_distance_m=0.0,
            review_status="auto",
        )
    )
    session.commit()

    return {
        "vehicle_id": vehicle.id,
        "display_ref": vehicle.display_ref,
        "sightings": [(s.id, s.crop_path) for s in sightings],
        "crops": crop_reports,
        "hops": hop_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo vehicle and trajectory.")
    parser.add_argument(
        "--clear", action="store_true", help="Remove previously seeded demo rows first."
    )
    args = parser.parse_args()

    db_session.init_db()
    with Session(db_session.engine) as session:
        if args.clear:
            clear_seeded(session)
        else:
            # Idempotent: re-running replaces the seeded vehicle rather than
            # stacking duplicates that would confuse the trajectory view.
            clear_seeded(session)
        summary = seed(session)

    print(f"Seeded demo vehicle {summary['display_ref']} ({summary['vehicle_id']})")
    for line in summary["crops"]:
        print(f"  crop {line}")
    print("  sightings:")
    for sighting_id, crop_path in summary["sightings"]:
        print(f"    {sighting_id}  crop_path={crop_path}")

    settings = get_settings()
    print()
    print("  accepted hops (fused computed, not stored by hand):")
    for to_code, gap, visual, temporal, fused in summary["hops"]:
        print(
            f"    -> {to_code} ({gap}s): visual={visual:.2f} temporal={temporal:.2f}"
            f"  fused = {settings.W_VISUAL}*{visual} + {settings.W_TEMPORAL}*{temporal}"
            f" = {fused:.4f}"
            f"  [threshold 0.72 {'PASS' if fused > 0.72 else 'FAIL'}]"
        )
    print()
    print("  rejected candidates:")
    for label, visual in (
        ("TEMPORAL_TOO_FAST", DEMO_REJECTED_VISUAL_TOO_FAST),
        ("SAME_CAMERA_TOO_SOON", DEMO_REJECTED_VISUAL_SAME_CAMERA),
    ):
        print(
            f"    {label:22} visual={visual:.2f}"
            f"  fused={fused_score(visual, 0.0):.4f}"
            f"  (sentence shows {round(visual * 100)}%)"
        )


if __name__ == "__main__":
    main()
