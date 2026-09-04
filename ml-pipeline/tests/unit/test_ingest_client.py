"""Ingest serialisation and the two emission modes.

Two distinct contracts are checked here, and conflating them is what let a real
bug through once already:

  * The `Sighting` dataclass mirrors the `sightings` TABLE in schema.md 3.6.
    Its field is `camera_id`, matching the column.
  * The ingest PAYLOAD targets `backend/app/schemas/ingest.py::IngestSighting`,
    a different and much smaller contract. It expects `camera_code`.

An earlier version of this file asserted the payload against the table columns.
Both the test and the serialiser shared that mistake, so the suite stayed green
while every POST would have been rejected by the backend for a missing required
field. The payload is now validated against the real Pydantic model, imported
directly, so the wire contract cannot drift unnoticed again.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from src.config import Settings
from src.ingest_client import (
    IngestAuthError,
    JsonlIngestClient,
    relative_crop_path,
    sighting_to_dict,
)
from src.types import Sighting

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "SIH_md_files" / "schema.md"
BACKEND_INGEST_SCHEMA_PATH = REPO_ROOT / "backend" / "app" / "schemas" / "ingest.py"


def load_backend_ingest_model() -> type:
    """Import IngestSighting from the backend without importing the backend.

    Loaded by file path rather than as a package: backend/ has its own venv and
    its packages (SQLModel, FastAPI) are not installed here. This module happens
    to depend only on pydantic, which is, so the real model can serve as the
    source of truth instead of a copy that would drift.
    """
    spec = importlib.util.spec_from_file_location(
        "backend_ingest_schema", BACKEND_INGEST_SCHEMA_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.IngestSighting


def schema_sighting_columns() -> list[str]:
    """Parse the sightings column names straight out of schema.md section 3.6."""
    sql = SCHEMA_PATH.read_text().split("CREATE TABLE sightings (")[1].split(");")[0]

    columns: list[str] = []
    for line in sql.splitlines():
        match = re.match(r"^([a-z_]+)\s+(TEXT|INTEGER|REAL|BLOB)\b", line.strip())
        if match:
            columns.append(match.group(1))
    return columns


def make_sighting(**overrides: object) -> Sighting:
    defaults: dict[str, object] = {
        "id": "11111111-2222-3333-4444-555555555555",
        "camera_id": "CAM-01",
        "local_track_id": 17,
        "first_frame_at": "2026-01-01T00:00:00.000Z",
        "last_frame_at": "2026-01-01T00:00:04.000Z",
        "best_frame_at": "2026-01-01T00:00:02.000Z",
        "frame_count": 40,
        "bbox_x": 10,
        "bbox_y": 20,
        "bbox_w": 100,
        "bbox_h": 80,
        "detection_confidence": 0.87,
        "vehicle_class": "car",
        "created_at": "2026-01-01T00:00:05.000Z",
        "embedding": np.ones(512, dtype=np.float32) / np.sqrt(512.0),
        "crop_path": "CAM-01/17.jpg",
    }
    defaults.update(overrides)
    return Sighting(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(CROP_STORAGE_PATH=tmp_path / "crops")


def test_sighting_dataclass_mirrors_the_schema_columns() -> None:
    """The Sighting DATACLASS still mirrors the sightings TABLE, 30 for 30.

    This is the storage-shape contract, and it uses `camera_id` like the column
    does. It is deliberately separate from the wire-shape contract below.
    """
    field_names = {field.name for field in dataclasses.fields(Sighting)}
    columns = schema_sighting_columns()

    assert len(columns) == 30
    assert field_names == set(columns)


def test_payload_validates_against_the_backend_ingest_model() -> None:
    """The wire contract, checked against the real Pydantic model.

    This is the assertion that matters. It parses the payload with the backend's
    own IngestSighting, so a renamed or missing required field fails here rather
    than as a 422 at run time. The earlier version of this test compared the
    payload against the table columns and therefore accepted `camera_id`, which
    the backend does not.
    """
    ingest_model = load_backend_ingest_model()

    validated = ingest_model.model_validate(sighting_to_dict(make_sighting()))

    assert validated.camera_code == "CAM-01"
    assert validated.local_track_id == 17
    assert validated.frame_count == 40


def test_payload_carries_every_field_the_backend_requires() -> None:
    """No required field may be absent from the payload."""
    ingest_model = load_backend_ingest_model()
    required = {
        name for name, field in ingest_model.model_fields.items() if field.is_required()
    }

    payload = sighting_to_dict(make_sighting())

    assert required <= set(payload), f"payload is missing {required - set(payload)}"


def test_payload_uses_camera_code_not_camera_id() -> None:
    """Pinned explicitly, because this exact mismatch shipped once.

    The dataclass field is `camera_id` (the column name); the wire key is
    `camera_code`. The value is the same human code either way.
    """
    payload = sighting_to_dict(make_sighting())

    assert payload["camera_code"] == "CAM-01"
    assert "camera_id" not in payload


def test_serialised_payload_is_json_round_trippable() -> None:
    payload = sighting_to_dict(make_sighting())

    restored = json.loads(json.dumps(payload))

    assert restored["camera_code"] == "CAM-01"
    assert restored["local_track_id"] == 17


def test_embedding_serialises_as_a_512_float_array() -> None:
    payload = sighting_to_dict(make_sighting())

    embedding = payload["embedding"]

    assert isinstance(embedding, list)
    assert len(embedding) == 512
    assert all(isinstance(value, float) for value in embedding)


def test_backend_owned_fields_are_left_unset() -> None:
    """The worker must not invent these; received_at especially."""
    payload = sighting_to_dict(make_sighting())

    assert payload["vehicle_id"] is None
    assert payload["received_at"] is None
    assert payload["resolution_status"] == "pending"
    assert payload["match_method"] is None
    assert payload["match_score"] is None


def test_jsonl_writes_one_parseable_line_per_sighting(tmp_path: Path) -> None:
    output_path = tmp_path / "run" / "CAM-01.jsonl"

    with JsonlIngestClient(output_path) as client:
        client.send(make_sighting(id="a"))
        client.send(make_sighting(id="b"))

    lines = output_path.read_text().strip().splitlines()

    assert len(lines) == 2
    assert [json.loads(line)["id"] for line in lines] == ["a", "b"]


def test_jsonl_lines_validate_against_the_backend_ingest_model(
    tmp_path: Path,
) -> None:
    """A JSONL line must be postable as-is, so the offline path stays replayable."""
    output_path = tmp_path / "CAM-01.jsonl"
    ingest_model = load_backend_ingest_model()

    with JsonlIngestClient(output_path) as client:
        client.send(make_sighting())

    record = json.loads(output_path.read_text().strip())

    validated = ingest_model.model_validate(record)
    assert validated.camera_code == "CAM-01"


def test_jsonl_appends_rather_than_truncating(tmp_path: Path) -> None:
    output_path = tmp_path / "CAM-01.jsonl"

    with JsonlIngestClient(output_path) as first:
        first.send(make_sighting(id="a"))
    with JsonlIngestClient(output_path) as second:
        second.send(make_sighting(id="b"))

    assert len(output_path.read_text().strip().splitlines()) == 2


def test_jsonl_needs_no_network_or_ingest_key(tmp_path: Path) -> None:
    """The demo path: JSONL mode must work with no backend and no key."""
    output_path = tmp_path / "offline.jsonl"

    with JsonlIngestClient(output_path) as client:
        client.send(make_sighting())

    assert client.written_count == 1
    assert output_path.is_file()


def test_crop_path_is_relative_to_crop_storage(settings: Settings) -> None:
    absolute = settings.CROP_STORAGE_PATH / "CAM-01" / "17.jpg"
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(b"")

    assert relative_crop_path(absolute, settings) == "CAM-01/17.jpg"


def test_crop_path_outside_storage_keeps_camera_and_filename(
    settings: Settings, tmp_path: Path
) -> None:
    stray = tmp_path / "elsewhere" / "CAM-02" / "9.jpg"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"")

    assert relative_crop_path(stray, settings) == "CAM-02/9.jpg"


def test_http_mode_refuses_to_start_without_a_key(tmp_path: Path) -> None:
    """Fail at construction, not after the first tracklet completes."""
    from src.ingest_client import HttpIngestClient

    keyless = Settings(INGEST_API_KEY="", CROP_STORAGE_PATH=tmp_path / "crops")

    with pytest.raises(IngestAuthError, match="INGEST_API_KEY is empty"):
        HttpIngestClient(keyless)


def test_timestamps_are_iso8601_utc_with_z() -> None:
    """schema.md section 2: lexicographic order must equal chronological order."""
    payload = sighting_to_dict(make_sighting())

    for field_name in ("first_frame_at", "last_frame_at", "best_frame_at", "created_at"):
        value = payload[field_name]
        assert isinstance(value, str)
        assert value.endswith("Z"), field_name
        datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
