"""Ingest serialisation and the two emission modes.

The field-name test is the important one. `sighting_to_dict` generates keys from
the Sighting dataclass, and this parses schema.md's CREATE TABLE directly, so
the two are compared against the spec rather than against each other. A column
renamed in the schema fails here rather than silently at the backend.
"""

from __future__ import annotations

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

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "SIH_md_files" / "schema.md"


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


def test_every_serialised_field_name_matches_the_schema() -> None:
    """The 30-column correspondence, checked against schema.md itself."""
    payload = sighting_to_dict(make_sighting())
    columns = schema_sighting_columns()

    assert len(columns) == 30
    assert set(payload) == set(columns)


def test_serialised_payload_is_json_round_trippable() -> None:
    payload = sighting_to_dict(make_sighting())

    restored = json.loads(json.dumps(payload))

    assert restored["camera_id"] == "CAM-01"
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


def test_jsonl_every_line_carries_every_schema_column(tmp_path: Path) -> None:
    output_path = tmp_path / "CAM-01.jsonl"
    columns = set(schema_sighting_columns())

    with JsonlIngestClient(output_path) as client:
        client.send(make_sighting())

    record = json.loads(output_path.read_text().strip())

    assert set(record) == columns


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
