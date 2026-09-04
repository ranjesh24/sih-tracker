"""End-to-end: a real clip through the whole worker, producing a valid Sighting.

This is the closest thing to the demo path that runs in CI. It builds a short
short clip from uploaded footage, runs the actual worker with the
real detector, tracker, OCR and embedder, and asserts the emitted JSONL is
something the backend would accept.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = Path(__file__).resolve().parents[2]
BACKEND_INGEST_SCHEMA_PATH = REPO_ROOT / "backend" / "app" / "schemas" / "ingest.py"


def load_backend_ingest_model() -> type:
    """Import IngestSighting by path; backend/ has its own venv (see unit tests)."""
    spec = importlib.util.spec_from_file_location(
        "backend_ingest_schema", BACKEND_INGEST_SCHEMA_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.IngestSighting
# Source footage for the end-to-end run. The suite used to carry its own
# vehicle images and pan a window across one; those images were removed from
# the repository, so the test now borrows a clip that has actually been uploaded
# through the app. If none exists the test skips rather than passing on a
# synthetic shape the detector would never recognise as a vehicle.
UPLOADS_DIR = PIPELINE_ROOT.parent / "backend" / "data" / "uploads"

CLIP_FRAME_COUNT = 30
CLIP_FPS = 10.0
CLIP_WIDTH_PX = 640
CLIP_HEIGHT_PX = 480


def _find_source_clip() -> Path | None:
    """Return an uploaded clip to run the pipeline against, or None."""
    if not UPLOADS_DIR.is_dir():
        return None
    clips = sorted(
        (path for path in UPLOADS_DIR.glob("*.mp4") if path.stat().st_size > 0),
        key=lambda path: path.stat().st_size,
    )
    return clips[0] if clips else None


@pytest.fixture(scope="module")
def test_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Re-encode the first frames of an uploaded clip into a short test clip."""
    source_clip = _find_source_clip()
    if source_clip is None:
        pytest.skip(
            f"no uploaded footage in {UPLOADS_DIR}; upload a clip through the app "
            "to run the end-to-end test"
        )

    capture = cv2.VideoCapture(str(source_clip))
    clip_path = tmp_path_factory.mktemp("clip") / "CAM-01.avi"
    writer = cv2.VideoWriter(
        str(clip_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        CLIP_FPS,
        (CLIP_WIDTH_PX, CLIP_HEIGHT_PX),
    )
    assert writer.isOpened()

    written = 0
    try:
        while written < CLIP_FRAME_COUNT:
            is_read, frame = capture.read()
            if not is_read:
                break
            writer.write(cv2.resize(frame, (CLIP_WIDTH_PX, CLIP_HEIGHT_PX)))
            written += 1
    finally:
        capture.release()
        writer.release()

    if written == 0:
        pytest.skip(f"could not decode any frame from {source_clip.name}")

    return clip_path


@pytest.fixture(scope="module")
def worker_run(test_clip: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the real worker script as a subprocess and return its results."""
    run_dir = tmp_path_factory.mktemp("run")
    output_path = run_dir / "CAM-01.jsonl"

    command = [
        sys.executable,
        str(PIPELINE_ROOT / "scripts" / "run_worker.py"),
        "--video", str(test_clip),
        "--camera-id", "CAM-01",
        "--epoch", "2026-01-01T00:00:00.000Z",
        "--out", str(output_path),
    ]

    environment_overrides = {
        "DEVICE": "mps",
        "FRAME_STRIDE": "1",
        "TRACK_LOST_FRAMES": "5",
        "TRACKLET_MIN_FRAMES": "4",
        "CROP_STORAGE_PATH": str(run_dir / "crops"),
        "BACKEND_STATIC_CROP_PATH": str(run_dir / "static" / "crops"),
        "YOLO_MODEL_PATH": str(PIPELINE_ROOT / "models" / "yolov8s.pt"),
    }

    import os

    environment = {**os.environ, **environment_overrides}

    started_at = time.time()
    completed = subprocess.run(
        command, cwd=PIPELINE_ROOT, env=environment, capture_output=True, text=True
    )
    elapsed_seconds = time.time() - started_at

    return {
        "completed": completed,
        "output_path": output_path,
        "run_dir": run_dir,
        "static_crop_dir": run_dir / "static" / "crops",
        "elapsed_seconds": elapsed_seconds,
    }


def test_worker_exits_successfully(worker_run: dict) -> None:
    completed = worker_run["completed"]

    assert completed.returncode == 0, (
        f"worker failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_worker_emits_at_least_one_sighting(worker_run: dict) -> None:
    lines = worker_run["output_path"].read_text().strip().splitlines()

    assert len(lines) >= 1


def test_emitted_sighting_validates_against_the_backend_ingest_model(
    worker_run: dict,
) -> None:
    """What the worker really emits must be acceptable to the real backend model."""
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])
    ingest_model = load_backend_ingest_model()

    validated = ingest_model.model_validate(record)

    assert validated.camera_code == "CAM-01"
    assert validated.frame_count > 0


def test_emitted_sighting_is_internally_valid(worker_run: dict) -> None:
    """Assert the CHECK constraints the sightings table would enforce."""
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    assert record["camera_code"] == "CAM-01"
    assert record["frame_count"] > 0
    assert record["bbox_w"] > 0 and record["bbox_h"] > 0
    assert 0.0 <= record["detection_confidence"] <= 1.0
    assert record["vehicle_class"] in {
        "car", "motorcycle", "bus", "truck", "auto", "other"
    }
    assert record["resolution_status"] == "pending"
    assert record["last_frame_at"] >= record["first_frame_at"]


def test_emitted_embedding_is_512d_and_unit_norm(worker_run: dict) -> None:
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    embedding = record["embedding"]

    assert record["embedding_dim"] == 512
    assert len(embedding) == 512
    assert float(np.linalg.norm(embedding)) == pytest.approx(1.0, abs=1e-5)


def test_timestamps_derive_from_the_supplied_epoch(worker_run: dict) -> None:
    """The clip starts at the epoch passed on the command line."""
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    first_frame_at = datetime.fromisoformat(
        record["first_frame_at"].replace("Z", "+00:00")
    )
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clip_duration_seconds = CLIP_FRAME_COUNT / CLIP_FPS

    assert epoch <= first_frame_at <= epoch.replace(
        second=int(clip_duration_seconds) + 1
    )


def test_crop_is_written_and_path_is_relative(worker_run: dict) -> None:
    """The crop lands where the backend serves it, keyed by sighting id.

    The path is relative to the backend static root, so the backend maps it to
    /static/crops/<sighting_id>.jpg without knowing anything about the worker's
    filesystem. Keying by sighting id rather than track id matters because track
    ids restart per camera and would otherwise collide across cameras.
    """
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])
    crop_path = record["crop_path"]

    assert not Path(crop_path).is_absolute()
    assert crop_path == f"crops/{record['id']}.jpg"

    written = worker_run["static_crop_dir"] / f"{record['id']}.jpg"
    assert written.is_file(), f"crop not found at {written}"


def test_unreadable_plate_is_none_not_an_error(worker_run: dict) -> None:
    """A vehicle with no legible plate still produces a complete sighting."""
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    if record["plate_text_norm"] is None:
        assert record["plate_is_valid"] is False
        assert record["embedding"] is not None, (
            "a plateless vehicle must still carry an embedding, or it cannot be "
            "matched across cameras at all"
        )
