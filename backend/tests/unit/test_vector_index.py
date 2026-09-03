"""Unit tests for the FAISS-backed VectorIndex (TASK-209)."""
from datetime import datetime, timezone

import numpy as np
import pytest

from app.services.vector_index import VectorIndex, encode_embedding
from tests.factories import iso, make_camera, make_sighting, unit_vector

DIM = 8


def _norm(v: np.ndarray) -> np.ndarray:
    return np.asarray(v, dtype=np.float32) / np.linalg.norm(v)


def test_add_and_search_roundtrip() -> None:
    index = VectorIndex(dim=DIM)
    a = _norm(unit_vector(1, DIM))
    b = _norm(unit_vector(2, DIM))
    index.add("s-a", a)
    index.add("s-b", b)

    results = index.search(a, k=2)

    assert len(index) == 2
    assert results[0][0] == "s-a"
    assert results[0][1] == pytest.approx(1.0, abs=1e-5)


def test_dimension_mismatch_raises() -> None:
    index = VectorIndex(dim=DIM)
    with pytest.raises(ValueError):
        index.add("s-bad", np.zeros(DIM + 1, dtype=np.float32))


def test_search_subset_returns_only_given_candidates() -> None:
    index = VectorIndex(dim=DIM)
    for i in range(1, 4):
        index.add(f"s-{i}", _norm(unit_vector(i, DIM)))
    query = _norm(unit_vector(1, DIM))

    scores = index.search_subset(query, ["s-1", "s-3", "s-unknown"])

    assert set(scores.keys()) == {"s-1", "s-3"}  # s-2 excluded, unknown skipped
    assert scores["s-1"] == pytest.approx(1.0, abs=1e-5)


def test_rebuild_from_db_loads_persisted_embeddings(session) -> None:
    camera = make_camera(session, "CAM-01")
    now = iso(datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc))
    # Two sightings with embeddings, one without.
    make_sighting(session, camera_id=camera.id, first_frame_at=now, embedding_vector=unit_vector(1))
    make_sighting(session, camera_id=camera.id, first_frame_at=now, embedding_vector=unit_vector(2))
    make_sighting(session, camera_id=camera.id, first_frame_at=now, embedding_vector=None)
    session.commit()

    index = VectorIndex(dim=512)
    loaded = index.rebuild_from_db(session)

    assert loaded == 2
    assert len(index) == 2


def test_encode_embedding_is_unit_length() -> None:
    blob = encode_embedding(np.array([3.0, 4.0] + [0.0] * 510, dtype=np.float32))
    vec = np.frombuffer(blob, dtype=np.float32)
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-6)
