"""Integration tests: ingest through to a persisted resolved sighting, and the
batch runner producing identical results to the ingest path on the same input.

In-memory SQLite (shared via StaticPool), TestClient, synthetic 512-D vectors,
no model loading.
"""
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.db.session as db_session
import app.models  # noqa: F401  (register tables)
from app.core.config import get_settings
from app.models import Sighting
from app.repositories import match_decision_repo
from tests.factories import iso, make_camera, make_edge, unit_vector

INGEST_KEY = "testkey"
T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "scripts")


def _fresh_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_two_cameras(engine) -> None:
    with Session(engine) as session:
        c1 = make_camera(session, "CAM-01")
        c2 = make_camera(session, "CAM-02")
        make_edge(
            session, c1.id, c2.id,
            min_transit_seconds=60, max_transit_seconds=600, distance_m=3000.0,
        )
        session.commit()


def _record(camera_code: str, secs: int, seed: int, plate: str | None = None) -> dict:
    return {
        "camera_code": camera_code,
        "local_track_id": seed,
        "first_frame_at": iso(T0 + timedelta(seconds=secs)),
        "last_frame_at": iso(T0 + timedelta(seconds=secs)),
        "best_frame_at": iso(T0 + timedelta(seconds=secs)),
        "frame_count": 5,
        "bbox_x": 0, "bbox_y": 0, "bbox_w": 10, "bbox_h": 10,
        "detection_confidence": 0.9,
        "vehicle_class": "car",
        "plate_text_raw": plate,
        "embedding": unit_vector(seed).tolist(),
    }


def _records() -> list[dict]:
    # Sorted by first_frame_at: a first sighting, a plate+visual re-sighting, and
    # a visually different new vehicle.
    return [
        _record("CAM-01", 0, seed=1, plate="BR01AB1234"),
        _record("CAM-02", 300, seed=1, plate="BR01AB1234"),
        _record("CAM-02", 320, seed=999),
    ]


def _summarise(engine) -> dict:
    with Session(engine) as session:
        sightings = list(session.exec(select(Sighting)).all())
        methods: Counter[str] = Counter(
            s.match_method for s in sightings if s.match_method
        )
        ambiguous = sum(1 for s in sightings if s.resolution_status == "ambiguous")
        reasons = match_decision_repo.count_by_rejection_reason(session)
    return {
        "total_sightings": len(sightings),
        "vehicles_created": methods.get("NEW", 0),
        "matches_by_method": dict(methods),
        "rejections_by_reason": reasons,
        "ambiguous_margin_count": reasons.get("AMBIGUOUS_MARGIN", 0),
        "ambiguous": ambiguous,
    }


@pytest.fixture(autouse=True)
def _ingest_key_env():
    os.environ["INGEST_API_KEY"] = INGEST_KEY
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client(engine):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_ingest_resolves_and_persists(monkeypatch) -> None:
    engine = _fresh_engine()
    monkeypatch.setattr(db_session, "engine", engine)
    _seed_two_cameras(engine)

    with _client(engine) as client:
        payload = _record("CAM-01", 0, seed=1, plate="BR01AB1234")
        resp = client.post(
            "/api/v1/ingest/sightings",
            json=payload,
            headers={"X-Ingest-Key": INGEST_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()
        sighting_id = body["sighting_id"]
        assert body["vehicle_id"] is not None
        assert body["resolution_status"] == "new_vehicle"

        # Persisted and fetchable through the read API.
        detail = client.get(f"/api/v1/sightings/{sighting_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == sighting_id

        # Wrong key -> 401 INVALID_INGEST_KEY.
        bad = client.post(
            "/api/v1/ingest/sightings",
            json=payload,
            headers={"X-Ingest-Key": "wrong"},
        )
        assert bad.status_code == 401
        assert bad.json()["error"]["code"] == "INVALID_INGEST_KEY"

        # Unregistered camera -> 404 CAMERA_NOT_FOUND (appflow 6.4).
        unknown = client.post(
            "/api/v1/ingest/sightings",
            json=_record("CAM-99", 5, seed=2),
            headers={"X-Ingest-Key": INGEST_KEY},
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "CAMERA_NOT_FOUND"


def test_batch_matches_ingest_path(monkeypatch, tmp_path) -> None:
    records = _records()

    # --- Path A: HTTP ingest ---
    engine_a = _fresh_engine()
    monkeypatch.setattr(db_session, "engine", engine_a)
    _seed_two_cameras(engine_a)
    with _client(engine_a) as client:
        for record in records:
            resp = client.post(
                "/api/v1/ingest/sightings",
                json=record,
                headers={"X-Ingest-Key": INGEST_KEY},
            )
            assert resp.status_code == 200
    summary_a = _summarise(engine_a)

    # --- Path B: batch runner on the same input, same seeded topology ---
    engine_b = _fresh_engine()
    monkeypatch.setattr(db_session, "engine", engine_b)
    _seed_two_cameras(engine_b)
    jsonl = tmp_path / "records.jsonl"
    import json

    jsonl.write_text("\n".join(json.dumps(r) for r in records))

    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
    import run_batch

    summary_b = run_batch.run(jsonl, gate_enabled=True)
    summary_b.pop("gate_enabled")

    assert summary_a["total_sightings"] == summary_b["total_sightings"] == len(records)
    assert summary_a["vehicles_created"] == summary_b["vehicles_created"]
    assert summary_a["matches_by_method"] == summary_b["matches_by_method"]
    assert summary_a["rejections_by_reason"] == summary_b["rejections_by_reason"]
    assert summary_a["ambiguous_margin_count"] == summary_b["ambiguous_margin_count"]
