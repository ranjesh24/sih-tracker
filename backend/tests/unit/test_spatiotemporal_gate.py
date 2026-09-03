"""Unit tests for the spatio-temporal gate and camera-graph transit windows
(techspec.md section 5.6; TASK-119).

Covers the four rejection reasons plus FEASIBLE, the two-hop sum-of-edges window,
bidirectional traversal, and the CameraNotFoundError raise for an absent camera.
"""
import pytest

from app.core.exceptions import CameraNotFoundError
from app.models import CameraEdge
from app.services.camera_graph import CameraGraph
from app.services.spatiotemporal_gate import GateStatus, evaluate_gate

MIN_REVISIT_SECONDS = 30

# Node ids and their human codes.
CAM_1, CAM_2, CAM_3, CAM_ISOLATED = "c1", "c2", "c3", "c4"
CODES = {CAM_1: "CAM-01", CAM_2: "CAM-02", CAM_3: "CAM-03", CAM_ISOLATED: "CAM-04"}


def _edge(
    from_id: str,
    to_id: str,
    min_s: int,
    max_s: int,
    dist_m: float,
    bidirectional: bool = True,
) -> CameraEdge:
    return CameraEdge(
        from_camera_id=from_id,
        to_camera_id=to_id,
        min_transit_seconds=min_s,
        max_transit_seconds=max_s,
        distance_m=dist_m,
        is_bidirectional=bidirectional,
    )


def _graph(bidirectional: bool = True) -> CameraGraph:
    """c1 -- c2 -- c3 (chain), plus an isolated c4. Edges optionally one-way."""
    graph = CameraGraph()
    for camera_id, code in CODES.items():
        graph.add_camera(camera_id, code)
    graph.add_edge(_edge(CAM_1, CAM_2, 10, 30, 1000.0, bidirectional))
    graph.add_edge(_edge(CAM_2, CAM_3, 5, 20, 500.0, bidirectional))
    return graph


def _gate(from_id: str, to_id: str, elapsed_seconds: int, graph: CameraGraph):
    return evaluate_gate(
        from_camera_id=from_id,
        to_camera_id=to_id,
        elapsed_seconds=elapsed_seconds,
        graph=graph,
        min_revisit_seconds=MIN_REVISIT_SECONDS,
    )


# --- the four rejection reasons ---


def test_rejects_same_camera_before_min_revisit() -> None:
    decision = _gate(CAM_1, CAM_1, elapsed_seconds=5, graph=_graph())

    assert decision.status is GateStatus.SAME_CAMERA_TOO_SOON
    assert decision.passed is False
    assert decision.reason == "SAME_CAMERA_TOO_SOON"


def test_rejects_when_no_path_between_cameras() -> None:
    decision = _gate(CAM_1, CAM_ISOLATED, elapsed_seconds=100, graph=_graph())

    assert decision.status is GateStatus.NO_PATH
    assert decision.passed is False
    assert decision.min_transit_seconds is None


def test_rejects_when_elapsed_below_min_transit() -> None:
    decision = _gate(CAM_1, CAM_2, elapsed_seconds=5, graph=_graph())

    assert decision.status is GateStatus.TEMPORAL_TOO_FAST
    assert decision.min_transit_seconds == 10
    assert decision.max_transit_seconds == 30


def test_rejects_when_elapsed_above_max_transit() -> None:
    decision = _gate(CAM_1, CAM_2, elapsed_seconds=120, graph=_graph())

    assert decision.status is GateStatus.TEMPORAL_EXPIRED
    assert decision.passed is False


# --- FEASIBLE ---


def test_feasible_single_hop_within_window() -> None:
    decision = _gate(CAM_1, CAM_2, elapsed_seconds=20, graph=_graph())

    assert decision.status is GateStatus.FEASIBLE
    assert decision.passed is True
    assert decision.reason is None
    assert decision.path_distance_m == 1000.0
    assert decision.path_camera_codes == ["CAM-01", "CAM-02"]


def test_feasible_same_camera_after_min_revisit() -> None:
    decision = _gate(CAM_1, CAM_1, elapsed_seconds=45, graph=_graph())

    assert decision.status is GateStatus.FEASIBLE
    assert decision.path_camera_codes == ["CAM-01"]


# --- two-hop path: window and distance are the sum of two edges ---


def test_two_hop_window_and_distance_are_sum_of_edges() -> None:
    path = _graph().shortest_path(CAM_1, CAM_3)

    assert path.exists is True
    assert path.hop_count == 2
    assert path.min_transit_seconds == 15  # 10 + 5
    assert path.max_transit_seconds == 50  # 30 + 20
    assert path.distance_m == 1500.0  # 1000 + 500
    assert path.camera_codes == ["CAM-01", "CAM-02", "CAM-03"]


def test_two_hop_feasible_within_summed_window() -> None:
    decision = _gate(CAM_1, CAM_3, elapsed_seconds=40, graph=_graph())

    assert decision.status is GateStatus.FEASIBLE
    assert decision.min_transit_seconds == 15
    assert decision.max_transit_seconds == 50


# --- bidirectional traversal ---


def test_bidirectional_edge_is_traversable_in_reverse() -> None:
    # c2 -> c1 only exists because the c1--c2 edge is bidirectional.
    decision = _gate(CAM_2, CAM_1, elapsed_seconds=20, graph=_graph(bidirectional=True))

    assert decision.status is GateStatus.FEASIBLE
    assert decision.path_camera_codes == ["CAM-02", "CAM-01"]


def test_one_way_edge_has_no_reverse_path() -> None:
    decision = _gate(CAM_2, CAM_1, elapsed_seconds=20, graph=_graph(bidirectional=False))

    assert decision.status is GateStatus.NO_PATH


# --- absent camera is a configuration error, not a rejection ---


def test_absent_camera_raises_camera_not_found() -> None:
    with pytest.raises(CameraNotFoundError):
        _gate(CAM_1, "does-not-exist", elapsed_seconds=20, graph=_graph())
