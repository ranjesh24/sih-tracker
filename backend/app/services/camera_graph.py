"""Camera graph service (techspec.md sections 4 & 5.6; CLAUDE.md).

Builds a ``networkx.DiGraph`` from ``camera_edges``, finds the shortest path
weighted by ``min_transit_seconds``, and sums the per-edge transit windows and
distance along that path. It also derives the spatio-temporal feasible candidate
set for a new sighting — the candidate generator for the amended visual tier
(techspec.md 5.6): the graph proposes who could physically be here, vision only
ranks within that set.

``is_bidirectional`` edges are traversable both ways, so the reverse edge is
added when the flag is set; a forward-only graph would report ``NO_PATH`` on half
of all legitimate matches and present as a model problem rather than a graph bug.

Layering: depends only on models, core, and the pure gate. It takes last-sighting
rows as input data rather than importing a repository, so it stays unit-testable.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from app.core.config import get_settings
from app.core.exceptions import CameraNotFoundError
from app.models import Camera, CameraEdge

MIN_TRANSIT_ATTR: str = "min_transit_seconds"
MAX_TRANSIT_ATTR: str = "max_transit_seconds"
DISTANCE_ATTR: str = "distance_m"
CODE_ATTR: str = "code"

_SAME_NODE_HOP_COUNT: int = 0
_ZERO_SECONDS: int = 0
_ZERO_DISTANCE_M: float = 0.0


@dataclass(frozen=True)
class PathResult:
    """Resolved shortest path between two cameras.

    ``exists`` is False when the destination is unreachable from the source.
    When it exists, the transit bounds and distance are summed over the path's
    edges and ``camera_codes`` lists the human camera codes along it.
    """

    exists: bool
    camera_codes: list[str]
    min_transit_seconds: int
    max_transit_seconds: int
    distance_m: float
    hop_count: int


@dataclass(frozen=True)
class CandidateSighting:
    """The last known sighting of a candidate vehicle."""

    vehicle_id: str
    camera_id: str
    seen_at: datetime


@dataclass(frozen=True)
class FeasibleCandidate:
    """A candidate vehicle that passed the spatio-temporal gate."""

    vehicle_id: str
    decision: "object"  # GateDecision; annotated loosely to avoid an import cycle


class CameraGraph:
    """Directed camera-transition graph over camera UUIDs."""

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    @classmethod
    def from_models(
        cls, cameras: Iterable[Camera], edges: Iterable[CameraEdge]
    ) -> "CameraGraph":
        """Build a graph from ``cameras`` (for node codes) and ``camera_edges``."""
        graph = cls()
        for camera in cameras:
            graph.add_camera(camera.id, camera.code)
        for edge in edges:
            graph.add_edge(edge)
        return graph

    def add_camera(self, camera_id: str, code: str) -> None:
        """Register a camera node and its human code."""
        self._graph.add_node(camera_id, **{CODE_ATTR: code})

    def add_edge(self, edge: CameraEdge) -> None:
        """Add the directed transition edge, plus its reverse if bidirectional."""
        self._add_directed(
            edge.from_camera_id,
            edge.to_camera_id,
            edge.min_transit_seconds,
            edge.max_transit_seconds,
            edge.distance_m,
        )
        if edge.is_bidirectional:
            self._add_directed(
                edge.to_camera_id,
                edge.from_camera_id,
                edge.min_transit_seconds,
                edge.max_transit_seconds,
                edge.distance_m,
            )

    def _add_directed(
        self,
        from_id: str,
        to_id: str,
        min_transit_seconds: int,
        max_transit_seconds: int,
        distance_m: float,
    ) -> None:
        self._graph.add_edge(
            from_id,
            to_id,
            **{
                MIN_TRANSIT_ATTR: min_transit_seconds,
                MAX_TRANSIT_ATTR: max_transit_seconds,
                DISTANCE_ATTR: distance_m,
            },
        )

    def has_camera(self, camera_id: str) -> bool:
        """Return True if the camera is a node in the graph."""
        return self._graph.has_node(camera_id)

    def _code(self, camera_id: str) -> str:
        """Human code for a node, falling back to the id if none was recorded."""
        return self._graph.nodes[camera_id].get(CODE_ATTR, camera_id)

    def shortest_path(self, from_camera_id: str, to_camera_id: str) -> PathResult:
        """Shortest path (min total ``min_transit_seconds``) between two cameras.

        Args:
            from_camera_id: source camera UUID.
            to_camera_id: destination camera UUID.

        Returns:
            A :class:`PathResult`. For the same camera it is a zero-length path;
            for an unreachable destination ``exists`` is False.

        Raises:
            CameraNotFoundError: if either camera is absent from the graph.
        """
        if not self.has_camera(from_camera_id):
            raise CameraNotFoundError(from_camera_id)
        if not self.has_camera(to_camera_id):
            raise CameraNotFoundError(to_camera_id)

        if from_camera_id == to_camera_id:
            return PathResult(
                exists=True,
                camera_codes=[self._code(from_camera_id)],
                min_transit_seconds=_ZERO_SECONDS,
                max_transit_seconds=_ZERO_SECONDS,
                distance_m=_ZERO_DISTANCE_M,
                hop_count=_SAME_NODE_HOP_COUNT,
            )

        try:
            nodes = nx.shortest_path(
                self._graph,
                source=from_camera_id,
                target=to_camera_id,
                weight=MIN_TRANSIT_ATTR,
            )
        except nx.NetworkXNoPath:
            return PathResult(False, [], _ZERO_SECONDS, _ZERO_SECONDS, _ZERO_DISTANCE_M, 0)

        total_min_seconds = 0
        total_max_seconds = 0
        total_distance_m = 0.0
        for src, dst in zip(nodes[:-1], nodes[1:]):
            data = self._graph.edges[src, dst]
            total_min_seconds += data[MIN_TRANSIT_ATTR]
            total_max_seconds += data[MAX_TRANSIT_ATTR]
            total_distance_m += data[DISTANCE_ATTR]

        return PathResult(
            exists=True,
            camera_codes=[self._code(n) for n in nodes],
            min_transit_seconds=total_min_seconds,
            max_transit_seconds=total_max_seconds,
            distance_m=total_distance_m,
            hop_count=len(nodes) - 1,
        )

    def feasible_candidates(
        self,
        camera_id: str,
        timestamp: datetime,
        last_sightings: Sequence[CandidateSighting],
        min_revisit_seconds: int | None = None,
    ) -> list[FeasibleCandidate]:
        """Vehicles that could physically be at ``camera_id`` at ``timestamp``.

        Each candidate's last sighting is passed through the gate; only those the
        gate marks feasible are returned. A candidate whose camera is absent from
        the graph raises :class:`CameraNotFoundError` — a broken topology surfaces
        rather than silently dropping candidates.
        """
        # Local import breaks the gate<->graph import cycle (rules.md layering).
        from app.services.spatiotemporal_gate import evaluate_gate

        if min_revisit_seconds is None:
            min_revisit_seconds = get_settings().MIN_REVISIT_SECONDS

        feasible: list[FeasibleCandidate] = []
        for candidate in last_sightings:
            elapsed_seconds = int((timestamp - candidate.seen_at).total_seconds())
            decision = evaluate_gate(
                from_camera_id=candidate.camera_id,
                to_camera_id=camera_id,
                elapsed_seconds=elapsed_seconds,
                graph=self,
                min_revisit_seconds=min_revisit_seconds,
            )
            if decision.passed:
                feasible.append(FeasibleCandidate(candidate.vehicle_id, decision))
        return feasible
