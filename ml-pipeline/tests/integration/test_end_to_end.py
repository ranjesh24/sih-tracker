"""End-to-end: a real clip through the whole worker, producing a valid Sighting.

This is the closest thing to the demo path that runs in CI. It builds a short
synthetic clip from a real vehicle photograph, runs the actual worker with the
real detector, tracker, OCR and embedder, and asserts the emitted JSONL is
something the backend would accept.
"""

from __future__ import annotations

import json
import re
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
SCHEMA_PATH = REPO_ROOT / "SIH_md_files" / "schema.md"
SAMPLE_IMAGE = PIPELINE_ROOT / "sample_data" / "reid_test" / "car_a_cam1.jpeg"

CLIP_FRAME_COUNT = 30
CLIP_FPS = 10.0
CLIP_WIDTH_PX = 640
CLIP_HEIGHT_PX = 480


def schema_sighting_columns() -> set[str]:
    sql = SCHEMA_PATH.read_text().split("CREATE TABLE sightings (")[1].split(");")[0]
    columns: set[str] = set()
    for line in sql.splitlines():
        match = re.match(r"^([a-z_]+)\s+(TEXT|INTEGER|REAL|BLOB)\b", line.strip())
        if match:
            columns.add(match.group(1))
    return columns


@pytest.fixture(scope="module")
def test_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Pan a window across a real vehicle photo to synthesise a moving vehicle."""
    source = cv2.imread(str(SAMPLE_IMAGE))
    assert source is not None, f"could not read {SAMPLE_IMAGE}"

    source = cv2.resize(source, (960, 788))
    clip_path = tmp_path_factory.mktemp("clip") / "CAM-01.avi"
    writer = cv2.VideoWriter(
        str(clip_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        CLIP_FPS,
        (CLIP_WIDTH_PX, CLIP_HEIGHT_PX),
    )
    assert writer.isOpened()

    for frame_index in range(CLIP_FRAME_COUNT):
        max_x = source.shape[1] - CLIP_WIDTH_PX
        x_px = int(max_x * (frame_index / (CLIP_FRAME_COUNT - 1)))
        writer.write(source[150 : 150 + CLIP_HEIGHT_PX, x_px : x_px + CLIP_WIDTH_PX].copy())

    writer.release()
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


def test_emitted_sighting_matches_the_schema(worker_run: dict) -> None:
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    assert set(record) == schema_sighting_columns()


def test_emitted_sighting_is_internally_valid(worker_run: dict) -> None:
    """Assert the CHECK constraints the sightings table would enforce."""
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])

    assert record["camera_id"] == "CAM-01"
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
    record = json.loads(worker_run["output_path"].read_text().strip().splitlines()[0])
    crop_path = record["crop_path"]

    assert not Path(crop_path).is_absolute()
    assert crop_path.startswith("CAM-01/")

    written = worker_run["run_dir"] / "crops" / crop_path
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
