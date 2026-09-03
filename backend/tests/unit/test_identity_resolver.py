"""Identity resolver tests — the amended algorithm (techspec.md 5.6; TASK-211..214).

In-memory SQLite, synthetic 512-D vectors, no model loading.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.models import MatchDecision, Sighting
from app.services.identity_resolver import resolve
from tests.factories import (
    blended_vector,
    iso,
    make_camera,
    make_edge,
    make_sighting,
    make_vehicle,
    unit_vector,
)

T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
PLATE = "BR01AB1234"
# Edge transit window [60, 600] s between the two cameras.
EDGE_MIN_S, EDGE_MAX_S = 60, 600


def _two_cameras(session):
    c1 = make_camera(session, "CAM-01")
    c2 = make_camera(session, "CAM-02")
    make_edge(
        session,
        c1.id,
        c2.id,
        min_transit_seconds=EDGE_MIN_S,
        max_transit_seconds=EDGE_MAX_S,
        distance_m=3000.0,
    )
    return c1, c2


def _decisions_for(session, sighting_id: str) -> list[MatchDecision]:
    return list(
        session.exec(
            select(MatchDecision).where(MatchDecision.sighting_id == sighting_id)
        ).all()
    )


def test_plate_exact_match_gate_passes_assigns_plate_exact(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1", canonical_plate=PLATE, plate_is_valid=True)
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=300)),
        embedding_vector=unit_vector(1), plate_text_norm=PLATE, plate_is_valid=True,
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned == v1.id
    assert new.match_method == "PLATE_EXACT"
    accepted = [d for d in decisions if d.outcome == "accepted"]
    assert accepted and accepted[0].tier == "plate" and accepted[0].gate_passed is True


def test_plate_matches_but_gate_rejects_falls_through(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1", canonical_plate=PLATE, plate_is_valid=True)
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    # Only 10 s later at the far camera: below the 60 s minimum -> TEMPORAL_TOO_FAST.
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=10)),
        embedding_vector=unit_vector(1), plate_text_norm=PLATE, plate_is_valid=True,
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned != v1.id  # not assigned to the plate match
    plate_rejects = [
        d for d in decisions
        if d.tier == "plate" and d.outcome == "rejected"
    ]
    assert plate_rejects
    assert plate_rejects[0].rejection_reason == "TEMPORAL_TOO_FAST"
    assert plate_rejects[0].gate_passed is False


def test_no_plate_single_best_candidate_assigns_visual(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1")
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=300)),
        embedding_vector=unit_vector(1),
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned == v1.id
    assert new.match_method == "VISUAL"
    accepted = [d for d in decisions if d.outcome == "accepted"]
    assert accepted and accepted[0].tier == "visual"
    # gate numerics populated on the accepted decision
    d = accepted[0]
    assert d.elapsed_seconds == 300
    assert d.min_transit_seconds == EDGE_MIN_S
    assert d.max_transit_seconds == EDGE_MAX_S
    assert d.path_distance_m == 3000.0
    assert d.path_camera_codes == "CAM-01,CAM-02"


def test_two_candidates_within_margin_is_ambiguous(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1")
    v2 = make_vehicle(session, display_ref="#V2")
    # Both candidates identical to the query and identically feasible -> tie.
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v2.id, embedding_vector=unit_vector(1),
    )
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=300)),
        embedding_vector=unit_vector(1),
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned is None
    assert new.vehicle_id is None
    assert new.resolution_status == "ambiguous"
    ambiguous = [d for d in decisions if d.outcome == "ambiguous"]
    assert ambiguous and ambiguous[0].rejection_reason == "AMBIGUOUS_MARGIN"
    assert ambiguous[0].runner_up_score is not None


def test_empty_feasible_set_creates_new_identity(session) -> None:
    _c1, c2 = _two_cameras(session)
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0),
        embedding_vector=unit_vector(1),
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned is not None
    assert new.vehicle_id == assigned
    assert new.match_method == "NEW"
    assert new.resolution_status == "new_vehicle"


def test_all_candidates_below_visual_floor_creates_new_identity(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1")
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    # Query is (near) orthogonal to the candidate -> cosine well below floor.
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=300)),
        embedding_vector=unit_vector(999),
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert new.match_method == "NEW"
    assert assigned != v1.id
    below = [d for d in decisions if d.rejection_reason == "BELOW_THRESHOLD"]
    assert below


def test_white_maruti_visually_identical_but_infeasible_is_gate_rejected(session) -> None:
    """The central claim: cosine 0.74 but physically impossible -> rejected."""
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1")
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    # Near-identical appearance (cosine ~0.74) but only 10 s apart across 3 km.
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=10)),
        embedding_vector=blended_vector(1, cosine=0.74),
    )
    session.commit()

    assigned, decisions = resolve(session, new)

    assert assigned != v1.id  # the gate refused the visually-identical match
    gate_rejects = [
        d for d in decisions
        if d.tier == "visual" and d.rejection_reason == "TEMPORAL_TOO_FAST"
    ]
    assert gate_rejects
    assert gate_rejects[0].gate_passed is False
    assert gate_rejects[0].visual_score == pytest.approx(0.74, abs=0.03)


def test_every_decision_persists_to_the_database(session) -> None:
    c1, c2 = _two_cameras(session)
    v1 = make_vehicle(session, display_ref="#V1")
    make_sighting(
        session, camera_id=c1.id, first_frame_at=iso(T0),
        vehicle_id=v1.id, embedding_vector=unit_vector(1),
    )
    new = make_sighting(
        session, camera_id=c2.id, first_frame_at=iso(T0 + timedelta(seconds=300)),
        embedding_vector=unit_vector(1),
    )
    session.commit()

    _assigned, decisions = resolve(session, new)
    session.commit()

    persisted = _decisions_for(session, new.id)
    assert len(persisted) == len(decisions)
    assert len(persisted) >= 1
