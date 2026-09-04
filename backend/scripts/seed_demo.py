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
from sqlmodel import Session, select  # noqa: E402

import app.db.session as db_session  # noqa: E402
from app.models import Camera, MatchDecision, Sighting, Vehicle  # noqa: E402

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
import sys
import cv2

clip_path, target, camera_code, plate, width, height = sys.argv[1:7]
width, height = int(width), int(height)

wrote = False
if clip_path:
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
            wrote = bool(cv2.imwrite(target, cv2.resize(crop, (width, height))))

if not wrote:
    import numpy as np
    frame = np.full((height, width, 3), 32, dtype=np.uint8)
    cv2.rectangle(frame, (40, 40), (width - 40, height - 40), (90, 180, 90), 2)
    cv2.putText(frame, camera_code, (60, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (230, 230, 230), 2)
    cv2.putText(frame, plate, (60, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (140, 200, 140), 2)
    wrote = bool(cv2.imwrite(target, frame))
    print("placeholder" if wrote else "FAILED")
else:
    print("frame")
"""

# The demo vehicle. A single car passing three junctions in sequence.
DEMO_PLATE = "BR01AB1234"
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


def _find_clip_for(camera_code: str) -> Path | None:
    """Return an uploaded clip recorded on this camera, if any."""
    if not UPLOADS_DIR.is_dir():
        return None
    matches = sorted(UPLOADS_DIR.glob(f"*_{camera_code}.*"))
    return matches[-1] if matches else None


def _extract_crop(camera_code: str, target: Path) -> str:
    """Write a crop JPEG for one camera and report how it was produced."""
    interpreter = _imaging_python()
    if interpreter is None:
        return "FAILED (no interpreter with opencv found)"

    clip = _find_clip_for(camera_code)
    result = subprocess.run(
        [
            interpreter,
            "-c",
            _CROP_SCRIPT,
            str(clip) if clip else "",
            str(target),
            camera_code,
            DEMO_PLATE,
            str(CROP_WIDTH_PX),
            str(CROP_HEIGHT_PX),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not target.is_file():
        return f"FAILED ({result.stderr.strip().splitlines()[-1:] or 'unknown'})"

    kind = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "written"
    if kind == "frame" and clip is not None:
        return f"frame from {clip.name}"
    return "generated placeholder"


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
        canonical_plate=DEMO_PLATE,
        plate_confidence=0.94,
        plate_is_valid=True,
        vehicle_class="car",
        sighting_count=len(DEMO_HOPS),
        camera_count=len(DEMO_HOPS),
        status="active",
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)

    crop_reports: list[str] = []
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
            plate_text_raw=DEMO_PLATE if index != 1 else "BR01A81234",
            # Camera 2 is the plate failure the visual tier has to bridge.
            plate_text_norm=DEMO_PLATE if index != 1 else None,
            plate_confidence=0.94 if index != 1 else 0.31,
            plate_is_valid=index != 1,
            embedding_dim=512,
            resolution_status="matched" if index > 0 else "new_vehicle",
            match_method=("PLATE_EXACT" if index == 2 else "VISUAL") if index > 0 else "NEW",
            match_score=0.91 if index > 0 else None,
        )
        session.add(sighting)
        session.commit()
        session.refresh(sighting)

        crop_file = STATIC_CROPS_DIR / f"{sighting.id}.jpg"
        report = _extract_crop(camera_code, crop_file)
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
        session.add(
            MatchDecision(
                sighting_id=current.id,
                candidate_vehicle_id=vehicle.id,
                candidate_sighting_id=previous.id,
                tier="plate" if current.match_method == "PLATE_EXACT" else "visual",
                outcome="accepted",
                visual_score=0.88,
                plate_score=1.0 if current.match_method == "PLATE_EXACT" else None,
                temporal_score=0.95,
                fused_score=0.91,
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
            visual_score=0.91,
            temporal_score=0.0,
            fused_score=0.42,
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
            visual_score=0.86,
            temporal_score=0.0,
            fused_score=0.39,
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


if __name__ == "__main__":
    main()
